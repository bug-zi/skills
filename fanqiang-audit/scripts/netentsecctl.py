#!/usr/bin/env python3
import argparse
import csv
import datetime as dt
import http.cookiejar
import json
import pathlib
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request


def make_context(insecure: bool) -> ssl.SSLContext:
    if insecure:
        return ssl._create_unverified_context()
    return ssl.create_default_context()


NSG_LOGIN_PATH = "/v1.0/login"
NSG_REST_PATH = "/v1.0/rest/"
NSG_LOGOUT_PATH = "/v1.0/out"
DEFAULT_CONFIG = pathlib.Path(__file__).resolve().parents[1] / "config" / "connection.local.json"
DEFAULT_MATRIX = pathlib.Path(__file__).resolve().parents[1] / "references" / "api-coverage-matrix.csv"
BUILTIN_NSG_FIREWALL = {'base_url': 'https://172.16.15.6:8080',
 'doops_cwd': '/Users/wwyz/Documents/网络安全智能体',
 'doops_target': 'zy',
 'insecure_tls': True,
 'password': '',
 'username': 'sysapi'}

def http_json(url: str, method: str, body=None, headers=None, insecure=False, timeout=15, cookies=None):
    ctx = make_context(insecure)
    payload = None
    final_headers = {"Content-Type": "application/json"}
    if headers:
        final_headers.update(headers)
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers=final_headers, method=method.upper())
    if cookies is None:
        opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))
    else:
        opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(cookies),
            urllib.request.HTTPSHandler(context=ctx),
        )
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = raw
        return resp, parsed, cookies


def nsg_login(base_url: str, username: str, password: str, insecure=False):
    url = base_url.rstrip("/") + NSG_LOGIN_PATH
    cookies = http.cookiejar.CookieJar()
    _resp, data, cookies = http_json(
        url,
        "POST",
        body={"username": username, "password": password},
        headers={"Accept": "application/json"},
        insecure=insecure,
        cookies=cookies,
    )
    if isinstance(data, dict) and data.get("success") is True:
        token = data.get("result", {}).get("token")
        if token:
            add_cookie(cookies, url, "token", token)
            return {"token": token, "raw": data, "cookies": cookies}
    raise RuntimeError(f"nsg login failed: {data}")


def add_cookie(cookie_jar, url: str, name: str, value: str):
    parsed = urllib.parse.urlparse(url)
    cookie = http.cookiejar.Cookie(
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
    cookie_jar.set_cookie(cookie)


def nsg_rest(base_url: str, token: str, body, insecure=False, phpsessid=None):
    url = base_url.rstrip("/") + NSG_REST_PATH
    cookies = http.cookiejar.CookieJar()
    if phpsessid:
        add_cookie(cookies, url, "PHPSESSID", phpsessid)
    add_cookie(cookies, url, "token", token)
    resp, data, _cookies = http_json(
        url,
        "POST",
        body=body,
        headers={"Accept": "application/json"},
        cookies=cookies,
        insecure=insecure,
    )
    return {
        "status": resp.status,
        "headers": dict(resp.getheaders()),
        "data": data,
    }


def nsg_call(base_url: str, token: str, module: str, function: str, body=None, page_index=1, page_size=20, insecure=False, phpsessid=None):
    head = {
        "module": module,
        "function": function,
        "page_index": page_index,
        "page_size": page_size,
    }
    payload = [{"head": head, "body": body or {}}]
    return nsg_rest(base_url, token, payload, insecure=insecure, phpsessid=phpsessid)


def load_nsg_config(path):
    cfg = dict(BUILTIN_NSG_FIREWALL)
    if path and pathlib.Path(path).exists():
        cfg.update(json.loads(pathlib.Path(path).read_text(encoding="utf-8")).get("nsg_firewall", {}))
    return cfg


def nsg_rest_session(base_url: str, cookies, body, insecure=False, timeout=25):
    url = base_url.rstrip("/") + NSG_REST_PATH
    resp, data, _cookies = http_json(
        url,
        "POST",
        body=body,
        headers={"Accept": "application/json", "Connection": "close"},
        cookies=cookies,
        insecure=insecure,
        timeout=timeout,
    )
    return {"status": resp.status, "headers": dict(resp.getheaders()), "data": data}


def nsg_session_call(base_url, cookies, module, function, body=None, page_index=1, page_size=20, insecure=False):
    payload = [
        {
            "head": {
                "module": module,
                "function": function,
                "page_index": page_index,
                "page_size": page_size,
            },
            "body": body or {},
        }
    ]
    return nsg_rest_session(base_url, cookies, payload, insecure=insecure)


def nsg_login_session(base_url: str, username: str, password: str, insecure=False):
    result = nsg_login(base_url, username, password, insecure=insecure)
    return result["cookies"]


def nsg_logout_session(base_url: str, username: str, cookies, insecure=False):
    try:
        nsg_rest_session(base_url, cookies, {"username": username}, insecure=insecure)
    except Exception:
        pass


def ensure_ok(result, label):
    data = result.get("data")
    head = data.get("head", {}) if isinstance(data, dict) else {}
    if head.get("error_code") not in (0, "0"):
        raise RuntimeError(f"{label} failed: {head or data}")
    return data


def iter_nsg_address_objects(base_url, cookies, insecure=False):
    first = nsg_session_call(
        base_url,
        cookies,
        "obj_address",
        "get_obj_addr_list",
        {"obj_addr": [{"is_detail": False}]},
        page_index=1,
        page_size=20,
        insecure=insecure,
    )
    data = ensure_ok(first, "get_obj_addr_list")
    total = int(data.get("head", {}).get("total") or 0)
    page_count = (total + 19) // 20 if total > 0 else 1
    pages = [data]
    for page_index in range(2, page_count + 1):
        page = nsg_session_call(
            base_url,
            cookies,
            "obj_address",
            "get_obj_addr_list",
            {"obj_addr": [{"is_detail": False}]},
            page_index=page_index,
            page_size=20,
            insecure=insecure,
        )
        pages.append(ensure_ok(page, "get_obj_addr_list"))
    for page in pages:
        for item in page.get("data") or []:
            yield item


def read_nsg_address_object(base_url, cookies, name, insecure=False):
    matches = [item for item in iter_nsg_address_objects(base_url, cookies, insecure=insecure) if item.get("name") == name]
    if not matches:
        raise RuntimeError(f"missing address object: {name}")
    if len(matches) > 1:
        raise RuntimeError(f"duplicate address object: {name}")
    return matches[0]


def collect_strings(value):
    if isinstance(value, dict):
        result = []
        for item in value.values():
            result.extend(collect_strings(item))
        return result
    if isinstance(value, list):
        result = []
        for item in value:
            result.extend(collect_strings(item))
        return result
    if value is None:
        return []
    return [str(value)]


def read_nsg_policy(base_url, cookies, name, insecure=False):
    result = nsg_session_call(
        base_url,
        cookies,
        "sec_policy",
        "get_sec_policy",
        {"sec_policy": [{"name": "", "is_detail": True}]},
        page_index=1,
        page_size=20,
        insecure=insecure,
    )
    data = ensure_ok(result, "get_sec_policy")
    matches = [item for item in data.get("data") or [] if item.get("name") == name]
    if not matches:
        raise RuntimeError(f"missing security policy: {name}")
    if len(matches) > 1:
        raise RuntimeError(f"duplicate security policy: {name}")
    return matches[0]


def ip_sort_key(value):
    return tuple(int(part) for part in value.split("."))


def parse_ipv4_list(raw):
    ips = []
    for token in raw.replace(",", "\n").splitlines():
        token = token.strip()
        if not token:
            continue
        ip = urllib.parse.unquote(token)
        parsed = __import__("ipaddress").ip_address(ip)
        if parsed.version != 4:
            raise ValueError(f"only IPv4 hosts are supported: {token}")
        ips.append(str(parsed))
    return sorted(dict.fromkeys(ips), key=ip_sort_key)


def existing_host_ips(record):
    values = []
    for member in record.get("include") or []:
        if member.get("addr_type") != "host" or not member.get("ip"):
            raise RuntimeError(f"{record.get('name')} contains non-host member: {member}")
        values.append(str(__import__("ipaddress").ip_address(str(member["ip"]))))
    return sorted(dict.fromkeys(values), key=ip_sort_key)


def set_address_object(base_url, cookies, record, name, ips, insecure=False):
    body = {
        "obj_addr": [
            {
                "name": name,
                "oldname": name,
                "desc": record.get("desc", "") or "",
                "include": [{"ip": ip, "addr_type": "host"} for ip in ips],
                "exclude": record.get("exclude") or [],
            }
        ]
    }
    result = nsg_session_call(
        base_url,
        cookies,
        "obj_address",
        "set_obj_addr_conf",
        body,
        insecure=insecure,
    )
    return ensure_ok(result, f"set_obj_addr_conf {name}")


def nsg_address_ips_publish(cfg, object_name, ips, mode="replace", apply=False, transport="direct"):
    base_url = cfg["base_url"].rstrip("/")
    username = cfg["username"]
    password = cfg["password"]
    insecure = bool(cfg.get("insecure_tls", False))
    cookies = nsg_login_session(base_url, username, password, insecure=insecure)
    try:
        before = read_nsg_address_object(base_url, cookies, object_name, insecure=insecure)
        policy = read_nsg_policy(base_url, cookies, object_name, insecure=insecure)
        if object_name not in "\n".join(collect_strings(policy)):
            raise RuntimeError(f"security policy {object_name} does not reference address object {object_name}")
        old_ips = existing_host_ips(before)
        if mode == "replace":
            final_ips = ips
            add_ips = [ip for ip in final_ips if ip not in set(old_ips)]
            remove_ips = [ip for ip in old_ips if ip not in set(final_ips)]
        elif mode == "append":
            final_ips = sorted(dict.fromkeys(old_ips + ips), key=ip_sort_key)
            add_ips = [ip for ip in ips if ip not in set(old_ips)]
            remove_ips = []
        else:
            raise ValueError(f"unsupported mode: {mode}")
        if len(final_ips) > 512:
            raise RuntimeError(f"object include limit exceeded: {object_name}={len(final_ips)}")
        report = {
            "time": dt.datetime.now().isoformat(timespec="seconds"),
            "transport": transport,
            "base_url": base_url,
            "object": object_name,
            "mode": mode,
            "preflight": {
                "object_found": True,
                "policy_found": True,
                "policy_references_object": True,
                "current_count": len(old_ips),
                "reference": before.get("reference"),
            },
            "plan": {
                "input_count": len(ips),
                "add_count": len(add_ips),
                "remove_count": len(remove_ips),
                "final_count": len(final_ips),
            },
            "applied": False,
        }
        if apply:
            set_address_object(base_url, cookies, before, object_name, final_ips, insecure=insecure)
            after = read_nsg_address_object(base_url, cookies, object_name, insecure=insecure)
            after_policy = read_nsg_policy(base_url, cookies, object_name, insecure=insecure)
            if object_name not in "\n".join(collect_strings(after_policy)):
                raise RuntimeError(f"postflight policy check failed: {object_name}")
            after_ips = existing_host_ips(after)
            report["applied"] = True
            report["after"] = {"count": len(after_ips)}
            report["verification"] = {
                "missing_ips": sorted(set(final_ips) - set(after_ips), key=ip_sort_key),
                "unexpected_ips": sorted(set(after_ips) - set(final_ips), key=ip_sort_key),
            }
        return report
    finally:
        nsg_logout_session(base_url, username, cookies, insecure=insecure)


def run_command(cmd, cwd=None, **kwargs):
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=cwd, **kwargs)


def extract_json(text):
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError(f"no JSON object found in output:\n{text}")
    return json.loads(text[start : end + 1])


def nsg_address_ips_doops(cfg, object_name, ips, mode="replace", apply=False):
    target = cfg.get("doops_target") or "zy"
    doops_cwd = cfg.get("doops_cwd")
    session = "nsg_addr_ips_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_root = pathlib.Path(tempfile.mkdtemp(prefix="nsg-cli-doops-"))
    remote_created = False
    try:
        shutil.copy2(pathlib.Path(__file__).resolve(), temp_root / "netentsecctl.py")
        (temp_root / "connection.local.json").write_text(
            json.dumps({"nsg_firewall": cfg}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (temp_root / "ips.txt").write_text("\n".join(ips) + "\n", encoding="utf-8")
        pushed = run_command(["doops", "-session", session, "push", "--target", target, "--src", str(temp_root)], cwd=doops_cwd)
        if pushed.returncode != 0:
            raise RuntimeError(f"doops push failed:\n{pushed.stdout}")
        remote_created = True
        remote_cmd = (
            f"cd /root/ws/{session} && python3 netentsecctl.py --config connection.local.json "
            f"nsg-address-ips --object '{object_name}' --ips-file ips.txt --mode {mode} --transport direct"
            f"{' --apply' if apply else ''}"
        )
        executed = run_command(["doops", "-session", session, "exec", "--target", target, "--cmd", remote_cmd], cwd=doops_cwd, timeout=180)
        if executed.returncode != 0:
            raise RuntimeError(f"doops exec failed:\n{executed.stdout}")
        report = extract_json(executed.stdout)
        report["transport"] = "doops"
        report["doops"] = {"target": target, "session": session}
        return report
    finally:
        if remote_created:
            run_command(["doops", "-session", session, "clean", "--target", target, "--workspace", session], cwd=doops_cwd, timeout=60)
        shutil.rmtree(temp_root, ignore_errors=True)


def cmd_nsg_address_ips(args):
    cfg = load_nsg_config(args.config)
    cfg["base_url"] = args.base_url or cfg.get("base_url")
    cfg["insecure_tls"] = args.insecure or bool(cfg.get("insecure_tls", False))
    if args.username:
        cfg["username"] = args.username
    if args.password:
        cfg["password"] = args.password
    missing = [key for key in ("base_url", "username", "password") if not cfg.get(key)]
    if missing:
        raise RuntimeError(f"missing config fields: {', '.join(missing)}")
    raw_ips = args.ips_file.read_text(encoding="utf-8") if args.ips_file else (args.ips or sys.stdin.read())
    ips = parse_ipv4_list(raw_ips)
    report = None
    direct_error = None
    if args.transport in ("auto", "direct"):
        try:
            report = nsg_address_ips_publish(cfg, args.object, ips, mode=args.mode, apply=args.apply, transport="direct")
        except Exception as exc:
            direct_error = str(exc)
            if args.transport == "direct":
                raise
    if report is None:
        report = nsg_address_ips_doops(cfg, args.object, ips, mode=args.mode, apply=args.apply)
        if direct_error:
            report["direct_error"] = direct_error
    print(json.dumps(report, ensure_ascii=False, indent=2))
    verification = report.get("verification", {})
    if verification.get("missing_ips") or verification.get("unexpected_ips"):
        raise SystemExit(3)


def cmd_nsg_login(args):
    cfg = load_nsg_config(args.config)
    base_url = args.base_url or cfg.get("base_url")
    username = args.username or cfg.get("username")
    password = args.password or cfg.get("password")
    insecure = args.insecure or bool(cfg.get("insecure_tls", False))
    missing = [
        name
        for name, value in (("base_url", base_url), ("username", username), ("password", password))
        if not value
    ]
    if missing:
        raise RuntimeError(f"missing config fields: {', '.join(missing)}")
    result = nsg_login(base_url, username, password, insecure=insecure)
    if args.output == "token":
        print(result["token"])
    else:
        print(json.dumps(result["raw"], ensure_ascii=False, indent=2))


def cmd_nsg_rest(args):
    body = json.loads(args.json)
    result = nsg_rest(args.base_url, args.token, body=body, insecure=args.insecure, phpsessid=args.phpsessid)
    print(json.dumps(result["data"], ensure_ascii=False, indent=2))


def cmd_nsg_call(args):
    body = json.loads(args.body_json) if args.body_json else {}
    result = nsg_call(
        args.base_url,
        args.token,
        args.module,
        args.function,
        body=body,
        page_index=args.page_index,
        page_size=args.page_size,
        insecure=args.insecure,
        phpsessid=args.phpsessid,
    )
    print(json.dumps(result["data"], ensure_ascii=False, indent=2))


def load_matrix_rows(path, risk="read", limit=None):
    rows = []
    with pathlib.Path(path).open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if risk and row.get("risk") != risk:
                continue
            rows.append(row)
            if limit and len(rows) >= limit:
                break
    return rows


def default_body_for_read(function):
    if function == "get_sec_policy":
        return {"sec_policy": [{"name": "", "is_detail": True}]}
    if function in {"get_obj_addr_list", "get_obj_addr_group"}:
        return {"obj_addr": [{"is_detail": False}]}
    if function == "get_blacklist_config":
        return {"addr_blacklist_cp": {"search_key": ""}}
    if function == "show_batch_domain_blacklist":
        return {"addr_blacklist_cp": {"search_key": "", "type": "hit_num"}}
    return {}


def cmd_nsg_batch_test(args):
    cfg = load_nsg_config(args.config)
    base_url = args.base_url or cfg.get("base_url")
    username = args.username or cfg.get("username")
    password = args.password or cfg.get("password")
    insecure = args.insecure or bool(cfg.get("insecure_tls", False))
    missing = [
        name
        for name, value in (("base_url", base_url), ("username", username), ("password", password))
        if not value
    ]
    if missing:
        raise RuntimeError(f"missing config fields: {', '.join(missing)}")
    if args.transport in ("auto", "doops"):
        direct_error = None
        if args.transport == "auto":
            try:
                return run_nsg_batch_direct(args, cfg)
            except Exception as exc:
                direct_error = str(exc)
        report = nsg_batch_test_doops(cfg, args.matrix, args.limit, args.page_size, args.stop_on_error, direct_error)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return
    return run_nsg_batch_direct(args, cfg)


def run_nsg_batch_direct(args, cfg):
    base_url = args.base_url or cfg.get("base_url")
    username = args.username or cfg.get("username")
    password = args.password or cfg.get("password")
    insecure = args.insecure or bool(cfg.get("insecure_tls", False))
    missing = [
        name
        for name, value in (("base_url", base_url), ("username", username), ("password", password))
        if not value
    ]
    if missing:
        raise RuntimeError(f"missing config fields: {', '.join(missing)}")
    rows = load_matrix_rows(args.matrix, risk="read", limit=args.limit)
    cookies = nsg_login_session(base_url.rstrip("/"), username, password, insecure=insecure)
    report = {
        "time": dt.datetime.now().isoformat(timespec="seconds"),
        "base_url": base_url,
        "matrix": str(args.matrix),
        "limit": args.limit,
        "total_candidates": len(rows),
        "results": [],
    }
    try:
        for row in rows:
            module = row["module"]
            function = row["function"]
            body = default_body_for_read(function)
            try:
                result = nsg_session_call(
                    base_url.rstrip("/"),
                    cookies,
                    module,
                    function,
                    body=body,
                    page_index=1,
                    page_size=args.page_size,
                    insecure=insecure,
                )
                data = result.get("data")
                head = data.get("head", {}) if isinstance(data, dict) else {}
                report["results"].append(
                    {
                        "module": module,
                        "function": function,
                        "ok": head.get("error_code") in (0, "0"),
                        "error_code": head.get("error_code"),
                        "error_string": head.get("error_string"),
                    }
                )
            except Exception as exc:
                report["results"].append(
                    {
                        "module": module,
                        "function": function,
                        "ok": False,
                        "exception": str(exc),
                    }
                )
            if args.stop_on_error and not report["results"][-1]["ok"]:
                break
    finally:
        nsg_logout_session(base_url.rstrip("/"), username, cookies, insecure=insecure)
    report["ok_count"] = sum(1 for item in report["results"] if item.get("ok"))
    report["fail_count"] = len(report["results"]) - report["ok_count"]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


def nsg_batch_test_doops(cfg, matrix, limit, page_size, stop_on_error, direct_error=None):
    target = cfg.get("doops_target") or "zy"
    doops_cwd = cfg.get("doops_cwd")
    session = "nsg_batch_test_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    temp_root = pathlib.Path(tempfile.mkdtemp(prefix="nsg-batch-doops-"))
    remote_created = False
    try:
        shutil.copy2(pathlib.Path(__file__).resolve(), temp_root / "netentsecctl.py")
        (temp_root / "connection.local.json").write_text(
            json.dumps({"nsg_firewall": cfg}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        shutil.copy2(pathlib.Path(matrix), temp_root / "api-coverage-matrix.csv")
        pushed = run_command(["doops", "-session", session, "push", "--target", target, "--src", str(temp_root)], cwd=doops_cwd)
        if pushed.returncode != 0:
            raise RuntimeError(f"doops push failed:\n{pushed.stdout}")
        remote_created = True
        limit_arg = f" --limit {limit}" if limit else ""
        stop_arg = " --stop-on-error" if stop_on_error else ""
        remote_cmd = (
            f"cd /root/ws/{session} && python3 netentsecctl.py --config connection.local.json "
            f"nsg-batch-test --transport direct --matrix api-coverage-matrix.csv --page-size {page_size}"
            f"{limit_arg}{stop_arg} --output result.json"
        )
        executed = run_command(["doops", "-session", session, "exec", "--target", target, "--cmd", remote_cmd], cwd=doops_cwd, timeout=240)
        if executed.returncode != 0:
            raise RuntimeError(f"doops exec failed:\n{executed.stdout}")
        read = run_command(
            ["doops", "-session", session, "read", "--target", target, "--path", f"/root/ws/{session}/result.json"],
            cwd=doops_cwd,
            timeout=120,
        )
        if read.returncode != 0:
            raise RuntimeError(f"doops read failed:\n{read.stdout}")
        report = extract_json(read.stdout)
        report["transport"] = "doops"
        report["doops"] = {"target": target, "session": session}
        if direct_error:
            report["direct_error"] = direct_error
        return report
    finally:
        if remote_created:
            run_command(["doops", "-session", session, "clean", "--target", target, "--workspace", session], cwd=doops_cwd, timeout=60)
        shutil.rmtree(temp_root, ignore_errors=True)


def build_parser():
    parser = argparse.ArgumentParser(prog="netentsecctl")
    parser.add_argument("--base-url")
    parser.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    parser.add_argument("--insecure", action="store_true", help="skip TLS verification")

    sub = parser.add_subparsers(dest="command", required=True)

    p_nsg_login = sub.add_parser("nsg-login", aliases=["v10-login"], help="NSG firewall /v1.0/login flow")
    p_nsg_login.add_argument("-u", "--username")
    p_nsg_login.add_argument("-p", "--password")
    p_nsg_login.add_argument("--output", choices=["json", "token"], default="json")
    p_nsg_login.set_defaults(func=cmd_nsg_login)

    p_nsg_rest = sub.add_parser("nsg-rest", aliases=["v10-rest"], help="NSG firewall raw /v1.0/rest/ call; JSON body should be the request array")
    p_nsg_rest.add_argument("--token", required=True)
    p_nsg_rest.add_argument("--phpsessid", help="optional PHPSESSID returned by login")
    p_nsg_rest.add_argument("--json", required=True, help="JSON request array string")
    p_nsg_rest.set_defaults(func=cmd_nsg_rest)

    p_nsg_call = sub.add_parser("nsg-call", help="NSG firewall /v1.0/rest/ call built from module/function")
    p_nsg_call.add_argument("--token", required=True)
    p_nsg_call.add_argument("--phpsessid", help="optional PHPSESSID returned by login")
    p_nsg_call.add_argument("--module", required=True)
    p_nsg_call.add_argument("--function", required=True)
    p_nsg_call.add_argument("--body-json", help="JSON object for body")
    p_nsg_call.add_argument("--page-index", type=int, default=1)
    p_nsg_call.add_argument("--page-size", type=int, default=20)
    p_nsg_call.set_defaults(func=cmd_nsg_call)

    p_nsg_addr_ips = sub.add_parser("nsg-address-ips", help="replace or append IPv4 host members in one NSG address object")
    p_nsg_addr_ips.add_argument("--object", default="翻墙禁止上网")
    p_nsg_addr_ips.add_argument("--ips-file", type=pathlib.Path)
    p_nsg_addr_ips.add_argument("--ips", help="newline or comma separated IPv4 hosts; stdin is used when omitted")
    p_nsg_addr_ips.add_argument("--mode", choices=["replace", "append"], default="replace")
    p_nsg_addr_ips.add_argument("--transport", choices=["auto", "direct", "doops"], default="doops")
    p_nsg_addr_ips.add_argument("--username")
    p_nsg_addr_ips.add_argument("--password")
    p_nsg_addr_ips.add_argument("--apply", action="store_true")
    p_nsg_addr_ips.set_defaults(func=cmd_nsg_address_ips)

    p_batch = sub.add_parser("nsg-batch-test", help="run read-only module/function tests from the coverage matrix")
    p_batch.add_argument("--matrix", type=pathlib.Path, default=DEFAULT_MATRIX)
    p_batch.add_argument("--limit", type=int, help="maximum read candidates to test")
    p_batch.add_argument("--page-size", type=int, default=20)
    p_batch.add_argument("--transport", choices=["auto", "direct", "doops"], default="doops")
    p_batch.add_argument("--username")
    p_batch.add_argument("--password")
    p_batch.add_argument("--output", type=pathlib.Path)
    p_batch.add_argument("--stop-on-error", action="store_true")
    p_batch.set_defaults(func=cmd_nsg_batch_test)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        print(body, file=sys.stderr)
        raise SystemExit(e.code)
    except Exception as e:
        print(str(e), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
