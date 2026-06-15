#!/usr/bin/env python3
"""
Build a lightweight SQLite index for 172.16.15.20 authentication logs.

The index is derived data for fanqiang audits. It stores parsed identity/session
fields and short samples only; it does not copy large raw logs.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable


DEFAULT_LOG_ROOT = Path("/proc/1/root/raid5/syslog-remote/172.16.15.20")
DEFAULT_OUT_DIR = Path("/tmp/fanqiang_indexes")
DATETIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}")
ACCOUNT_IN_PATH_RE = re.compile(r"/第三方用户/([^/\s]+)")

IP_FIELDS = ("client_ip", "user_ip", "ip", "src_ip", "source_ip")
MAC_FIELDS = ("mac", "user_mac", "client_mac", "source_mac")
ACCOUNT_FIELDS = ("account", "user_id", "userid", "login_name", "username", "user_name", "uid")
NAME_FIELDS = ("name", "realname", "real_name", "display_name", "姓名", "用户", "认证用户")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build daily SQLite index from 172.16.15.20 authentication logs.")
    parser.add_argument("--date", required=True, help="Audit date, format YYYY-MM-DD.")
    parser.add_argument("--log-root", default=str(DEFAULT_LOG_ROOT), help="Directory containing 172.16.15.20 logs.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Directory for generated index files.")
    parser.add_argument("--output", help="Explicit SQLite output path.")
    parser.add_argument("--force", action="store_true", help="Rebuild even if the output index already exists.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON summary.")
    return parser.parse_args()


def parse_day(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open("r", encoding="utf-8", errors="replace")


def discover_auth_logs(log_root: Path) -> list[Path]:
    if not log_root.exists():
        raise FileNotFoundError(f"log root does not exist: {log_root}")
    files = [p for p in log_root.rglob("*authlog*.log*") if p.is_file()]
    return sorted(files, key=lambda p: str(p))


def iter_json_payloads(path: Path) -> Iterable[dict[str, Any]]:
    with open_text(path) as handle:
        for line in handle:
            start = line.find("{")
            if start < 0:
                continue
            try:
                payload = json.loads(line[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def iter_auth_items(payload: dict[str, Any]) -> Iterable[dict[str, Any]]:
    authlog = payload.get("authlog")
    if isinstance(authlog, list):
        for item in authlog:
            if isinstance(item, dict):
                yield item
    elif isinstance(authlog, dict):
        yield authlog


def first_value(item: dict[str, Any], fields: tuple[str, ...]) -> str:
    for field in fields:
        value = item.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def parse_datetimes(*values: Any) -> list[dt.datetime]:
    found: list[dt.datetime] = []
    for value in values:
        if value is None:
            continue
        for match in DATETIME_RE.findall(str(value)):
            normalized = match.replace("T", " ")
            try:
                found.append(dt.datetime.strptime(normalized, "%Y-%m-%d %H:%M:%S"))
            except ValueError:
                continue
    return found


def session_interval(item: dict[str, Any]) -> tuple[dt.datetime | None, dt.datetime | None]:
    times = parse_datetimes(item.get("tstamp"), item.get("create_time"), item.get("time"), item.get("timestamp"))
    if not times:
        return None, None
    return min(times), max(times)


def overlaps_day(start: dt.datetime | None, end: dt.datetime | None, day: dt.date) -> bool:
    if start is None:
        return False
    day_start = dt.datetime.combine(day, dt.time.min)
    day_end = dt.datetime.combine(day, dt.time.max)
    actual_end = end or start
    return start <= day_end and actual_end >= day_start


def extract_account(item: dict[str, Any]) -> str:
    explicit = first_value(item, ACCOUNT_FIELDS)
    if explicit:
        return explicit
    for field in ("fullpath", "path", "group_path"):
        value = item.get(field)
        if not value:
            continue
        match = ACCOUNT_IN_PATH_RE.search(str(value))
        if match:
            return match.group(1)
    return ""


def normalize_mac(value: str) -> str:
    return value.strip().lower().replace("-", ":")


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            ip TEXT NOT NULL,
            mac TEXT,
            account TEXT,
            user TEXT,
            name TEXT,
            online_start TEXT,
            online_end TEXT,
            first_seen TEXT,
            last_seen TEXT,
            source_file TEXT NOT NULL,
            sample TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_auth_sessions_date_ip ON auth_sessions(date, ip);
        CREATE INDEX IF NOT EXISTS idx_auth_sessions_ip_interval ON auth_sessions(ip, online_start, online_end);
        CREATE INDEX IF NOT EXISTS idx_auth_sessions_account ON auth_sessions(account);
        CREATE INDEX IF NOT EXISTS idx_auth_sessions_mac ON auth_sessions(mac);
        """
    )


def build_index(day: dt.date, log_root: Path, output: Path, force: bool) -> dict[str, Any]:
    if output.exists() and not force:
        return {
            "status": "exists",
            "date": day.isoformat(),
            "log_root": str(log_root),
            "output": str(output),
            "message": "index already exists; use --force to rebuild",
        }

    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    files = discover_auth_logs(log_root)
    conn = sqlite3.connect(output)
    create_schema(conn)

    lines_scanned = 0
    inserted = 0
    unique_ips: set[str] = set()
    unique_accounts: set[str] = set()
    zero_mac_records = 0
    seen: set[tuple[str, str, str, str, str, str]] = set()

    with conn:
        conn.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)", ("date", day.isoformat()))
        conn.execute("INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)", ("log_root", str(log_root)))
        conn.execute(
            "INSERT OR REPLACE INTO metadata(key, value) VALUES(?, ?)",
            ("generated_at", dt.datetime.now().isoformat(timespec="seconds")),
        )

        for path in files:
            with open_text(path) as handle:
                for line in handle:
                    lines_scanned += 1
                    start = line.find("{")
                    if start < 0:
                        continue
                    try:
                        payload = json.loads(line[start:])
                    except json.JSONDecodeError:
                        continue
                    for item in iter_auth_items(payload):
                        ip = first_value(item, IP_FIELDS)
                        if not ip:
                            continue
                        online_start, online_end = session_interval(item)
                        if not overlaps_day(online_start, online_end, day):
                            continue

                        mac = normalize_mac(first_value(item, MAC_FIELDS))
                        account = extract_account(item)
                        user = first_value(item, ACCOUNT_FIELDS)
                        name = first_value(item, NAME_FIELDS)
                        start_text = online_start.isoformat(sep=" ") if online_start else ""
                        end_text = online_end.isoformat(sep=" ") if online_end else start_text
                        dedupe_key = (ip, mac, account, start_text, end_text, str(path))
                        if dedupe_key in seen:
                            continue
                        seen.add(dedupe_key)

                        if not mac or mac in {"00:00:00:00:00:00", "0:0:0:0:0:0"}:
                            zero_mac_records += 1
                        unique_ips.add(ip)
                        if account:
                            unique_accounts.add(account)

                        sample = json.dumps(item, ensure_ascii=False, separators=(",", ":"))[:240]
                        conn.execute(
                            """
                            INSERT INTO auth_sessions (
                                date, ip, mac, account, user, name, online_start, online_end,
                                first_seen, last_seen, source_file, sample
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                day.isoformat(),
                                ip,
                                mac,
                                account,
                                user,
                                name,
                                start_text,
                                end_text,
                                start_text,
                                end_text,
                                str(path),
                                sample,
                            ),
                        )
                        inserted += 1

    conn.close()
    return {
        "status": "built",
        "date": day.isoformat(),
        "log_root": str(log_root),
        "output": str(output),
        "files_scanned": len(files),
        "lines_scanned": lines_scanned,
        "records_inserted": inserted,
        "unique_ips": len(unique_ips),
        "unique_accounts": len(unique_accounts),
        "zero_mac_records": zero_mac_records,
    }


def main() -> int:
    args = parse_args()
    day = parse_day(args.date)
    output = Path(args.output) if args.output else Path(args.out_dir) / f"auth_index_{day:%Y%m%d}.sqlite"
    summary = build_index(day, Path(args.log_root), output, args.force)
    print(json.dumps(summary, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
