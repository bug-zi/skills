from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlparse

from health_common import ensure_dir, is_valid_url, normalize_url, now_iso, slugify, write_json


def build_inventory(
    url: str,
    *,
    name: str | None = None,
    discovery: bool = True,
    username: str | None = None,
    password_env: str | None = None,
) -> dict:
    normalized = normalize_url(url)
    if not is_valid_url(normalized):
        raise SystemExit(f"Invalid URL: {url}")
    parsed = urlparse(normalized)
    system_id = slugify(parsed.netloc.replace(".", "-"), "adhoc-site")
    page_name = name or parsed.netloc
    return {
        "generated_at": now_iso(),
        "source": {"type": "adhoc-url", "url": normalized},
        "systems": [
            {
                "id": system_id,
                "name": page_name,
                "priority": "medium",
                "owner": "管理员",
                "environment": "adhoc",
                "websites": [
                    {
                        "page_id": "entry",
                        "name": "入口页面",
                        "url": normalized,
                        "expected_status": 200,
                        "timeout_ms": 5000,
                        "content_checks": {
                            "required_text": [],
                            "forbidden_text": ["404", "500", "系统维护", "系统繁忙", "服务不可用", "Internal Server Error"],
                            "min_length": 80,
                        },
                        "source": "adhoc-url",
                    }
                ],
                "admin_flows": [],
                "admin_credentials": {
                    "username": username,
                    "password_env": password_env,
                    "login_url": normalized.rstrip("/") + "/login",
                }
                if username and password_env
                else {},
                "hosts": [],
                "services": [],
            }
        ],
        "global": {
            "allow_mutation": False,
            "screenshot_on_failure": True,
            "max_parallel": 5,
            "crawler": {
                "enabled": bool(discovery),
                "max_depth": 1,
                "max_pages": 20,
                "same_origin_only": True,
                "request_interval_ms": 200,
                "obey_robots_txt": True,
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a temporary inventory from one URL.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--name")
    parser.add_argument("--out", required=True)
    parser.add_argument("--no-discovery", action="store_true")
    parser.add_argument("--username")
    parser.add_argument("--password-env", default="WEBSITE_HEALTH_ADMIN_PASSWORD")
    args = parser.parse_args()

    out_dir = ensure_dir(args.out)
    inventory = build_inventory(
        args.url,
        name=args.name,
        discovery=not args.no_discovery,
        username=args.username,
        password_env=args.password_env if args.username else None,
    )
    write_json(Path(out_dir) / "inventory.normalized.json", inventory)
    print(Path(out_dir) / "inventory.normalized.json")


if __name__ == "__main__":
    main()
