#!/usr/bin/env python3
import argparse
import datetime as dt
import http.cookiejar
import json
import pathlib
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "connection.local.json"
DEFAULT_OUT_DIR = ROOT / "snapshots"
BUILTIN_NSG_FIREWALL = {'base_url': 'https://172.16.15.6:8080',
 'doops_cwd': '/Users/wwyz/Documents/网络安全智能体',
 'doops_target': 'zy',
 'insecure_tls': True,
 'password': '',
 'username': 'sysapi'}

READ_TARGETS = [
    {
        "key": "system_info",
        "module": "dashboard",
        "function": "get_system_info",
        "body": {},
        "paginate": False,
    },
    {
        "key": "system_resource",
        "module": "dashboard",
        "function": "get_system_resource",
        "body": {},
        "paginate": False,
    },
    {
        "key": "security_policies",
        "module": "sec_policy",
        "function": "get_sec_policy",
        "body": {"sec_policy": [{"name": "", "is_detail": True}]},
        "paginate": True,
    },
    {
        "key": "address_objects",
        "module": "obj_address",
        "function": "get_obj_addr_list",
        "body": {"obj_addr": [{"is_detail": False}]},
        "paginate": True,
    },
    {
        "key": "address_object_groups",
        "module": "obj_address",
        "function": "get_obj_addr_group",
        "body": {"obj_addr": [{"is_detail": False}]},
        "paginate": True,
    },
    {
        "key": "address_blacklist",
        "module": "addr_blacklist",
        "function": "get_blacklist_config",
        "body": {"addr_blacklist_cp": {"search_key": ""}},
        "paginate": True,
    },
    {
        "key": "batch_domain_blacklist",
        "module": "addr_blacklist",
        "function": "show_batch_domain_blacklist",
        "body": {"addr_blacklist_cp": {"search_key": "", "type": "hit_num"}},
        "paginate": True,
    },
    {
        "key": "batch_domain_commit_status",
        "module": "addr_blacklist",
        "function": "get_batch_domain_blacklist_commit_status",
        "body": {},
        "paginate": False,
    },
    {
        "key": "syslog_server_config",
        "module": "syslog",
        "function": "get_syslog_server_config_all",
        "body": {},
        "paginate": False,
    },
]


def load_config(path):
    cfg = dict(BUILTIN_NSG_FIREWALL)
    if path.exists():
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        cfg.update(data.get("nsg_firewall", {}))
    missing = [key for key in ("base_url", "username", "password") if not cfg.get(key)]
    if missing:
        raise SystemExit(f"Missing config fields: {', '.join(missing)}. Add them to the built-in defaults or config file.")
    return cfg


def add_cookie(cookie_jar, url, name, value):
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


def make_opener(insecure_tls):
    context = ssl._create_unverified_context() if insecure_tls else ssl.create_default_context()
    cookies = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookies),
        urllib.request.HTTPSHandler(context=context),
    )
    return opener, cookies


def post_json(opener, url, body, timeout=20, tries=3):
    payload = json.dumps(body).encode("utf-8")
    last_error = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Connection": "close",
                },
                method="POST",
            )
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", "replace")
                return json.loads(raw) if raw else None
        except Exception as exc:
            last_error = exc
            time.sleep(2)
    raise last_error


def rest_call(opener, base_url, target, page_index=1, page_size=20):
    body = [
        {
            "head": {
                "module": target["module"],
                "function": target["function"],
                "page_index": page_index,
                "page_size": page_size,
            },
            "body": target["body"],
        }
    ]
    return post_json(opener, base_url.rstrip("/") + "/v1.0/rest/", body)


def extract_records(data):
    payload = data.get("data") if isinstance(data, dict) else None
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        records = []
        for value in payload.values():
            if isinstance(value, list):
                records.extend(value)
        return records
    return []


def total_from(data):
    head = data.get("head") if isinstance(data, dict) else {}
    total = head.get("total")
    if isinstance(total, str) and total.lstrip("-").isdigit():
        return int(total)
    if isinstance(total, int):
        return total
    return -1


def fetch_target(opener, base_url, target):
    first = rest_call(opener, base_url, target, page_index=1, page_size=20)
    head = first.get("head") if isinstance(first, dict) else {}
    if head.get("error_code") not in (0, "0"):
        return {"ok": False, "head": head, "raw": first}
    if not target.get("paginate"):
        return {"ok": True, "head": head, "data": first.get("data")}

    records = extract_records(first)
    total = total_from(first)
    page_count = ((total + 19) // 20) if total > 20 else 1
    for page in range(2, page_count + 1):
        data = rest_call(opener, base_url, target, page_index=page, page_size=20)
        records.extend(extract_records(data))
    return {"ok": True, "head": head, "total": total, "data": records}


def build_indexes(snapshot):
    indexes = {}
    for key in ("security_policies", "address_objects", "address_object_groups"):
        section = snapshot["sections"].get(key, {})
        if not section.get("ok") or not isinstance(section.get("data"), list):
            continue
        indexes[key + "_by_name"] = {
            item.get("name"): item
            for item in section["data"]
            if isinstance(item, dict) and item.get("name")
        }
    return indexes


def write_snapshot(snapshot, out_dir, pretty):
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"nsg_snapshot_{timestamp}.json"
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, ensure_ascii=False, indent=2 if pretty else None)
    return out_path


def summarize_snapshot(snapshot):
    return {
        key: {
            "ok": value.get("ok"),
            "total": value.get("total", total_from(value.get("raw", {}))),
            "error": (value.get("head") or {}).get("error_string"),
        }
        for key, value in snapshot["sections"].items()
    }


def snapshot_direct(cfg, out_dir, pretty):
    base_url = cfg["base_url"].rstrip("/")
    opener, cookies = make_opener(bool(cfg.get("insecure_tls", True)))

    login = post_json(
        opener,
        base_url + "/v1.0/login",
        {"username": cfg["username"], "password": cfg["password"]},
        tries=6,
    )
    token = login.get("result", {}).get("token") if isinstance(login, dict) else None
    if not token:
        raise RuntimeError(f"Login failed: {login}")
    add_cookie(cookies, base_url + "/v1.0/rest/", "token", token)

    snapshot = {
        "snapshot_at": dt.datetime.now().isoformat(timespec="seconds"),
        "base_url": base_url,
        "transport": "direct",
        "sections": {},
    }
    try:
        for target in READ_TARGETS:
            snapshot["sections"][target["key"]] = fetch_target(opener, base_url, target)
        snapshot["indexes"] = build_indexes(snapshot)
        out_path = write_snapshot(snapshot, out_dir, pretty)
    finally:
        try:
            post_json(opener, base_url + "/v1.0/out", {"username": cfg["username"]}, tries=1)
        except Exception:
            pass

    return {"snapshot": str(out_path), "transport": "direct", "summary": summarize_snapshot(snapshot)}


def run_command(cmd, cwd=None, **kwargs):
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=cwd, **kwargs)


def extract_json(text):
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError(f"No JSON object found in doops output:\n{text}")
    return json.loads(text[start : end + 1])


def snapshot_doops(cfg, out_dir, pretty, direct_error=None):
    target = cfg.get("doops_target") or "zy"
    doops_cwd = cfg.get("doops_cwd")
    session = "nsg_snapshot_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_root = pathlib.Path(tempfile.mkdtemp(prefix="nsg-snapshot-doops-"))
    remote_created = False
    try:
        shutil.copy2(pathlib.Path(__file__).resolve(), temp_root / "nsg_snapshot.py")
        (temp_root / "connection.local.json").write_text(
            json.dumps({"nsg_firewall": cfg}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        pushed = run_command(["doops", "-session", session, "push", "--target", target, "--src", str(temp_root)], cwd=doops_cwd)
        if pushed.returncode != 0:
            raise RuntimeError(f"doops push failed:\n{pushed.stdout}")
        remote_created = True

        pretty_flag = " --pretty" if pretty else ""
        remote_cmd = (
            "cd /root/ws/{session} && "
            "python3 nsg_snapshot.py --config connection.local.json --out-dir snapshots --transport direct"
            "{pretty_flag}"
        ).format(session=session, pretty_flag=pretty_flag)
        executed = run_command(["doops", "-session", session, "exec", "--target", target, "--cmd", remote_cmd], cwd=doops_cwd, timeout=240)
        if executed.returncode != 0:
            raise RuntimeError(f"doops exec failed:\n{executed.stdout}")

        report = extract_json(executed.stdout)
        remote_snapshot = report.get("snapshot")
        if remote_snapshot:
            remote_path = remote_snapshot
            if not remote_path.startswith("/"):
                remote_path = f"/root/ws/{session}/{remote_path}"
            read = run_command(
                ["doops", "-session", session, "read", "--target", target, "--path", remote_path],
                cwd=doops_cwd,
                timeout=120,
            )
            if read.returncode != 0:
                raise RuntimeError(f"doops read failed:\n{read.stdout}")
            out_dir.mkdir(parents=True, exist_ok=True)
            local_path = out_dir / pathlib.Path(remote_path).name
            local_path.write_text(read.stdout, encoding="utf-8")
            report["snapshot"] = str(local_path)

        report["transport"] = "doops"
        report["doops"] = {"target": target, "session": session}
        if direct_error:
            report["direct_error"] = direct_error
        return report
    finally:
        if remote_created:
            run_command(["doops", "-session", session, "clean", "--target", target, "--workspace", session], cwd=doops_cwd, timeout=60)
        shutil.rmtree(temp_root, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="Read-only SecGate 3600 snapshot")
    parser.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out-dir", type=pathlib.Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument(
        "--transport",
        choices=("auto", "direct", "doops"),
        default="doops",
        help="connection transport; doops is the local default; auto tries direct first and falls back to doops",
    )
    args = parser.parse_args()

    cfg = load_config(args.config)
    report = None
    direct_error = None
    if args.transport in ("auto", "direct"):
        try:
            report = snapshot_direct(cfg, args.out_dir, args.pretty)
        except Exception as exc:
            direct_error = str(exc)
            if args.transport == "direct":
                raise SystemExit(direct_error)
    if report is None:
        report = snapshot_doops(cfg, args.out_dir, args.pretty, direct_error=direct_error)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
