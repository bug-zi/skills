from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))


def minimal_report() -> dict:
    return {
        "generated_at": "2026-05-10T08:00:00+08:00",
        "overall_status": "warning",
        "score": 76,
        "executive_summary": "公开页面可访问，管理员入口需要复核。",
        "summary": {"total_systems": 1, "healthy": 0, "warning": 1, "critical": 0, "unknown": 0},
        "systems": [{"id": "admin", "name": "管理平台", "status": "warning", "score": 76}],
        "priority_findings": [
            {
                "id": "finding-001",
                "system_id": "admin",
                "system_name": "管理平台",
                "severity": "medium",
                "priority": "P2",
                "title": "受保护入口待复核",
                "business_impact": "需要确认登录态下业务入口是否稳定。",
                "technical_evidence": "automation_login_status=unknown",
                "target": "https://example.com/admin",
                "recommendation": "使用人工已确认登录态复测。",
            }
        ],
        "module_reports": [],
        "artifacts": {},
    }


def write_report(tmp_path: Path) -> Path:
    report_path = tmp_path / "final-report.json"
    report_path.write_text(json.dumps(minimal_report(), ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


def test_ai_guide_prompt_reflects_skill_core_functionality() -> None:
    import generate_ai_report_guide_image

    report = minimal_report()
    report["report_identity"] = {
        "site_name": "教务管理平台",
        "site_url": "https://example.com/admin?token=secret",
    }
    report["priority_findings"][0]["technical_evidence"] = (
        "request failed; OPENAI_API_KEY="
        + "sk-"
        + "real-secret-abcdefghijklmnopqrstuvwxyz; Cookie=session=abc"
    )
    report["module_reports"] = [
        {
            "report_type": "browser-inspection",
            "metrics": {
                "avg_open_time_ms": 1320,
                "slow_pages": 2,
                "avg_ttfb_ms": 260,
            },
        },
        {"report_type": "content-review"},
        {"report_type": "host-service-health"},
    ]

    prompt = generate_ai_report_guide_image.build_prompt(report)

    assert "管理平台管理员" in prompt
    assert "Excel 资源清单" in prompt
    assert "临时 URL 快速巡检" in prompt
    assert "URL + 管理员凭证深度浏览" in prompt
    assert "内容完整性审查" in prompt
    assert "管理员浏览器实测" in prompt
    assert "主机与微服务健康检查" in prompt
    assert "证据链" in prompt
    assert "不健康索引" in prompt
    assert "复测" in prompt
    assert "HTML/PDF/Markdown/JSON" in prompt
    assert "教务管理平台" in prompt
    assert "监测时间：2026-05-10 08:00" in prompt
    assert "平均打开时间" in prompt
    assert "sk-real-secret" not in prompt
    assert "Cookie=session" not in prompt
    assert "https://example.com" not in prompt


def test_overall_ai_guide_prompt_reflects_batch_governance() -> None:
    import generate_ai_report_guide_image

    report = {
        "report_kind": "multi-site-overall",
        "generated_at": "2026-05-10T08:00:00+08:00",
        "overall_status": "warning",
        "score": 82,
        "summary": {"total_systems": 4, "healthy": 1, "warning": 2, "critical": 0, "unknown": 1},
        "batch_metrics": {
            "site_count": 4,
            "average_score": 82,
            "lowest_score": 50,
            "failed": 1,
            "quality_failed": 1,
            "status_distribution": {"healthy": 1, "warning": 2, "critical": 0, "unknown": 1},
        },
        "site_results": [
            {"name": "门户站", "status": "healthy", "score": 96, "report": "sites/001/delivery/final-report.html"},
            {"name": "新闻网", "status": "warning", "score": 82, "report": "sites/002/delivery/final-report.html"},
            {"name": "服务大厅", "status": "warning", "score": 74, "report": "sites/003/delivery/final-report.html"},
            {"name": "缺地址站", "status": "unknown", "score": 0, "error": "URL 为空"},
        ],
        "priority_sites": [
            {"name": "缺地址站", "status": "unknown", "score": 0},
            {"name": "服务大厅", "status": "warning", "score": 74},
        ],
        "common_issue_families": [
            {"title": "站点巡检未完成", "site_count": 1, "priority": "P1"},
            {"title": "管理员入口待复核", "site_count": 2, "priority": "P2"},
        ],
        "priority_findings": [
            {
                "priority": "P1",
                "title": "站点巡检未完成",
                "business_impact": "批次覆盖存在缺口。",
                "technical_evidence": "token=secret; Cookie=session=abc",
                "recommendation": "补齐 URL 后重新纳入批次复测。",
            }
        ],
    }

    prompt = generate_ai_report_guide_image.build_prompt(report)

    assert "门户站、新闻网、服务大厅等4个站点健康巡检总体报告导览" in prompt
    assert "巡检对象：门户站、新闻网、服务大厅等4个站点" in prompt
    assert "监测时间：2026-05-10 08:00" in prompt
    assert "多站点网站健康巡检总体报告导览" not in prompt
    assert "批次治理" in prompt
    assert "N+1" in prompt
    assert "站点健康分布" in prompt
    assert "优先处置站点" in prompt
    assert "共性风险与问题族" in prompt
    assert "全量站点矩阵" in prompt
    assert "交付索引" in prompt
    assert "单站报告入口" in prompt
    assert "批次站点数：4" in prompt
    assert "平均评分：82/100" in prompt
    assert "最低评分：50/100" in prompt
    assert "失败/未知站点：1" in prompt
    assert "优先处置：缺地址站、服务大厅" in prompt
    assert "共性问题：站点巡检未完成（1站）、管理员入口待复核（2站）" in prompt
    assert "单站浏览器证据长分析" in prompt
    assert "Cookie=session" not in prompt
    assert "token=secret" not in prompt


def test_placeholder_api_key_is_not_treated_as_configured(monkeypatch) -> None:
    import generate_ai_report_guide_image
    import render_report

    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "your-key-here")

    assert not render_report.has_usable_openai_api_key()
    try:
        generate_ai_report_guide_image.generate_image(minimal_report(), Path("unused.png"), model="gpt-image-2", size="1024x1024", quality="low")
    except RuntimeError as exc:
        assert "OPENAI_API_KEY" in str(exc)
    else:
        raise AssertionError("placeholder key should not be accepted")


def test_secret_values_are_redacted_from_optional_error_file(tmp_path: Path) -> None:
    import render_report

    command = [sys.executable, "-c", "import sys; print('sk-' + 'real-secret-' + 'abcdefghijklmnopqrstuvwxyz'); sys.exit(2)"]

    ok = render_report.run_optional_with_error_file(command, tmp_path, "ai-report-guide-error.txt")

    text = (tmp_path / "ai-report-guide-error.txt").read_text(encoding="utf-8-sig")
    assert ok is False
    assert "sk-real-secret" not in text
    assert "[REDACTED_OPENAI_KEY]" in text


def test_summary_image_copy_is_not_accepted_as_ai_guide(tmp_path: Path) -> None:
    import render_report

    summary = tmp_path / "executive-summary.png"
    guide = tmp_path / "ai-report-guide.png"
    summary.write_bytes(b"same-image-bytes")
    guide.write_bytes(b"same-image-bytes")

    valid, reason = render_report.valid_ai_guide_image(guide, tmp_path)

    assert valid is False
    assert reason == "matches_executive_summary"


def test_no_api_key_without_explicit_guide_choice_stops_before_rendering(tmp_path: Path, monkeypatch) -> None:
    import render_report

    report_path = write_report(tmp_path)
    (tmp_path / "quality-audit.md").write_text("ok", encoding="utf-8")
    (tmp_path / "quality-audit.json").write_text('{"status": "pass"}', encoding="utf-8")
    (tmp_path / "score-audit.md").write_text("ok", encoding="utf-8")
    (tmp_path / "score-audit.json").write_text('{"status": "pass", "blocking_reasons": []}', encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    old_argv = sys.argv
    sys.argv = ["render_report.py", "--report", str(report_path), "--out", str(tmp_path), "--no-load-env"]
    try:
        with pytest.raises(SystemExit) as exc:
            render_report.main()
    finally:
        sys.argv = old_argv

    status = json.loads((tmp_path / "ai-report-guide-status.json").read_text(encoding="utf-8"))

    assert exc.value.code != 0
    assert status["status"] == "needs_user_choice"
    assert status["requires_user_api_key"] is True
    assert "请先询问用户" in status["message"]
    assert not (tmp_path / "final-report.html").exists()
    assert not (tmp_path / "delivery").exists()


def test_html_guide_mode_keeps_report_clean_and_records_user_choice(tmp_path: Path, monkeypatch) -> None:
    import render_report

    report_path = write_report(tmp_path)
    (tmp_path / "quality-audit.md").write_text("ok", encoding="utf-8")
    (tmp_path / "quality-audit.json").write_text('{"status": "pass"}', encoding="utf-8")
    (tmp_path / "score-audit.md").write_text("ok", encoding="utf-8")
    (tmp_path / "score-audit.json").write_text('{"status": "pass", "blocking_reasons": []}', encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    old_argv = sys.argv
    sys.argv = [
        "render_report.py",
        "--report",
        str(report_path),
        "--out",
        str(tmp_path),
        "--guide-mode",
        "html-guide",
        "--no-load-env",
    ]
    try:
        render_report.main()
    finally:
        sys.argv = old_argv

    html = (tmp_path / "final-report.html").read_text(encoding="utf-8")
    status = json.loads((tmp_path / "ai-report-guide-status.json").read_text(encoding="utf-8"))

    assert status["status"] == "html_guide_selected"
    assert status["requires_user_api_key"] is False
    assert "html-guide-visual" in html
    assert "OPENAI_API_KEY" not in html
    assert "--skip-ai-guide-image" not in html
    assert (tmp_path / "delivery" / "ai-report-guide-status.json").exists()


def test_guide_cover_names_the_inspected_site_and_url() -> None:
    import render_report

    report = minimal_report()
    report["report_identity"] = {
        "site_name": "杭州电子科技大学AI教育平台",
        "site_url": "https://hdu.aiedulab.cn/",
    }

    html = render_report.render_guide_cover(report, guide_rel=None, guide_status={"status": "html_guide_selected"})

    assert '<h1 id="guide-cover-title">杭州电子科技大学AI教育平台</h1>' in html
    assert '<p class="report-type">网站健康状况巡检报告</p>' in html
    assert "巡检网址" in html
    assert "杭州电子科技大学AI教育平台" in html
    assert "https://hdu.aiedulab.cn/" in html
    assert "网站名称" not in html
    assert "网站网址" not in html


def test_guide_cover_keeps_report_scope_without_score_semantics() -> None:
    import render_report

    html = render_report.render_guide_cover(
        minimal_report(),
        guide_rel="./html-assets/guide-cover.png",
        guide_status={"status": "generated"},
    )

    assert "报告口径" in html
    assert "评分语义" not in html


def test_report_title_uses_site_name_and_compact_report_type() -> None:
    import render_report

    report = minimal_report()
    report["report_identity"] = {
        "site_name": "杭州电子科技大学AI教育平台",
        "site_url": "https://hdu.aiedulab.cn/",
    }

    assert render_report.report_title(report) == "杭州电子科技大学AI教育平台｜网站健康巡检报告"


def test_multi_site_title_uses_concrete_site_scope() -> None:
    import render_report

    report = {
        "report_kind": "multi-site-overall",
        "generated_at": "2026-05-10T08:00:00+08:00",
        "overall_status": "warning",
        "score": 82,
        "site_results": [
            {"name": "门户站", "status": "healthy", "score": 96},
            {"name": "新闻网", "status": "warning", "score": 82},
            {"name": "服务大厅", "status": "warning", "score": 74},
            {"name": "缺地址站", "status": "unknown", "score": 0},
        ],
        "batch_metrics": {"site_count": 4},
        "summary": {"total_systems": 4},
        "priority_findings": [],
    }

    title = "门户站、新闻网、服务大厅等4个站点健康巡检总体报告"
    html = render_report.render_guide_cover(report, guide_rel=None, guide_status={"status": "html_guide_selected"})
    markdown = render_report.render_multi_site_overall_markdown(report)

    assert render_report.report_title(report) == title
    assert f'<h1 id="guide-cover-title">{title}</h1>' in html
    assert f"# {title}" in markdown
    assert "多站点网站健康巡检总体报告" not in html
    assert "多站点网站健康巡检总体报告" not in markdown


def test_report_identity_prefers_page_title_over_slug_system_id() -> None:
    import render_report

    report = minimal_report()
    report["systems"] = [{"system_id": "hdu-aiedulab-cn", "system_name": "hdu.aiedulab.cn", "status": "warning"}]
    report["module_reports"] = [
        {
            "report_type": "browser-inspection",
            "final_url": "https://hdu.aiedulab.cn/",
            "visited_pages": [
                {
                    "label": "public-root",
                    "url": "https://hdu.aiedulab.cn/",
                    "title": "杭州电子科技大学AI教育平台",
                }
            ],
        }
    ]

    identity = render_report.report_identity(report)

    assert identity["site_name"] == "杭州电子科技大学AI教育平台"
    assert identity["site_url"] == "https://hdu.aiedulab.cn/"


def test_reuse_existing_mode_uses_existing_valid_guide_image(tmp_path: Path, monkeypatch) -> None:
    import render_report

    report_path = write_report(tmp_path)
    guide_path = tmp_path / "ai-report-guide.png"
    guide_path.write_bytes(b"valid-existing-guide-image")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    old_argv = sys.argv
    sys.argv = [
        "render_report.py",
        "--report",
        str(report_path),
        "--out",
        str(tmp_path),
        "--guide-mode",
        "reuse-existing",
        "--no-load-env",
    ]
    try:
        render_report.main()
    finally:
        sys.argv = old_argv

    html = (tmp_path / "final-report.html").read_text(encoding="utf-8")
    status = json.loads((tmp_path / "ai-report-guide-status.json").read_text(encoding="utf-8"))

    assert status["status"] == "reused_existing"
    assert status["requires_user_api_key"] is False
    assert "./html-assets/guide-cover.png" in html
    assert '<div class="html-guide-visual"' not in html
    assert (tmp_path / "delivery" / "html-assets" / "guide-cover.png").exists()


def test_reuse_existing_mode_rejects_missing_guide_image(tmp_path: Path, monkeypatch) -> None:
    import render_report

    report_path = write_report(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    old_argv = sys.argv
    sys.argv = [
        "render_report.py",
        "--report",
        str(report_path),
        "--out",
        str(tmp_path),
        "--guide-mode",
        "reuse-existing",
        "--no-load-env",
    ]
    try:
        with pytest.raises(SystemExit) as exc:
            render_report.main()
    finally:
        sys.argv = old_argv

    status = json.loads((tmp_path / "ai-report-guide-status.json").read_text(encoding="utf-8"))

    assert exc.value.code != 0
    assert status["status"] == "needs_user_choice"
    assert status["reason"] == "missing"
    assert not (tmp_path / "final-report.html").exists()


def test_ai_image_mode_falls_back_to_html_guide_when_generation_fails(tmp_path: Path, monkeypatch) -> None:
    import render_report

    report_path = write_report(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "realvalidkeyabcdefghijklmnop")
    monkeypatch.setattr(render_report, "ensure_openai_python_package", lambda out_dir: True, raising=False)

    def fake_run_optional_with_error_file(command: list[str], out_dir: Path, error_filename: str) -> bool:
        (out_dir / error_filename).write_text("可选步骤执行失败\nnetwork unavailable\n", encoding="utf-8")
        return False

    monkeypatch.setattr(render_report, "run_optional_with_error_file", fake_run_optional_with_error_file)

    old_argv = sys.argv
    sys.argv = [
        "render_report.py",
        "--report",
        str(report_path),
        "--out",
        str(tmp_path),
        "--guide-mode",
        "ai-image",
        "--no-load-env",
    ]
    try:
        render_report.main()
    finally:
        sys.argv = old_argv

    html = (tmp_path / "final-report.html").read_text(encoding="utf-8")
    status = json.loads((tmp_path / "ai-report-guide-status.json").read_text(encoding="utf-8"))

    assert status["status"] == "failed"
    assert status["requires_user_api_key"] is False
    assert "html-guide-visual" in html
    assert "OPENAI_API_KEY" not in html
    assert "--skip-ai-guide-image" not in html


def test_ai_image_mode_installs_openai_dependency_before_generation_when_missing(tmp_path: Path, monkeypatch) -> None:
    import importlib.util
    import subprocess

    import render_report

    report_path = write_report(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "realvalidkeyabcdefghijklmnop")

    original_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str):
        if name == "openai":
            return None
        return original_find_spec(name)

    commands: list[list[str]] = []

    def fake_run(command: list[str], check=False, capture_output=True, text=True):
        commands.append(command)
        if len(command) >= 4 and command[:4] == [sys.executable, "-m", "pip", "install"]:
            return subprocess.CompletedProcess(command, 0, "installed openai", "")
        if command == [sys.executable, "-c", "import openai"]:
            return subprocess.CompletedProcess(command, 0, "", "")
        if any(str(part).endswith("generate_ai_report_guide_image.py") for part in command):
            (tmp_path / "ai-report-guide.png").write_bytes(b"generated guide image")
            return subprocess.CompletedProcess(command, 0, str(tmp_path / "ai-report-guide.png"), "")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    monkeypatch.setattr(render_report.subprocess, "run", fake_run)

    old_argv = sys.argv
    sys.argv = [
        "render_report.py",
        "--report",
        str(report_path),
        "--out",
        str(tmp_path),
        "--guide-mode",
        "ai-image",
        "--no-load-env",
        "--no-pdf",
    ]
    try:
        render_report.main()
    finally:
        sys.argv = old_argv

    status = json.loads((tmp_path / "ai-report-guide-status.json").read_text(encoding="utf-8"))

    assert any(command[:4] == [sys.executable, "-m", "pip", "install"] and "openai" in command[-1] for command in commands)
    assert status["status"] == "generated"
    assert (tmp_path / "delivery" / "html-assets" / "guide-cover.png").exists()


def test_ai_image_mode_stops_when_openai_dependency_install_fails(tmp_path: Path, monkeypatch) -> None:
    import importlib.util
    import subprocess

    import render_report

    report_path = write_report(tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-" + "realvalidkeyabcdefghijklmnop")

    original_find_spec = importlib.util.find_spec

    def fake_find_spec(name: str):
        if name == "openai":
            return None
        return original_find_spec(name)

    def fake_run(command: list[str], check=False, capture_output=True, text=True):
        if command[:4] == [sys.executable, "-m", "pip", "install"]:
            return subprocess.CompletedProcess(command, 1, "", "No matching distribution found for openai")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)
    monkeypatch.setattr(render_report.subprocess, "run", fake_run)

    old_argv = sys.argv
    sys.argv = [
        "render_report.py",
        "--report",
        str(report_path),
        "--out",
        str(tmp_path),
        "--guide-mode",
        "ai-image",
        "--no-load-env",
        "--no-pdf",
    ]
    try:
        with pytest.raises(SystemExit) as exc:
            render_report.main()
    finally:
        sys.argv = old_argv

    status = json.loads((tmp_path / "ai-report-guide-status.json").read_text(encoding="utf-8"))

    assert exc.value.code != 0
    assert status["status"] == "missing_dependency"
    assert status["requires_user_api_key"] is False
    assert status["error_file"] == "ai-report-guide-dependency-error.txt"
    assert not (tmp_path / "final-report.html").exists()
    assert not (tmp_path / "delivery").exists()


def test_render_report_generates_pdf_delivery_artifact(tmp_path: Path, monkeypatch) -> None:
    import render_report

    report_path = write_report(tmp_path)
    (tmp_path / "quality-audit.md").write_text("ok", encoding="utf-8")
    (tmp_path / "quality-audit.json").write_text('{"status": "pass"}', encoding="utf-8")
    (tmp_path / "score-audit.md").write_text("ok", encoding="utf-8")
    (tmp_path / "score-audit.json").write_text('{"status": "pass", "blocking_reasons": []}', encoding="utf-8")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fake_render_pdf_report(html_path: Path, pdf_path: Path) -> None:
        assert html_path.name == "final-report.html"
        pdf_path.write_bytes(b"%PDF-1.4\n% test pdf\n")

    monkeypatch.setattr(render_report, "render_pdf_report", fake_render_pdf_report, raising=False)

    old_argv = sys.argv
    sys.argv = [
        "render_report.py",
        "--report",
        str(report_path),
        "--out",
        str(tmp_path),
        "--guide-mode",
        "html-guide",
        "--no-load-env",
    ]
    try:
        render_report.main()
    finally:
        sys.argv = old_argv

    manifest = json.loads((tmp_path / "delivery-manifest.json").read_text(encoding="utf-8"))

    assert (tmp_path / "final-report.pdf").stat().st_size > 0
    assert (tmp_path / "delivery" / "final-report.pdf").stat().st_size > 0
    assert manifest["checks"]["official_pdf_exists"] is True
    assert manifest["checks"]["delivery_pdf_exists"] is True
    assert manifest["artifacts"]["pdf_report"]["exists"] is True
    assert manifest["artifacts"]["delivery_pdf_report"]["exists"] is True
    assert manifest["ready_to_deliver"] is True


def test_public_docs_do_not_ship_private_proxy_or_placeholder_key() -> None:
    root = Path(__file__).resolve().parents[1]
    docs = "\n".join(
        (root / path).read_text(encoding="utf-8")
        for path in [
            ".env.example",
            "SKILL.md",
            "README.md",
            "docs/configuration-and-security.md",
            "docs/quick-start.md",
            "docs/report-delivery.md",
            "docs/pipeline-architecture.md",
        ]
    )

    assert "https://token.aiedulab.cn" not in docs
    assert "sk-" + "your-key-here" not in docs
    assert ".env 中的 OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_IMAGE_MODEL" not in docs


def test_skill_requires_user_guide_choice_for_natural_language_invocation() -> None:
    root = Path(__file__).resolve().parents[1]
    skill = (root / "SKILL.md").read_text(encoding="utf-8")

    assert "自然语言调用前置确认" in skill
    assert "必须先停下来询问用户" in skill
    assert "不得直接运行 `run_health_inspection.py`" in skill
    assert "默认同意使用 `.env` 中的 API Key" in skill
    assert "没有明确选择就不能执行正式渲染" in skill


def test_image_generation_readiness_parser_and_decision() -> None:
    import check_image_generation_readiness as readiness

    output = """
apply_patch_freeform             under development  false
image_generation                 under development  true
shell_tool                       stable             true
"""

    assert readiness.parse_feature_status(output) == "enabled"
    assert readiness.parse_feature_status(output.replace("true", "false")) == "disabled"
    assert readiness.parse_feature_status("shell_tool stable true") == "missing"

    disabled = readiness.build_readiness(feature_status="disabled", api_key_configured=False)
    enabled = readiness.build_readiness(feature_status="enabled", api_key_configured=False)

    assert disabled["requires_user_api_key"] is True
    assert "codex features enable image_generation" in disabled["next_action"]
    assert enabled["can_try_builtin_imagegen"] is True
    assert enabled["requires_user_api_key"] is False


def test_windows_codex_command_prefers_executable_wrapper(monkeypatch) -> None:
    import check_image_generation_readiness as readiness

    monkeypatch.setattr(readiness.os, "name", "nt", raising=False)

    def fake_which(name: str) -> str | None:
        values = {
            "codex": r"C:\tools\codex",
            "codex.cmd": r"C:\tools\codex.cmd",
            "codex.exe": r"C:\tools\codex.exe",
        }
        return values.get(name)

    monkeypatch.setattr(readiness.shutil, "which", fake_which)

    assert readiness.codex_command() == [r"C:\tools\codex.cmd"]


def test_read_json_accepts_utf8_bom(tmp_path: Path) -> None:
    import health_common

    path = tmp_path / "final-report.json"
    path.write_text('{"overall_status": "warning"}', encoding="utf-8-sig")

    assert health_common.read_json(path)["overall_status"] == "warning"
