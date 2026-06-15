#!/usr/bin/env python3
"""
Build the compact fast-audit table from tw_act evidence and the auth index.

This script reads only compact derived data and source tw_act text files. It does
not query access-log families and does not modify firewall state.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any


DEFAULT_SFTP_ROOT = Path("/proc/1/root/raid5/sftp/huashu/upload")
DEFAULT_INDEX_DIR = Path("/tmp/fanqiang_indexes")
DEFAULT_CONTROL_JSON = Path("/tmp/fanqiang_control_check.json")

OUTPUT_COLUMNS = [
    "学号/账号",
    "翻墙时间",
    "内网IP",
    "翻墙协议/类型",
    "访问IP/对象",
    "身份时间匹配",
    "学号匹配",
    "备注",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build fast proxy/VPN audit CSV.")
    parser.add_argument("--date", required=True, help="Audit date, format YYYY-MM-DD.")
    parser.add_argument("--start", help="Start time, default date 00:00:00.")
    parser.add_argument("--end", help="End time, default date 23:59:59.")
    parser.add_argument("--sftp-root", default=str(DEFAULT_SFTP_ROOT))
    parser.add_argument("--auth-index", help="SQLite auth index path.")
    parser.add_argument("--index-dir", default=str(DEFAULT_INDEX_DIR))
    parser.add_argument("--control-json", default=str(DEFAULT_CONTROL_JSON))
    parser.add_argument("--out", required=True, help="Output CSV path.")
    parser.add_argument("--summary", help="Output JSON summary path.")
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def parse_time(value: str | None, day: dt.date, default: dt.time) -> dt.datetime:
    if not value:
        return dt.datetime.combine(day, default)
    value = value.strip()
    if len(value) == 8 and value.count(":") == 2:
        return dt.datetime.combine(day, dt.datetime.strptime(value, "%H:%M:%S").time())
    return dt.datetime.strptime(value, "%Y-%m-%d %H:%M:%S")


def day_from_arg(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def iter_tw_rows(sftp_root: Path, day: dt.date, start: dt.datetime, end: dt.datetime) -> tuple[list[dict[str, str]], int, int]:
    files = sorted(sftp_root.glob(f"tw_act_{day:%Y%m%d}*.txt"))
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    duplicate_rows = 0
    for path in files:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                parts = [part.strip() for part in line.split(",")]
                if len(parts) < 6:
                    continue
                try:
                    event_time = dt.datetime.strptime(parts[0], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
                if not (start <= event_time <= end):
                    continue
                dedupe_key = (parts[0], parts[3], parts[4], parts[5], parts[6] if len(parts) > 6 else "")
                if dedupe_key in seen:
                    duplicate_rows += 1
                    continue
                seen.add(dedupe_key)
                rows.append(
                    {
                        "time": event_time.strftime("%Y-%m-%d %H:%M:%S"),
                        "ip": parts[3],
                        "target": parts[4],
                        "protocol": parts[5],
                        "object": parts[6] if len(parts) > 6 else "",
                        "source_file": str(path),
                    }
                )
    return rows, len(files), duplicate_rows


def auth_index_path(args: argparse.Namespace, day: dt.date) -> Path:
    if args.auth_index:
        return Path(args.auth_index)
    return Path(args.index_dir) / f"auth_index_{day:%Y%m%d}.sqlite"


def load_control_status(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"status_by_ip": {}, "load_error": f"control json not found: {path}"}
    data = json.loads(path.read_text(encoding="utf-8"))
    status_by_ip = data.get("status_by_ip")
    if not isinstance(status_by_ip, dict):
        status_by_ip = {}
    return {"status_by_ip": status_by_ip, "raw": data}


def choose_auth_match(conn: sqlite3.Connection, ip: str, event_time: str) -> tuple[str, str, str]:
    exact = conn.execute(
        """
        SELECT account, online_start, online_end
        FROM auth_sessions
        WHERE ip = ?
          AND online_start <= ?
          AND online_end >= ?
        ORDER BY
          CASE WHEN account IS NULL OR account = '' THEN 1 ELSE 0 END,
          online_start DESC
        LIMIT 1
        """,
        (ip, event_time, event_time),
    ).fetchone()
    if exact:
        account = exact[0] or ""
        return account, "覆盖", "已匹配" if account else "未匹配"

    same_day = conn.execute(
        """
        SELECT account, online_start, online_end
        FROM auth_sessions
        WHERE ip = ?
        ORDER BY
          CASE WHEN account IS NULL OR account = '' THEN 1 ELSE 0 END,
          online_start DESC
        LIMIT 1
        """,
        (ip,),
    ).fetchone()
    if same_day:
        account = same_day[0] or ""
        return account, "同日IP", "已匹配" if account else "未匹配"
    return "", "未匹配", "未匹配"


def build_rows(tw_rows: list[dict[str, str]], index_path: Path, control: dict[str, Any]) -> tuple[list[dict[str, str]], dict[str, int]]:
    if not index_path.exists():
        raise FileNotFoundError(f"auth index not found: {index_path}")
    status_by_ip = control.get("status_by_ip", {})
    conn = sqlite3.connect(index_path)
    output: list[dict[str, str]] = []
    counters: dict[str, int] = defaultdict(int)
    try:
        for item in tw_rows:
            account, time_status, account_status = choose_auth_match(conn, item["ip"], item["time"])
            control_status = status_by_ip.get(item["ip"], "核验失败" if status_by_ip else "未核验")
            note_parts = []
            if time_status == "同日IP":
                note_parts.append("认证时间未覆盖翻墙时间，仅作辅助")
            if account_status == "未匹配":
                note_parts.append("认证日志未提供可用学号/账号")
            output.append(
                {
                    "学号/账号": account,
                    "翻墙时间": item["time"],
                    "内网IP": item["ip"],
                    "翻墙协议/类型": item["protocol"],
                    "访问IP/对象": item["target"] if not item["object"] else f"{item['target']} {item['object']}",
                    "身份时间匹配": time_status,
                    "学号匹配": account_status,
                    "备注": "；".join(note_parts),
                }
            )
            counters[f"identity_time_{time_status}"] += 1
            counters[f"account_{account_status}"] += 1
            counters[f"control_{control_status}"] += 1
    finally:
        conn.close()
    return output, dict(counters)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    day = day_from_arg(args.date)
    start = parse_time(args.start, day, dt.time.min)
    end = parse_time(args.end, day, dt.time.max.replace(microsecond=0))
    tw_rows, tw_files, duplicate_tw_rows = iter_tw_rows(Path(args.sftp_root), day, start, end)
    control = load_control_status(Path(args.control_json))
    rows, counters = build_rows(tw_rows, auth_index_path(args, day), control)
    write_csv(Path(args.out), rows)

    summary = {
        "date": day.isoformat(),
        "start": start.strftime("%Y-%m-%d %H:%M:%S"),
        "end": end.strftime("%Y-%m-%d %H:%M:%S"),
        "tw_files_checked": tw_files,
        "tw_records": len(tw_rows),
        "duplicate_tw_records_removed": duplicate_tw_rows,
        "unique_internal_ips": len({row["ip"] for row in tw_rows}),
        "output_rows": len(rows),
        "counters": counters,
        "control_json": str(args.control_json),
        "control_load_error": control.get("load_error", ""),
    }
    if args.summary:
        summary_path = Path(args.summary)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2 if args.pretty else None), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
