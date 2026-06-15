from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from health_common import ensure_dir, read_json


SCRIPT_DIR = Path(__file__).resolve().parent

MODULE_FAILURES = {
    "discover_site_pages.py": (
        "site-discovery",
        "site-discovery-report.json",
        "页面发现模块未执行成功",
    ),
    "check_content.py": (
        "content-review",
        "content-review-report.json",
        "内容完整性检查未执行成功",
    ),
    "check_deep_browser.py": (
        "browser-inspection",
        "browser-inspection-report.json",
        "浏览器深度巡检未执行成功",
    ),
    "check_browser_flow.py": (
        "browser-flow",
        "browser-flow-report.json",
        "浏览器流程巡检未执行成功",
    ),
    "check_host_services.py": (
        "host-services",
        "host-services-report.json",
        "主机与服务检查未执行成功",
    ),
}


def run_script(name: str, args: list[str]) -> int:
    cmd = [sys.executable, str(SCRIPT_DIR / name), *args]
    return subprocess.run(cmd, check=False).returncode


def record_failed_module(out_dir: Path, report_type: str, title: str, detail: str) -> None:
    from health_common import module_report, write_json

    system = {"id": report_type, "name": title, "priority": "medium"}
    finding = {
        "id": f"{report_type}-runtime-001",
        "system_id": report_type,
        "system_name": title,
        "severity": "medium",
        "priority": "P2",
        "title": title,
        "business_impact": "本轮对应检查模块未能执行，报告覆盖范围不完整，需要先修复巡检运行环境后复查。",
        "technical_evidence": detail,
        "target": report_type,
        "recommendation": "修复巡检依赖或运行环境后重新执行该模块，避免误把缺失检查解读为系统健康。",
        "evidence_files": [],
    }
    filename = next(
        (item[1] for item in MODULE_FAILURES.values() if item[0] == report_type),
        f"{report_type}-report.json",
    )
    write_json(out_dir / filename, module_report(report_type, [finding], [{"system_id": system["id"], "system_name": system["name"], "findings": 1}], {"runtime_failed": True}))


def run_check_module(out_dir: Path, script_name: str, args: list[str], *, strict: bool = False) -> int:
    code = run_script(script_name, args)
    if code == 0:
        return code
    report_type, _, title = MODULE_FAILURES.get(
        script_name,
        (Path(script_name).stem, f"{Path(script_name).stem}-report.json", f"{script_name} 未执行成功"),
    )
    detail = f"{script_name} exited with code {code}"
    record_failed_module(out_dir, report_type, title, detail)
    if strict:
        raise SystemExit(detail)
    return code


def run_required_step(script_name: str, args: list[str]) -> None:
    code = run_script(script_name, args)
    if code != 0:
        raise SystemExit(f"{script_name} failed with exit code {code}")


def score_audit_allows_manual_approval(out_dir: Path) -> bool:
    audit = read_json(out_dir / "score-audit.json")
    reasons = set(audit.get("blocking_reasons") or [])
    return str(audit.get("status") or "") == "blocked" and reasons.issubset({"low_score_requires_review"})


def main() -> None:
    parser = argparse.ArgumentParser(description="Orchestrate website health inspection modules.")
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--checks", default="discovery,content,deep-browser,host,merge,render")
    parser.add_argument(
        "--guide-mode",
        choices=["auto", "ai-image", "html-guide", "reuse-existing"],
        default="auto",
        help="导读图生成方式；缺少 API Key 时 auto 会要求先确认用户选择。",
    )
    parser.add_argument("--skip-ai-guide-image", action="store_true", help="兼容参数，等同 --guide-mode html-guide。")
    parser.add_argument("--no-pdf", action="store_true", help="Debug only: skip final-report.pdf generation.")
    parser.add_argument("--strict", action="store_true", help="Fail immediately if any check module exits non-zero.")
    parser.add_argument("--score-audit-threshold", type=int, default=60)
    parser.add_argument("--score-review-approved", action="store_true")
    parser.add_argument("--score-review-note", default="")
    args = parser.parse_args()
    if args.score_review_approved and not args.score_review_note.strip():
        raise SystemExit("--score-review-note is required when --score-review-approved is used")

    out_dir = ensure_dir(args.out)
    inventory = read_json(args.inventory)
    checks = {item.strip() for item in args.checks.split(",") if item.strip()}

    if "discovery" in checks and inventory.get("global", {}).get("crawler", {}).get("enabled"):
        run_check_module(out_dir, "discover_site_pages.py", ["--inventory", args.inventory, "--out", str(out_dir), "--merge"], strict=args.strict)
    if "content" in checks:
        run_check_module(out_dir, "check_content.py", ["--inventory", args.inventory, "--out", str(out_dir)], strict=args.strict)
    if "deep-browser" in checks:
        run_check_module(out_dir, "check_deep_browser.py", ["--inventory", args.inventory, "--out", str(out_dir)], strict=args.strict)
    if "browser" in checks:
        run_check_module(out_dir, "check_browser_flow.py", ["--inventory", args.inventory, "--out", str(out_dir)], strict=args.strict)
    if "host" in checks:
        run_check_module(out_dir, "check_host_services.py", ["--inventory", args.inventory, "--out", str(out_dir)], strict=args.strict)
    if "merge" in checks:
        final = out_dir / "final-report.json"
        run_required_step("merge_reports.py", ["--in", str(out_dir), "--out", str(final)])
        if not final.exists():
            raise SystemExit("merge_reports.py completed but final-report.json was not generated")
        audit_args = [
            "--report",
            str(final),
            "--out",
            str(out_dir),
            "--threshold",
            str(args.score_audit_threshold),
        ]
        code = run_script("audit_score_reasonableness.py", audit_args)
        if code != 0:
            if not args.score_review_approved or not score_audit_allows_manual_approval(out_dir):
                raise SystemExit(f"audit_score_reasonableness.py failed with exit code {code}")
    if "render" in checks:
        final = out_dir / "final-report.json"
        if not final.exists():
            raise SystemExit("render requested but final-report.json is missing")
        render_args = ["--report", str(final), "--out", str(out_dir)]
        if args.skip_ai_guide_image:
            render_args.append("--skip-ai-guide-image")
        else:
            render_args.extend(["--guide-mode", args.guide_mode])
        if args.no_pdf:
            render_args.append("--no-pdf")
        if args.score_review_approved:
            render_args.append("--score-review-approved")
            render_args.extend(["--score-review-note", args.score_review_note])
        run_required_step("render_report.py", render_args)
    print(out_dir)


if __name__ == "__main__":
    main()
