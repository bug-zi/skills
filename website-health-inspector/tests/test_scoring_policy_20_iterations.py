from __future__ import annotations

import sys
from pathlib import Path

import pytest


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


SCENARIOS = [
    pytest.param(
        [
            finding(cluster_key="shared-root", target="https://example.test/a"),
            finding(cluster_key="shared-root", target="https://example.test/b"),
        ],
        95,
        id="iteration-01-structured-root-dedupes-across-pages",
    ),
    pytest.param(
        [
            finding(category="request-failure-endpoint", title="request failed", target="https://example.test/api/users?page=1"),
            finding(category="request-failure-endpoint", title="request failed", target="https://example.test/api/users?page=2"),
            finding(category="request-failure-endpoint", title="request failed", target="https://example.test/api/orders?page=1"),
        ],
        88,
        id="iteration-02-endpoint-normalization-strips-query",
    ),
    pytest.param(
        [
            finding(category="admin-login-unconfirmed", confidence="automation-boundary"),
            finding(category="automation-session-boundary", confidence="automation-boundary"),
        ],
        100,
        id="iteration-03-automation-login-and-session-boundaries-are-zero",
    ),
    pytest.param(
        [finding(category="parameterized-route-boundary", confidence="automation-boundary")],
        100,
        id="iteration-04-parameterized-business-routes-are-zero",
    ),
    pytest.param(
        [
            finding(title="body too short", technical_evidence="body_length=12, min_length=500"),
            finding(title="another body too short", technical_evidence="body_length=14, min_length=500"),
        ],
        98,
        id="iteration-05-spa-text-checks-are-low-weight-once",
    ),
    pytest.param(
        [finding(category="module-coverage-gap", title="host module missing")],
        95,
        id="iteration-06-single-coverage-gap-is-five-points",
    ),
    pytest.param(
        [
            finding(category="module-coverage-gap", title="host missing"),
            finding(category="module-coverage-gap", title="browser missing"),
            finding(category="module-coverage-gap", title="content missing"),
            finding(category="module-coverage-gap", title="function missing"),
        ],
        90,
        id="iteration-07-coverage-gaps-are-capped",
    ),
    pytest.param(
        [finding(category="module-runtime-failure", title="content module exited")],
        92,
        id="iteration-08-module-runtime-failure-is-stronger-than-coverage-gap",
    ),
    pytest.param(
        [finding(category="high-confidence-risk", severity="high", environment="dev")],
        88,
        id="iteration-09-non-production-high-risk-is-reduced",
    ),
    pytest.param(
        [finding(category="confirmed-outage", severity="critical", environment="prod", system_priority="critical", core_path=True)],
        65,
        id="iteration-10-production-critical-core-outage-stays-severe",
    ),
    pytest.param(
        [finding(category="review-needed", severity="medium", confidence="confirmed")],
        92,
        id="iteration-11-confirmed-medium-review-is-weighted-up",
    ),
    pytest.param(
        [finding(category="review-needed", severity="medium", confidence="low")],
        97,
        id="iteration-12-low-confidence-review-is-weighted-down",
    ),
    pytest.param(
        [finding(category="manual-confirmed-normal", title="login failed wording but manual check passed", severity="high")],
        100,
        id="iteration-13-manual-confirmed-normal-zeroes-noisy-findings",
    ),
    pytest.param(
        [
            finding(category="auth-refresh", target="https://example.test/auth/refresh", technical_evidence="HTTP 401"),
            finding(category="auth-refresh", target="https://example.test/auth/refresh?retry=1", technical_evidence="HTTP 401"),
        ],
        94,
        id="iteration-14-auth-refresh-retries-score-once",
    ),
    pytest.param(
        [finding(category="protected-route-login-redirect", confidence="confirmed", title="protected route redirects after confirmed login")],
        92,
        id="iteration-15-confirmed-protected-route-redirect-is-real-review",
    ),
    pytest.param(
        [
            finding(category="public-footer-404", target="https://example.test/help"),
            finding(category="public-footer-404", target="https://example.test/privacy"),
        ],
        94,
        id="iteration-16-public-footer-404-family-scores-once",
    ),
    pytest.param(
        [finding(category="tls-expiry", technical_evidence="tls_expiry_days=20")],
        95,
        id="iteration-17-tls-expiry-within-thirty-days-is-warning",
    ),
    pytest.param(
        [finding(category="tls-expiry", technical_evidence="tls_expiry_days=5")],
        88,
        id="iteration-18-tls-expiry-within-seven-days-is-urgent",
    ),
    pytest.param(
        [finding(category="tls-expiry", technical_evidence="tls_expiry_days=-1")],
        78,
        id="iteration-19-expired-tls-is-high-confidence-risk",
    ),
    pytest.param(
        [
            finding(category="slow-page", target=f"https://example.test/page-{index}", technical_evidence="open_time_ms=4200")
            for index in range(5)
        ],
        95,
        id="iteration-20-repeated-slow-pages-have-family-cap",
    ),
]


@pytest.mark.parametrize(("findings", "expected_score"), SCENARIOS)
def test_scoring_policy_20_iteration_matrix(findings: list[dict], expected_score: int) -> None:
    assert score_from_finding_clusters(findings) == expected_score
