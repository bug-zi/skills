from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def find_browser() -> str:
    candidates = [
        os.getenv("CHROME_PATH", ""),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    browser = next((item for item in candidates if item and Path(item).exists()), "")
    return browser


def check_openpyxl(required: bool) -> dict:
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        return {
            "name": "openpyxl",
            "ok": not required,
            "required": required,
            "message": "Install with `python -m pip install openpyxl` to read Excel inventories.",
        }
    return {"name": "openpyxl", "ok": True, "required": required, "message": "available"}


def check_pdf_browser(required: bool) -> dict:
    browser = find_browser()
    if browser:
        return {"name": "pdf_browser", "ok": True, "required": required, "message": browser}
    return {
        "name": "pdf_browser",
        "ok": not required,
        "required": required,
        "message": "Chrome/Edge was not found. Install a browser, set CHROME_PATH, or use --no-pdf for debug-only output.",
    }


def build_checks(*, excel: bool, pdf: bool) -> list[dict]:
    return [
        check_openpyxl(excel),
        check_pdf_browser(pdf),
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Check website-health-inspector runtime dependencies.")
    parser.add_argument("--excel", action="store_true", help="Require Excel import dependencies.")
    parser.add_argument("--pdf", action="store_true", help="Require Chrome/Edge PDF printing support.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable dependency status.")
    args = parser.parse_args()

    checks = build_checks(excel=args.excel, pdf=args.pdf)
    payload = {
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for item in checks:
            status = "OK" if item["ok"] else "MISSING"
            required = "required" if item["required"] else "optional"
            print(f"[{status}] {item['name']} ({required}): {item['message']}")
    if not payload["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
