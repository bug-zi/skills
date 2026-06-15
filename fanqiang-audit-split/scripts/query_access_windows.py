#!/usr/bin/env python3
"""
Query compact access context from 172.16.15.20 logs by IP plus tw_act time windows.

This script is intended to run on the log host or DOOPS target. It reads only the
candidate CSV/JSON and the existing access logs, then writes compact derived
results. It does not copy raw logs.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import json
import os
import re
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any


DEFAULT_LOG_ROOT = Path("/proc/1/root/raid5/syslog-remote/172.16.15.20")
DATETIME_RE = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}")
LOG_FAMILY_PATTERNS = {
    "proxy_identify": "*proxy_identify*.log*",
    "ssl_log": "*ssl_log*.log*",
    "web": "*web*.log*",
    "app_conn": "*app_conn*.log*",
    "app": '{"app".log*',
}
IP_FIELDS = ("client_ip", "user_ip", "ip", "src_ip", "source_ip")
OBJECT_FIELDS = ("ssl_server_name", "url", "domain", "host", "server_name")
APP_FIELDS = ("app_mark", "appname", "app_name", "policy_name", "uri_category_id")
DST_IP_FIELDS = ("server_ip", "dst_ip", "dest_ip", "destination_ip")
DST_PORT_FIELDS = ("dst_port", "dest_port", "port", "server_port")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query 172.16.15.20 access logs by candidate IP and tw_act windows.")
    parser.add_argument("--candidates", required=True, type=Path, help="Candidate CSV or JSON from tw_act analysis.")
    parser.add_argument("--log-root", default=str(DEFAULT_LOG_ROOT), help="172.16.15.20 log directory.")
    parser.add_argument("--out", type=Path, help="Optional output JSON path for machine-readable evidence.")
    parser.add_argument("--csv-out", type=Path, help="Output CSV path for human review.")
    parser.add_argument("--window-minutes", type=int, default=10, help="Primary window size on each side of hit time.")
    parser.add_argument("--expand-minutes", type=int, default=30, help="Second window size for unmatched IPs.")
    parser.add_argument("--max-samples", type=int, default=3, help="Evidence sample count per IP.")
    parser.add_argument("--max-top", type=int, default=5, help="Top value count per field.")
    parser.add_argument("--audit-date", help="Audit date YYYY-MM-DD. Defaults to the first candidate event date.")
    parser.add_argument(
        "--families",
        default="proxy_identify,ssl_log,web,app_conn,app",
        help="Comma-separated log families: proxy_identify,ssl_log,web,app_conn,app.",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser.parse_args()


def parse_time(value: Any) -> dt.datetime | None:
    if value is None:
        return None
    match = DATETIME_RE.search(str(value))
    if not match:
        return None
    try:
        return dt.datetime.strptime(match.group(0).replace("T", " "), "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def open_text(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return path.open("r", encoding="utf-8", errors="replace")


def first_value(item: dict[str, Any], fields: tuple[str, ...]) -> str:
    for field in fields:
        value = item.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def row_value(row: dict[str, Any], *names: str) -> str:
    normalized = {str(key).lstrip("\ufeff").strip(): value for key, value in row.items()}
    for name in names:
        value = normalized.get(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def load_candidate_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"candidate file does not exist: {path}")

    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("candidates", data if isinstance(data, list) else [])
    else:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))

    events: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        ip = row_value(row, "内网IP", "ip", "client_ip")
        if not ip:
            continue
        time_candidates = [
            row_value(row, "翻墙时间"),
            row_value(row, "最近命中时间"),
            row_value(row, "最新时间"),
            row_value(row, "首次时间"),
            row_value(row, "time"),
            row_value(row, "event_time"),
        ]
        event_time = None
        for value in time_candidates:
            parsed = parse_time(value)
            if parsed:
                event_time = parsed
                break
        if not event_time:
            continue
        protocol = row_value(row, "翻墙协议/类型", "protocol")
        target = row_value(row, "访问IP/对象", "target")
        account = row_value(row, "学号/账号", "account")
        control_status = row_value(row, "管控情况", "control_status")
        key = (account, event_time.strftime("%Y-%m-%d %H:%M:%S"), ip, protocol, target)
        if key in seen:
            continue
        seen.add(key)
        events.append(
            {
                "event_id": f"E{index:05d}",
                "account": account,
                "ip": ip,
                "event_time": event_time,
                "protocol": protocol,
                "target": target,
                "control_status": control_status,
            }
        )
    return events


def build_event_windows(events: list[dict[str, Any]], minutes: int) -> dict[str, list[dict[str, Any]]]:
    delta = dt.timedelta(minutes=minutes)
    by_ip: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        start = event["event_time"] - delta
        end = event["event_time"] + delta
        item = dict(event)
        item["window_start"] = start
        item["window_end"] = end
        by_ip.setdefault(event["ip"], []).append(item)
    return by_ip


def matching_events(event_time: dt.datetime | None, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if event_time is None:
        return events
    return [event for event in events if event["window_start"] <= event_time <= event["window_end"]]


def infer_audit_date(events: list[dict[str, Any]], explicit: str | None) -> dt.date:
    if explicit:
        return dt.datetime.strptime(explicit, "%Y-%m-%d").date()
    if not events:
        raise ValueError("cannot infer audit date from empty candidate events")
    return min(event["event_time"] for event in events).date()


def likely_contains_day(path: Path, audit_date: dt.date) -> bool:
    mtime_date = dt.datetime.fromtimestamp(os.path.getmtime(path)).date()
    next_date = audit_date + dt.timedelta(days=1)
    name = path.name
    if name.endswith(".log") and mtime_date == audit_date:
        return True
    if name.endswith(".log.1") and mtime_date == next_date:
        return True
    if name.endswith(".gz") and mtime_date == next_date:
        return True
    return False


def discover_logs(log_root: Path, families: list[str], audit_date: dt.date) -> list[Path]:
    if not log_root.exists():
        raise FileNotFoundError(f"log root does not exist: {log_root}")
    files: set[Path] = set()
    for family in families:
        pattern = LOG_FAMILY_PATTERNS.get(family)
        if not pattern:
            raise ValueError(f"unsupported log family: {family}")
        files.update(path for path in log_root.glob(pattern) if path.is_file() and likely_contains_day(path, audit_date))
    return sorted(files, key=lambda path: str(path))


def iter_items(line: str) -> list[tuple[str, dict[str, Any]]]:
    start = line.find("{")
    if start < 0:
        return []
    try:
        payload = json.loads(line[start:])
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict):
        return []
    out: list[tuple[str, dict[str, Any]]] = []
    for source, value in payload.items():
        items = value if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, dict):
                out.append((str(source), item))
    return out


def summarize_counter(counter: Counter[str], limit: int) -> list[dict[str, Any]]:
    return [{"value": key, "count": count} for key, count in counter.most_common(limit) if key]


def behavior_assessment(item: dict[str, Any]) -> str:
    if not item["matched_rows"]:
        return "未命中访问上下文，需复核"

    app_labels = [entry["value"] for entry in item["top_app_labels"]]
    source_names = [entry["value"] for entry in item["source_counts"]]
    haystack = " ".join(app_labels + source_names)

    if "代理隧道" in haystack or "翻墙" in haystack:
        return "访问窗口内命中代理隧道/翻墙软件特征"
    return "访问窗口内有上下文命中，未见额外代理隧道标签"


def scan_access(
    log_root: Path,
    events: list[dict[str, Any]],
    minutes: int,
    max_samples: int,
    max_top: int,
    families: list[str],
    audit_date: dt.date,
) -> dict[str, Any]:
    windows_by_ip = build_event_windows(events, minutes)
    summaries: dict[str, dict[str, Any]] = {}
    for event in events:
        summaries[event["event_id"]] = {
            "event_id": event["event_id"],
            "account": event["account"],
            "event_time": event["event_time"].strftime("%Y-%m-%d %H:%M:%S"),
            "ip": event["ip"],
            "protocol": event["protocol"],
            "target": event["target"],
            "control_status": event["control_status"],
            "window_minutes": minutes,
            "window_start": (event["event_time"] - dt.timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S"),
            "window_end": (event["event_time"] + dt.timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S"),
            "matched_rows": 0,
            "source_counts": Counter(),
            "app_labels": Counter(),
            "objects": Counter(),
            "destinations": Counter(),
            "samples": [],
        }

    log_files = discover_logs(log_root, families, audit_date)
    candidate_lines = 0
    parsed_rows = 0
    file_reports: list[dict[str, Any]] = []

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as ip_handle:
        ip_file = Path(ip_handle.name)
        for ip in sorted(windows_by_ip):
            ip_handle.write(ip + "\n")

    try:
      for path in log_files:
        before_candidate = candidate_lines
        before_parsed = parsed_rows
        try:
            if path.suffix == ".gz":
                gzip_proc = subprocess.Popen(
                    ["gzip", "-cd", str(path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                grep_proc = subprocess.Popen(
                    ["grep", "-F", "-f", str(ip_file)],
                    stdin=gzip_proc.stdout,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                if gzip_proc.stdout:
                    gzip_proc.stdout.close()
            else:
                gzip_proc = None
                grep_proc = subprocess.Popen(
                    ["grep", "-F", "-f", str(ip_file), str(path)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )

            if grep_proc.stdout is None:
                raise RuntimeError("grep stdout unavailable")
            with grep_proc.stdout as handle:
                for line in handle:
                    candidate_lines += 1
                    for source, item in iter_items(line):
                        ip = first_value(item, IP_FIELDS)
                        if ip not in windows_by_ip:
                            continue
                        event_time = parse_time(item.get("tstamp") or item.get("create_time") or item.get("time"))
                        matched_events = matching_events(event_time, windows_by_ip[ip])
                        if not matched_events:
                            continue

                        app_label = first_value(item, APP_FIELDS)
                        access_object = first_value(item, OBJECT_FIELDS)
                        dst_ip = first_value(item, DST_IP_FIELDS)
                        dst_port = first_value(item, DST_PORT_FIELDS)
                        destination = f"{dst_ip}:{dst_port}" if dst_ip and dst_port else dst_ip
                        sample = json.dumps(item, ensure_ascii=False, separators=(",", ":"))[:240]

                        for event in matched_events:
                            summary = summaries[event["event_id"]]
                            summary["matched_rows"] += 1
                            summary["source_counts"][source] += 1
                            if app_label:
                                summary["app_labels"][app_label[:160]] += 1
                            if access_object:
                                summary["objects"][access_object[:200]] += 1
                            if destination:
                                summary["destinations"][destination[:160]] += 1
                            if len(summary["samples"]) < max_samples:
                                summary["samples"].append(sample)
                        parsed_rows += len(matched_events)
            grep_code = grep_proc.wait()
            gzip_code = gzip_proc.wait() if gzip_proc else 0
            file_reports.append(
                {
                    "file": path.name,
                    "candidate_lines": candidate_lines - before_candidate,
                    "matched_rows": parsed_rows - before_parsed,
                    "status": "ok",
                    "grep_returncode": grep_code,
                    "gzip_returncode": gzip_code,
                }
            )
        except Exception as exc:
            file_reports.append(
                {
                    "file": path.name,
                    "candidate_lines": candidate_lines - before_candidate,
                    "matched_rows": parsed_rows - before_parsed,
                    "status": "failed",
                    "error": str(exc),
                }
            )
    finally:
        try:
            ip_file.unlink()
        except OSError:
            pass

    compact: list[dict[str, Any]] = []
    for summary in summaries.values():
        compact.append(
            {
                "event_id": summary["event_id"],
                "account": summary["account"],
                "event_time": summary["event_time"],
                "ip": summary["ip"],
                "protocol": summary["protocol"],
                "target": summary["target"],
                "control_status": summary["control_status"],
                "window_minutes": minutes,
                "window_start": summary["window_start"],
                "window_end": summary["window_end"],
                "matched_rows": summary["matched_rows"],
                "source_counts": summarize_counter(summary["source_counts"], max_top),
                "top_app_labels": summarize_counter(summary["app_labels"], max_top),
                "top_objects": summarize_counter(summary["objects"], max_top),
                "top_destinations": summarize_counter(summary["destinations"], max_top),
                "samples": summary["samples"],
                "status": "命中" if summary["matched_rows"] else "未命中",
            }
        )

    return {
        "window_minutes": minutes,
        "families": families,
        "audit_date": audit_date.isoformat(),
        "candidate_events": len(events),
        "candidate_ips": len(windows_by_ip),
        "log_files": len(log_files),
        "candidate_lines": candidate_lines,
        "matched_rows": parsed_rows,
        "matched_events": sum(1 for item in compact if item["matched_rows"] > 0),
        "unmatched_events": sum(1 for item in compact if item["matched_rows"] == 0),
        "matched_ips": len({item["ip"] for item in compact if item["matched_rows"] > 0}),
        "unmatched_ips": len({item["ip"] for item in compact if item["matched_rows"] == 0}),
        "file_reports": file_reports,
        "access_summaries": sorted(compact, key=lambda item: (item["matched_rows"], item["event_time"], item["ip"]), reverse=True),
    }


def write_csv(path: Path, access_summaries: list[dict[str, Any]]) -> None:
    fields = [
        "事件ID",
        "学号/账号",
        "翻墙时间",
        "内网IP",
        "翻墙协议/类型",
        "访问IP/对象",
        "窗口分钟",
        "访问日志命中数",
        "状态",
        "翻墙行为评估",
        "管控情况",
        "日志来源",
        "应用标签",
        "访问对象",
        "目的IP端口",
        "证据样例",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in access_summaries:
            writer.writerow(
                {
                    "事件ID": item["event_id"],
                    "学号/账号": item["account"],
                    "翻墙时间": item["event_time"],
                    "内网IP": item["ip"],
                    "翻墙协议/类型": item["protocol"],
                    "访问IP/对象": item["target"],
                    "窗口分钟": item["window_minutes"],
                    "访问日志命中数": item["matched_rows"],
                    "状态": item["status"],
                    "翻墙行为评估": behavior_assessment(item),
                    "管控情况": item["control_status"],
                    "日志来源": "; ".join(f"{x['value']}({x['count']})" for x in item["source_counts"]),
                    "应用标签": "; ".join(f"{x['value']}({x['count']})" for x in item["top_app_labels"]),
                    "访问对象": "; ".join(f"{x['value']}({x['count']})" for x in item["top_objects"]),
                    "目的IP端口": "; ".join(f"{x['value']}({x['count']})" for x in item["top_destinations"]),
                    "证据样例": " | ".join(item["samples"]),
                }
            )


def main() -> int:
    args = parse_args()
    if not args.out and not args.csv_out:
        raise SystemExit("at least one of --csv-out or --out is required")
    events = load_candidate_events(args.candidates)
    audit_date = infer_audit_date(events, args.audit_date)
    families = [family.strip() for family in args.families.split(",") if family.strip()]
    primary = scan_access(Path(args.log_root), events, args.window_minutes, args.max_samples, args.max_top, families, audit_date)

    final = dict(primary)
    final["expanded_window_minutes"] = None
    final["expanded_result"] = None

    if primary["unmatched_events"] and args.expand_minutes > args.window_minutes:
        by_event_id = {event["event_id"]: event for event in events}
        unmatched = [
            by_event_id[item["event_id"]]
            for item in primary["access_summaries"]
            if item["matched_rows"] == 0 and item["event_id"] in by_event_id
        ]
        expanded = scan_access(Path(args.log_root), unmatched, args.expand_minutes, args.max_samples, args.max_top, families, audit_date)
        final["expanded_window_minutes"] = args.expand_minutes
        final["expanded_result"] = expanded

        by_event = {item["event_id"]: item for item in primary["access_summaries"]}
        for item in expanded["access_summaries"]:
            if item["matched_rows"] > 0:
                by_event[item["event_id"]] = item
        merged = sorted(by_event.values(), key=lambda item: (item["matched_rows"], item["event_time"], item["ip"]), reverse=True)
        final["access_summaries"] = merged
        final["matched_events"] = sum(1 for item in merged if item["matched_rows"] > 0)
        final["unmatched_events"] = sum(1 for item in merged if item["matched_rows"] == 0)
        final["matched_ips"] = len({item["ip"] for item in merged if item["matched_rows"] > 0})
        final["unmatched_ips"] = len({item["ip"] for item in merged if item["matched_rows"] == 0})

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(final, ensure_ascii=False, indent=2 if args.pretty else None), encoding="utf-8")
    if args.csv_out:
        write_csv(args.csv_out, final["access_summaries"])

    print(
        json.dumps(
            {
                "output": str(args.out) if args.out else None,
                "csv_output": str(args.csv_out) if args.csv_out else None,
                "candidate_events": final["candidate_events"],
                "candidate_ips": final["candidate_ips"],
                "matched_events": final["matched_events"],
                "unmatched_events": final["unmatched_events"],
                "matched_ips": final["matched_ips"],
                "unmatched_ips": final["unmatched_ips"],
                "matched_rows": final["matched_rows"],
                "expanded_window_minutes": final["expanded_window_minutes"],
            },
            ensure_ascii=False,
            indent=2 if args.pretty else None,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
