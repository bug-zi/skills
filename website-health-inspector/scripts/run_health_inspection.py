from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from check_runtime_dependencies import check_pdf_browser
from env_utils import load_project_env
from health_common import ensure_dir
from health_common import read_json


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent


def run_step(label: str, script_name: str, args: list[str]) -> None:
    command = [sys.executable, str(SCRIPT_DIR / script_name), *args]
    print(f"[website-health-inspector] {label}: {script_name}")
    result = subprocess.run(command, cwd=str(ROOT), check=False)
    if result.returncode != 0:
        raise SystemExit(f"{script_name} failed with exit code {result.returncode}")


def require_pdf_runtime() -> None:
    status = check_pdf_browser(required=True)
    if not status["ok"]:
        raise SystemExit(status["message"])


def ordered_checks(raw: str) -> str:
    requested = {item.strip() for item in raw.split(",") if item.strip()}
    requested.discard("render")
    requested.add("merge")
    order = ["discovery", "content", "deep-browser", "browser", "host", "merge"]
    return ",".join(item for item in order if item in requested)


def validate_formal_report(out_dir: Path) -> None:
    html_path = out_dir / "final-report.html"
    if not html_path.exists():
        raise SystemExit("Formal HTML report is missing: final-report.html")
    pdf_path = out_dir / "final-report.pdf"
    if not pdf_path.exists() or pdf_path.stat().st_size <= 0:
        raise SystemExit("Formal PDF report is missing or empty: final-report.pdf")
    markup = html_path.read_text(encoding="utf-8", errors="replace")
    required_markers = {
        "guide cover": '<section class="guide-cover"',
        "fold sections": 'class="fold-section"',
        "report nav": 'class="report-nav"',
        "formal template style": "--paper:",
    }
    missing = [label for label, marker in required_markers.items() if marker not in markup]
    if missing:
        raise SystemExit("Formal report quality gate failed; missing: " + ", ".join(missing))
    legacy_htmls = sorted(
        item.name
        for item in out_dir.glob("final-*-health-report.html")
        if item.name != "final-report.html"
    )
    if legacy_htmls:
        raise SystemExit(
            "Formal report quality gate failed; non-final HTML artifacts remain: "
            + ", ".join(legacy_htmls)
            + ". Re-run render_report.py so drafts are archived before delivery."
        )


def score_audit_allows_manual_approval(out_dir: Path) -> bool:
    audit = read_json(out_dir / "score-audit.json")
    reasons = set(audit.get("blocking_reasons") or [])
    return str(audit.get("status") or "") == "blocked" and reasons.issubset({"low_score_requires_review"})


def main() -> None:
    load_project_env(ROOT)
    parser = argparse.ArgumentParser(
        description="Run the official website health inspection pipeline and render the formal report."
    )
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--name")
    parser.add_argument("--username")
    parser.add_argument("--password")
    parser.add_argument("--password-env", default="WEBSITE_HEALTH_ADMIN_PASSWORD")
    parser.add_argument("--no-discovery", action="store_true")
    parser.add_argument("--checks", default="discovery,content,deep-browser,host")
    parser.add_argument(
        "--guide-mode",
        choices=["auto", "ai-image", "html-guide", "reuse-existing"],
        default="auto",
        help="Guide cover mode. html-guide/reuse-existing skip image generation; auto/ai-image let render_report decide.",
    )
    parser.add_argument("--skip-ai-guide-image", action="store_true", help="Compatibility alias for --guide-mode html-guide.")
    parser.add_argument("--no-pdf", action="store_true", help="Debug only: skip PDF generation and delivery readiness.")
    parser.add_argument("--no-quality-audit", action="store_true")
    parser.add_argument("--score-audit-threshold", type=int, default=60)
    parser.add_argument("--score-review-approved", action="store_true")
    parser.add_argument("--score-review-note", default="")
    args = parser.parse_args()
    if args.score_review_approved and not args.score_review_note.strip():
        raise SystemExit("--score-review-note is required when --score-review-approved is used")

    out_dir = ensure_dir(args.out)
    if not args.no_pdf:
        require_pdf_runtime()
    if args.password:
        os.environ[args.password_env] = args.password

    build_args = ["--url", args.url, "--out", str(out_dir)]
    if args.name:
        build_args.extend(["--name", args.name])
    if args.no_discovery:
        build_args.append("--no-discovery")
    if args.username:
        build_args.extend(["--username", args.username, "--password-env", args.password_env])
    run_step("build inventory", "build_adhoc_inventory.py", build_args)

    inventory_path = out_dir / "inventory.normalized.json"
    inspect_args = [
        "--inventory",
        str(inventory_path),
        "--out",
        str(out_dir),
        "--checks",
        ordered_checks(args.checks),
        "--score-audit-threshold",
        str(args.score_audit_threshold),
    ]
    if args.score_review_approved:
        inspect_args.extend(["--score-review-approved", "--score-review-note", args.score_review_note])
    run_step(
        "run checks and merge JSON",
        "inspect_sites.py",
        inspect_args,
    )

    final_json = out_dir / "final-report.json"
    score_audit_args = [
        "--report",
        str(final_json),
        "--out",
        str(out_dir),
        "--threshold",
        str(args.score_audit_threshold),
    ]
    try:
        run_step("audit score reasonableness", "audit_score_reasonableness.py", score_audit_args)
    except SystemExit:
        if not args.score_review_approved or not score_audit_allows_manual_approval(out_dir):
            raise
    render_args = ["--report", str(final_json), "--out", str(out_dir)]
    if args.skip_ai_guide_image:
        render_args.append("--skip-ai-guide-image")
    else:
        render_args.extend(["--guide-mode", args.guide_mode])
    if args.no_pdf:
        render_args.append("--no-pdf")
    if args.score_review_approved:
        render_args.extend(["--score-review-approved", "--score-review-note", args.score_review_note])
    run_step("render formal HTML/Markdown/PDF report", "render_report.py", render_args)
    if args.no_pdf:
        print("[website-health-inspector] PDF was skipped for debug-only output; delivery will not be ready.")
    else:
        validate_formal_report(out_dir)

    if not args.no_quality_audit:
        run_step(
            "run report quality audit",
            "audit_report_quality.py",
            [
                "--run-dir",
                str(out_dir),
                "--iteration",
                "1",
                "--out",
                str(out_dir / "quality-audit.md"),
            ],
        )

    print(f"[website-health-inspector] delivery HTML: {out_dir / 'delivery' / 'final-report.html'}")
    print(f"[website-health-inspector] delivery PDF: {out_dir / 'delivery' / 'final-report.pdf'}")
    print(f"[website-health-inspector] delivery manifest: {out_dir / 'delivery-manifest.json'}")
    print(f"[website-health-inspector] structured JSON: {final_json}")


if __name__ == "__main__":
    main()
