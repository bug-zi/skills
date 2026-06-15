from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from scoring_model import score_from_finding_clusters  # noqa: E402


def finding(**overrides) -> dict:
    base = {
        "system_id": "admin-platform",
        "system_name": "Admin Platform",
        "severity": "medium",
        "priority": "P2",
        "title": "Review needed",
        "technical_evidence": "evidence",
        "target": "https://example.test/admin",
        "business_impact": "Review needed.",
        "recommendation": "Review and fix.",
    }
    base.update(overrides)
    return base


def test_iteration_21_system_name_variants_share_one_root_cause_cluster() -> None:
    findings = [
        finding(system_id="Admin Platform", cluster_key="shared-rendering-root", target="https://example.test/a"),
        finding(system_id="admin-platform", cluster_key="shared-rendering-root", target="https://example.test/b"),
    ]

    assert score_from_finding_clusters(findings) == 95


def test_iteration_22_endpoint_method_query_hash_and_slash_are_one_request_root() -> None:
    findings = [
        finding(category="request-failure-endpoint", target="GET https://example.test/api/users?page=1#top"),
        finding(category="request-failure-endpoint", target="GET https://example.test/api/users/?page=2"),
        finding(category="request-failure-endpoint", target="https://example.test/api/users#retry"),
    ]

    assert score_from_finding_clusters(findings) == 94


def test_iteration_23_dynamic_api_ids_collapse_to_endpoint_family() -> None:
    findings = [
        finding(category="request-failure-endpoint", target="https://example.test/api/users/123/profile"),
        finding(category="request-failure-endpoint", target="https://example.test/api/users/456/profile"),
        finding(category="request-failure-endpoint", target="https://example.test/api/users/550e8400-e29b-41d4-a716-446655440000/profile"),
    ]

    assert score_from_finding_clusters(findings) == 94


def test_iteration_24_hashed_static_asset_failures_collapse_to_asset_family() -> None:
    findings = [
        finding(category="request-failure-endpoint", target="https://example.test/assets/chunk.1a2b3c4d.js"),
        finding(category="request-failure-endpoint", target="https://example.test/assets/chunk.9f8e7d6c.js"),
        finding(category="request-failure-endpoint", target="https://example.test/assets/chunk.abcdef12.js"),
    ]

    assert score_from_finding_clusters(findings) == 94


def test_iteration_25_manual_confirmed_confidence_zeroes_legacy_noise() -> None:
    findings = [
        finding(
            category="",
            finding_type="",
            confidence="manual-confirmed-normal",
            severity="critical",
            title="Login failed wording, but manual operator confirmed the site is normal",
        )
    ]

    assert score_from_finding_clusters(findings) == 100


def test_iteration_26_low_confidence_high_signal_is_review_not_high_confidence_penalty() -> None:
    findings = [
        finding(
            category="high-confidence-risk",
            severity="high",
            confidence="low",
            title="弱证据高风险提示",
            technical_evidence="single transient browser signal",
        )
    ]

    assert score_from_finding_clusters(findings) == 92


def test_iteration_27_legacy_http_response_titles_dedupe_by_canonical_endpoint() -> None:
    findings = [
        finding(title="浏览器捕获到异常 HTTP 响应", target="https://example.test/api/projects/123/detail"),
        finding(title="浏览器捕获到异常 HTTP 响应", target="https://example.test/api/projects/456/detail"),
    ]

    assert score_from_finding_clusters(findings) == 95


def test_iteration_28_score_breakdown_explains_residual_score_without_fake_100() -> None:
    import render_report

    html = render_report.render_score_breakdown({"score": 80, "priority_findings": [], "module_reports": []})

    assert "为什么是 80 分" in html
    assert "未形成可逐项扣分的问题簇" in html
    assert "为什么是 100 分" not in html


def test_iteration_29_default_impact_and_recommendation_are_actionable() -> None:
    import render_report

    impact = render_report.business_impact_for_finding(finding(business_impact="", recommendation=""))
    recommendation = render_report.recommendation_line_for_finding(finding(), "")

    assert "可能影响部分页面体验或需要后续排查" not in impact
    assert "影响范围尚未确认" in impact
    assert "补齐" in recommendation
    assert "请检查" not in recommendation


def test_iteration_31_report_normalization_rewrites_placeholder_impact_in_json() -> None:
    import render_report

    report = {
        "priority_findings": [
            finding(
                title="页面内容过短",
                business_impact="可能影响部分页面体验或需要后续排查。",
                recommendation="请检查。",
            )
        ],
        "module_reports": [
            {
                "report_type": "content-review",
                "findings": [
                    finding(
                        title="Review needed",
                        business_impact="Review needed.",
                        recommendation="Review and fix.",
                    )
                ],
            }
        ],
    }

    normalized = render_report.normalize_report_for_render(report)

    for item in [normalized["priority_findings"][0], normalized["module_reports"][0]["findings"][0]]:
        assert "可能影响部分页面体验或需要后续排查" not in item["business_impact"]
        assert "Review needed" not in item["business_impact"]
        assert "请检查" not in item["recommendation"]
        assert item["business_impact"]
        assert item["recommendation"]


def test_iteration_30_audit_detects_unclear_placeholder_phrases() -> None:
    import audit_report_quality

    phrases = audit_report_quality.unclear_placeholder_phrases(
        "可能影响部分页面体验或需要后续排查。请检查。建议尽快排查。"
    )

    assert "可能影响部分页面体验或需要后续排查" in phrases
    assert "请检查" in phrases
