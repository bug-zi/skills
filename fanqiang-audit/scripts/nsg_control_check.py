#!/usr/bin/env python3
"""
Read-only SecGate 3600 control-object check.

The script logs in, reads only target address objects, checks candidate IP
membership, and exits. It does not read the full firewall snapshot and never
writes configuration.
"""

from __future__ import annotations

import argparse
import datetime as dt
import http.cookiejar
import ipaddress
import json
import pathlib
import ssl
import sys
import time
import urllib.parse
import urllib.request
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "connection.local.json"
BUILTIN_NSG_FIREWALL = {
    "base_url": "https://172.16.15.6:8080",
    "doops_target": "zy",
    "insecure_tls": True,
    "password": "",
    "username": "sysapi",
}
DEFAULT_OBJECTS = ["翻墙禁止上网", "翻墙风险IP", "翻墙风险域名"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only check for SecGate 3600 proxy/VPN control objects.")
    parser.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    parser.add_argument("--base-url")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--insecure", action="store_true")
    parser.add_argument("--ips-file", type=pathlib.Path, required=True)
    parser.add_argument("--objects", nargs="*", default=DEFAULT_OBJECTS)
    parser.add_argument("--page-size", type=int, default=20)
    parser.add_argument("--tries", type=int, default=3)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def load_config(path: pathlib.Path) -> dict[str, Any]:
    cfg = dict(BUILTIN_NSG_FIREWALL)
    if path.exists():
        cfg.update(json.loads(path.read_text(encoding="utf-8")).get("nsg_firewall", {}))
    return cfg


def make_opener(insecure_tls: bool):
    context = ssl._create_unverified_context() if insecure_tls else ssl.create_default_context()
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookies),
        urllib.request.HTTPSHandler(context=context),
    )
    return opener, cookies


def add_cookie(cookie_jar: http.cookiejar.CookieJar, url: str, name: str, value: str) -> None:
    parsed = urllib.parse.urlparse(url)
    cookie_jar.set_cookie(
        http.cookiejar.Cookie(
            version=0,
            name=name,
            value=value,
            port=None,
            port_specified=False,
            domain=parsed.hostname or "",
            domain_specified=False,
            domain_initial_dot=False,
            path="/",
            path_specified=True,
            secure=parsed.scheme == "https",
            expires=None,
            discard=True,
            comment=None,
            comment_url=None,
            rest={},
            rfc2109=False,
        )
    )


def post_json(opener, url: str, body: Any, timeout: int = 20, tries: int = 3) -> Any:
    payload = json.dumps(body).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json", "Accept": "application/json", "Connection": "close"},
                method="POST",
            )
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
                return json.loads(raw) if raw else {}
        except Exception as exc:
            last_error = exc
            if attempt + 1 < tries:
                time.sleep(1)
    raise RuntimeError(str(last_error))


def rest_call(opener, base_url: str, module: str, function: str, body: dict[str, Any], page_index: int, page_size: int, tries: int) -> Any:
    request_body = [
        {
            "head": {
                "module": module,
                "function": function,
                "page_index": page_index,
                "page_size": page_size,
            },
            "body": body,
        }
    ]
    return post_json(opener, base_url.rstrip("/") + "/v1.0/rest/", request_body, tries=tries)


def extract_records(data: Any) -> list[dict[str, Any]]:
    payload = data.get("data") if isinstance(data, dict) else None
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        records: list[dict[str, Any]] = []
        for value in payload.values():
            if isinstance(value, list):
                records.extend(item for item in value if isinstance(item, dict))
        return records
    return []


def total_from(data: Any) -> int:
    head = data.get("head") if isinstance(data, dict) else {}
    total = head.get("total")
    if isinstance(total, int):
        return total
    if isinstance(total, str) and total.isdigit():
        return int(total)
    return -1


def head_ok(data: Any) -> bool:
    head = data.get("head", {}) if isinstance(data, dict) else {}
    return head.get("error_code") in (0, "0")


def read_addr_objects(opener, base_url: str, page_size: int, tries: int) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    first = rest_call(
        opener,
        base_url,
        "obj_address",
        "get_obj_addr_list",
        {"obj_addr": [{"is_detail": False}]},
        1,
        page_size,
        tries,
    )
    if not head_ok(first):
        return [], [{"stage": "get_obj_addr_list", "head": first.get("head") if isinstance(first, dict) else first}]
    records = extract_records(first)
    total = total_from(first)
    page_count = ((total + page_size - 1) // page_size) if total > page_size else 1
    for page in range(2, page_count + 1):
        data = rest_call(
            opener,
            base_url,
            "obj_address",
            "get_obj_addr_list",
            {"obj_addr": [{"is_detail": False}]},
            page,
            page_size,
            tries,
        )
        if head_ok(data):
            records.extend(extract_records(data))
        else:
            errors.append({"stage": f"get_obj_addr_list page {page}", "head": data.get("head") if isinstance(data, dict) else data})
    return records, errors


def read_ips(path: pathlib.Path) -> list[str]:
    ips: list[str] = []
    for raw in path.read_text(encoding="utf-8").replace(",", "\n").splitlines():
        value = raw.strip()
        if not value:
            continue
        parsed = ipaddress.ip_address(value)
        if parsed.version == 4:
            ips.append(str(parsed))
    return sorted(dict.fromkeys(ips), key=lambda item: tuple(int(part) for part in item.split(".")))


def collect_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        result: list[str] = []
        for item in value.values():
            result.extend(collect_values(item))
        return result
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(collect_values(item))
        return result
    if value is None:
        return []
    return [str(value)]


def object_contains_ip(record: dict[str, Any], ip: str) -> bool:
    return ip in set(collect_values(record))


def main() -> int:
    args = parse_args()
    cfg = load_config(args.config)
    if args.base_url:
        cfg["base_url"] = args.base_url
    if args.username:
        cfg["username"] = args.username
    if args.password:
        cfg["password"] = args.password
    insecure = args.insecure or bool(cfg.get("insecure_tls", False))
    base_url = str(cfg["base_url"]).rstrip("/")
    username = str(cfg["username"])
    password = str(cfg["password"])
    candidates = read_ips(args.ips_file)

    opener, cookies = make_opener(insecure)
    report: dict[str, Any] = {
        "checked_at": dt.datetime.now().isoformat(timespec="seconds"),
        "base_url": base_url,
        "objects": args.objects,
        "candidate_count": len(candidates),
        "status_by_ip": {ip: "核验失败" for ip in candidates},
        "object_results": {},
        "errors": [],
        "readonly": True,
    }
    try:
        login = post_json(opener, base_url + "/v1.0/login", {"username": username, "password": password}, tries=args.tries)
        token = login.get("result", {}).get("token") if isinstance(login, dict) else None
        if not token:
            report["errors"].append({"stage": "login", "message": "login failed", "response": login})
        else:
            add_cookie(cookies, base_url + "/v1.0/rest/", "token", token)
            records, errors = read_addr_objects(opener, base_url, args.page_size, args.tries)
            report["errors"].extend(errors)
            if errors and not records:
                report["object_results"] = {
                    name: {"exists": None, "status": "核验失败"} for name in args.objects
                }
            else:
                by_name = {str(item.get("name")): item for item in records if item.get("name")}
                for name in args.objects:
                    record = by_name.get(name)
                    if not record:
                        report["object_results"][name] = {"exists": False}
                        continue
                    members = sorted({value for value in collect_values(record) if value.count(".") == 3})
                    matched = [ip for ip in candidates if object_contains_ip(record, ip)]
                    report["object_results"][name] = {
                        "exists": True,
                        "matched_ips": matched,
                        "matched_count": len(matched),
                        "member_like_values_count": len(members),
                    }
                for ip in candidates:
                    if any(ip in item.get("matched_ips", []) for item in report["object_results"].values()):
                        report["status_by_ip"][ip] = "已管控"
                    elif any(item.get("exists") for item in report["object_results"].values()):
                        report["status_by_ip"][ip] = "未管控"
                    elif report["object_results"]:
                        report["status_by_ip"][ip] = "对象不存在"
    finally:
        try:
            post_json(opener, base_url + "/v1.0/out", {"username": username}, tries=1)
        except Exception:
            pass

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0 if not report["errors"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
