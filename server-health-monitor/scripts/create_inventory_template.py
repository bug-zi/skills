#!/usr/bin/env python3
"""Create a CSV template for server health inventory."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


FIELDS = [
    "name",
    "address",
    "os_type",
    "role",
    "owner",
    "department",
    "business_system",
    "business_domain",
    "user_group",
    "criticality",
    "has_redundancy",
    "impact_note",
    "ports",
    "auth_ref",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a server inventory CSV template.")
    parser.add_argument("--out", required=True, help="Output CSV path.")
    args = parser.parse_args()
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(
            {
                "name": "zheyin-web-01",
                "address": "192.0.2.10",
                "os_type": "linux",
                "role": "portal web",
                "owner": "web operations",
                "department": "Information Center",
                "business_system": "Campus portal",
                "business_domain": "office",
                "user_group": "faculty and students",
                "criticality": "core",
                "has_redundancy": "false",
                "impact_note": "Portal access may be affected if HTTPS is unreachable.",
                "ports": "22,80,443",
                "auth_ref": "env:ZHEYIN_WEB01_SSH_PASSWORD",
            }
        )
    print(f"Template written to {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
