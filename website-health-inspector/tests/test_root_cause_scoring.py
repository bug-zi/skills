from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import merge_reports  # noqa: E402
import render_report  # noqa: E402
from health_common import module_report  # noqa: E402
from scoring_model import health_status_from_score_and_findings  # noqa: E402


def finding(**overrides) -> dict:
    base = {
        "system_id": "admin-platform",
        "system_name": "管理平台",
        "severity": "medium",
        "priority": "P2",
        "title": "需要复核的页面异常",
        "business_impact": "可能影响部分页面体验。",
        "technical_evidence": "evidence",
        "target": "https://example.test/admin",
        "recommendation": "复核后处理。",
    }
    base.update(overrides)
    return base


def test_structured_cluster_key_scores_once_across_modules_and_pages() -> None:
    findings = [
        finding(
            id="content-001",
            title="内容检查发现页面异常",
            target="https://example.test/admin/home",
            cluster_key="shared-rendering-root-cause",
            technical_evidence="content module signal",
        ),
        finding(
            id="browser-001",
            title="浏览器检查发现同源页面异常",
            target="https://example.test/admin/settings",
            cluster_key="shared-rendering-root-cause",
            technical_evidence="browser module signal",
        ),
    ]

    assert merge_reports.score_from_finding_clusters(findings) == 95


def test_structured_automation_boundaries_do_not_reduce_main_health_score() -> None:
    findings = [
        finding(
            title="Login state signal missing",
            category="admin-login-unconfirmed",
            confidence="automation-boundary",
            technical_evidence="automation_login_status=unknown",
        ),
        finding(
            title="Protected route redirected while session is uncertain",
            category="automation-session-boundary",
            confidence="automation-boundary",
            technical_evidence="target=/admin/users actual=/login",
        ),
    ]

    assert merge_reports.score_from_finding_clusters(findings) == 100


def test_zero_penalty_automation_boundaries_are_healthy_status() -> None:
    findings = [
        finding(
            title="Login state signal missing",
            category="admin-login-unconfirmed",
            confidence="automation-boundary",
            technical_evidence="automation_login_status=unknown",
        ),
        finding(
            title="Protected route redirected while session is uncertain",
            category="automation-session-boundary",
            confidence="automation-boundary",
            technical_evidence="target=/admin/users actual=/login",
        ),
    ]

    assert merge_reports.score_from_finding_clusters(findings) == 100
    assert health_status_from_score_and_findings(100, findings, has_reports=True) == "healthy"


def test_manual_confirmed_normal_is_healthy_status() -> None:
    findings = [
        finding(
            title="人工复核已确认正常",
            category="manual-confirmed-normal",
            confidence="manual-confirmed-normal",
            severity="high",
        )
    ]

    assert merge_reports.score_from_finding_clusters(findings) == 100
    assert health_status_from_score_and_findings(100, findings, has_reports=True) == "healthy"


def test_positive_penalty_status_bands_are_not_healthy() -> None:
    warning_findings = [finding(category="request-failure-endpoint")]
    critical_findings = [finding(category="confirmed-outage", severity="critical")]
    low_score_findings = [
        finding(id=f"outage-{index}", category="confirmed-outage", severity="critical", target=f"https://example.test/{index}")
        for index in range(2)
    ]

    assert health_status_from_score_and_findings(94, warning_findings, has_reports=True) == "warning"
    assert health_status_from_score_and_findings(65, critical_findings, has_reports=True) == "critical"
    assert health_status_from_score_and_findings(30, low_score_findings, has_reports=True) == "critical"
    assert health_status_from_score_and_findings(80, [], has_reports=False) == "unknown"


def test_module_report_uses_effective_penalty_status_not_raw_finding_presence() -> None:
    report = module_report(
        "browser-inspection",
        [
            finding(
                category="admin-login-unconfirmed",
                confidence="automation-boundary",
                severity="low",
            )
        ],
        [{"system_id": "admin-platform", "system_name": "管理平台", "findings": 1}],
    )

    assert report["score"] == 100
    assert report["status"] == "healthy"


def test_request_failures_group_same_endpoint_but_score_distinct_endpoints() -> None:
    findings = [
        finding(
            title="浏览器资源请求失败",
            category="request-failure-endpoint",
            target="https://example.test/api/users?page=1",
            technical_evidence="GET failed to fetch",
        ),
        finding(
            title="浏览器资源请求失败",
            category="request-failure-endpoint",
            target="https://example.test/api/users?page=2",
            technical_evidence="GET failed to fetch",
        ),
        finding(
            title="浏览器资源请求失败",
            category="request-failure-endpoint",
            target="https://example.test/api/orders?page=1",
            technical_evidence="GET failed to fetch",
        ),
    ]

    assert merge_reports.score_from_finding_clusters(findings) == 88


def test_merge_report_status_follows_effective_score_not_module_warning(tmp_path: Path) -> None:
    module = module_report(
        "browser-inspection",
        [
            finding(
                category="admin-login-unconfirmed",
                confidence="automation-boundary",
                severity="low",
            )
        ],
        [{"system_id": "admin-platform", "system_name": "管理平台", "findings": 1}],
    )
    module["status"] = "warning"
    module["score"] = 95
    (tmp_path / "browser-inspection-report.json").write_text(
        __import__("json").dumps(module, ensure_ascii=False),
        encoding="utf-8",
    )

    merged = merge_reports.merge(tmp_path)

    assert merged["score"] == 100
    assert merged["overall_status"] == "healthy"
    assert merged["summary"]["healthy"] == 1
    assert merged["summary"]["warning"] == 0
    assert merged["systems"][0]["status"] == "healthy"


def test_merge_report_positive_penalty_is_warning_not_healthy(tmp_path: Path) -> None:
    module = module_report(
        "browser-inspection",
        [finding(category="module-runtime-failure", target="content-module")],
        [{"system_id": "admin-platform", "system_name": "管理平台", "findings": 1}],
    )
    (tmp_path / "browser-inspection-report.json").write_text(
        __import__("json").dumps(module, ensure_ascii=False),
        encoding="utf-8",
    )

    merged = merge_reports.merge(tmp_path)

    assert merged["score"] == 92
    assert merged["overall_status"] == "warning"
    assert merged["summary"]["warning"] == 1
    assert merged["systems"][0]["status"] == "warning"


def test_render_score_breakdown_uses_same_penalties_as_merged_score() -> None:
    findings = [
        finding(
            title="Footer link issue",
            category="public-footer-404",
            target="https://example.test/help",
            technical_evidence="rendered_status=in_app_404",
        )
    ]
    merged_score = merge_reports.score_from_finding_clusters(findings)
    report = {"score": merged_score, "priority_findings": findings, "module_reports": []}

    rendered_penalty = sum(row["penalty"] for row in render_report.score_breakdown(report))

    assert rendered_penalty == 100 - merged_score
