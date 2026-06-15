from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))


def test_health_common_redacts_sensitive_data_without_mutating_input(tmp_path: Path) -> None:
    import health_common

    fake_openai_key = "sk-" + "real-secret-" + "abcdefghijklmnopqrstuvwxyz"
    payload = {
        "admin_credentials": {
            "username": "admin",
            "password": "Ab123456",
            "password_env": "WEBSITE_HEALTH_ADMIN_PASSWORD",
        },
        "headers": {"Authorization": "Bearer abcdefghijklmnopqrstuvwxyz123456"},
        "text": f"default password is Ab123456; token=abcdefghijklmnopqrstuvwxyz123456; OPENAI_API_KEY={fake_openai_key}",
    }

    redacted = health_common.scrub_sensitive_data(payload, explicit_values=["Ab123456"])

    assert payload["admin_credentials"]["password"] == "Ab123456"
    assert redacted["admin_credentials"]["username"] == "admin"
    assert redacted["admin_credentials"]["password_env"] == "WEBSITE_HEALTH_ADMIN_PASSWORD"
    serialized = json.dumps(redacted, ensure_ascii=False)
    assert "Ab123456" not in serialized
    assert "sk-real-secret" not in serialized
    assert "abcdefghijklmnopqrstuvwxyz123456" not in serialized

    out = tmp_path / "report.json"
    health_common.write_json(out, payload, explicit_sensitive_values=["Ab123456"])
    written = out.read_text(encoding="utf-8")
    assert "Ab123456" not in written
    assert "WEBSITE_HEALTH_ADMIN_PASSWORD" in written


def test_deep_browser_clean_text_redacts_supplied_password_and_tokens() -> None:
    import check_deep_browser

    fake_openai_key = "sk-" + "real-secret-" + "abcdefghijklmnopqrstuvwxyz"
    text = f"System default password Ab123456 and token=abcdefghijklmnopqrstuvwxyz123456 with {fake_openai_key}"

    cleaned = check_deep_browser.clean_text(text, secrets=["Ab123456"])

    assert "Ab123456" not in cleaned
    assert "sk-real-secret" not in cleaned
    assert "abcdefghijklmnopqrstuvwxyz123456" not in cleaned
    assert "[REDACTED" in cleaned


def test_rendered_route_utils_classifies_404_and_parameterized_routes() -> None:
    import rendered_route_utils

    assert rendered_route_utils.classify_rendered_page("/help", "404 页面未找到 返回首页", 200) == "in_app_404"
    assert rendered_route_utils.classify_rendered_page("/courses", "课程列表 课程中心", 200) == "rendered_ok"
    assert rendered_route_utils.route_requires_parameters("/courses/:courseId")
    assert rendered_route_utils.route_requires_parameters("/projects/{projectId}/detail")
    assert not rendered_route_utils.route_requires_parameters("/courses")

    script = 'const routes=[{path:"/help"},{path:"/datasets"},{path:"/courses/:courseId"},{path:"/api/private"}];'
    assert rendered_route_utils.extract_static_routes_from_script(script) == ["/help", "/datasets"]
    assert rendered_route_utils.extract_parameterized_routes_from_script(script) == ["/courses/:courseId"]


def test_deep_browser_seed_routes_cover_public_footer_and_admin_sections() -> None:
    import check_deep_browser

    routes = check_deep_browser.seed_route_candidates("https://example.com")
    paths = {Path(item["href"]).as_posix() if item["href"].startswith("/") else "/" + item["href"].split("/", 3)[-1] for item in routes}

    assert "/help" in paths
    assert "/privacy" in paths
    assert "/terms" in paths
    assert "/certificate" in paths
    assert "/system/settings" in paths


def test_login_status_from_signals_accepts_successful_auth_response() -> None:
    import check_deep_browser

    assert check_deep_browser.login_status_from_signals(
        username="admin",
        body_text="课程 教室 训练 实验 考试 资源",
        current_url="https://example.com/dashboard",
        has_login_form=False,
        auth_success_seen=True,
    )
    assert not check_deep_browser.login_status_from_signals(
        username="admin",
        body_text="登录 用户名 密码",
        current_url="https://example.com/login",
        has_login_form=True,
        auth_success_seen=True,
    )


def test_audit_flags_login_status_contradiction_and_json_secret(tmp_path: Path) -> None:
    import audit_report_quality

    report = {
        "overall_status": "warning",
        "score": 80,
        "priority_findings": [],
        "module_reports": [
            {
                "report_type": "browser-inspection",
                "login": {"status": "success", "note": "after login"},
                "visited_pages": [],
                "screenshots": [],
            }
        ],
    }
    (tmp_path / "final-report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    html = """
    <html><head><style>:root { --paper: #fff; }</style></head><body>
    <section class="guide-cover"></section>
    <nav class="report-nav"><a href="#x">x</a></nav>
    <section class="fold-section" id="x">登录状态未确认</section>
    </body></html>
    """
    (tmp_path / "final-report.html").write_text(html, encoding="utf-8")
    (tmp_path / "final-report.md").write_text("ok", encoding="utf-8")
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    fake_openai_key = "sk-" + "real-secret-" + "abcdefghijklmnopqrstuvwxyz"
    (delivery / "final-report.json").write_text(json.dumps({"leak": fake_openai_key}), encoding="utf-8")

    structured = audit_report_quality.audit_structured(tmp_path, iteration=10)

    assert structured["checks"]["login_status_consistent"] is False
    assert structured["checks"]["no_secret_like_text"] is False
    assert "login_status_consistent" in structured["failed_checks"]
    assert "no_secret_like_text" in structured["failed_checks"]


def test_audit_requires_non_empty_pdf_delivery_artifact(tmp_path: Path) -> None:
    import audit_report_quality

    report = {
        "overall_status": "warning",
        "score": 80,
        "priority_findings": [],
        "module_reports": [
            {
                "report_type": "browser-inspection",
                "login": {"status": "unknown", "note": "not checked"},
                "visited_pages": [],
                "screenshots": [],
            }
        ],
    }
    (tmp_path / "final-report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    html = """
    <html><head><style>:root { --paper: #fff; }</style></head><body>
    <section class="guide-cover"><div class="html-guide-visual">报告图文导览 阅读路径与重点证据</div></section>
    <nav class="report-nav">
      <a href="#a">1</a><a href="#b">2</a><a href="#c">3</a><a href="#d">4</a>
      <a href="#e">5</a><a href="#f">6</a><a href="#g">7</a><a href="#h">8</a>
    </nav>
    <button data-toggle-all>全部展开</button>
    <section class="fold-section" id="a"></section><section class="fold-section" id="b"></section>
    <section class="fold-section" id="c"></section><section class="fold-section" id="d"></section>
    <section class="fold-section" id="e"></section><section class="fold-section" id="f"></section>
    <section class="fold-section" id="g"></section><section class="fold-section" id="h"></section>
    </body></html>
    """
    (tmp_path / "final-report.html").write_text(html, encoding="utf-8")
    (tmp_path / "final-report.md").write_text("ok", encoding="utf-8")
    (tmp_path / "final-report.pdf").write_bytes(b"")
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    (delivery / "final-report.html").write_text(html, encoding="utf-8")
    (delivery / "final-report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    (delivery / "final-report.md").write_text("ok", encoding="utf-8")
    (delivery / "final-report.pdf").write_bytes(b"")
    (delivery / "html-assets").mkdir()
    (delivery / "screenshots").mkdir()

    structured = audit_report_quality.audit_structured(tmp_path, iteration=11)

    assert structured["checks"]["official_pdf_exists"] is False
    assert structured["checks"]["delivery_pdf_exists"] is False
    assert structured["status"] == "fail"
    assert "official_pdf_exists" in structured["failed_checks"]
    assert "delivery_pdf_exists" in structured["failed_checks"]


def test_cluster_metadata_controls_score_for_parameterized_boundaries() -> None:
    import merge_reports
    import render_report

    finding = {
        "title": "Some detail pages need business IDs",
        "target": "parameterized routes",
        "severity": "medium",
        "category": "parameterized-route-boundary",
        "confidence": "automation-boundary",
    }

    assert merge_reports.finding_cluster_key(finding)[1] == "parameterized-route-boundary"
    assert merge_reports.root_cause_penalty(finding) == 0
    assert render_report.finding_cluster_key(finding)[1] == "parameterized-route-boundary"
    assert render_report.root_cause_penalty(finding) == 0


def test_discovery_extracts_client_side_routes_from_bundle_text() -> None:
    import discover_site_pages

    html = '<html><script src="/assets/app.123.js"></script><script src="https://cdn.example.com/x.js"></script></html>'
    scripts = discover_site_pages.extract_script_sources(html, "https://example.com")

    assert scripts == ["https://example.com/assets/app.123.js"]

    js = 'createRouter([{path:"/"},{path:"/help"},{path:"/privacy"},{path:"/courses/:id"},{path:"/api/user"}])'
    routes = discover_site_pages.extract_spa_routes(js)

    assert routes["static"] == ["/", "/help", "/privacy"]
    assert routes["parameterized"] == ["/courses/:id"]
