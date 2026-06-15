from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))


def finding(**overrides) -> dict:
    base = {
        "id": "finding-001",
        "system_id": "admin",
        "system_name": "管理平台",
        "severity": "medium",
        "priority": "P2",
        "title": "接口请求失败",
        "category": "request-failure-endpoint",
        "business_impact": "影响范围尚未确认。",
        "technical_evidence": "HTTP 500",
        "target": "https://example.test/api/users",
        "recommendation": "补齐复测证据。",
    }
    base.update(overrides)
    return base


def write_report(tmp_path: Path, *, score: int, findings: list[dict]) -> Path:
    report = {
        "generated_at": "2026-05-14T10:00:00+08:00",
        "overall_status": "warning",
        "score": score,
        "executive_summary": "测试报告",
        "summary": {"total_systems": 1, "healthy": 0, "warning": 1, "critical": 0, "unknown": 0},
        "systems": [{"system_id": "admin", "system_name": "管理平台", "status": "warning"}],
        "priority_findings": findings,
        "module_reports": [],
        "artifacts": {},
    }
    path = tmp_path / "final-report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_status_report(tmp_path: Path, *, score: int, status: str, findings: list[dict]) -> Path:
    report_path = write_report(tmp_path, score=score, findings=findings)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["overall_status"] = status
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


def test_score_audit_passes_high_score_without_duplicate_suspicions(tmp_path: Path) -> None:
    import audit_score_reasonableness

    report_path = write_report(
        tmp_path,
        score=92,
        findings=[finding(category="module-runtime-failure", title="内容模块运行失败", target="content-module")],
    )

    result = audit_score_reasonableness.audit_report(report_path, tmp_path, threshold=60)

    assert result["status"] == "pass"
    assert result["blocking_reasons"] == []
    assert result["recomputed_score"] == 92
    assert (tmp_path / "score-audit.json").exists()
    assert (tmp_path / "score-audit.md").exists()


def test_score_audit_blocks_low_score(tmp_path: Path) -> None:
    import audit_score_reasonableness

    report_path = write_report(
        tmp_path,
        score=53,
        findings=[
            finding(id=f"outage-{index}", category="confirmed-outage", severity="critical", target=f"https://example.test/down-{index}")
            for index in range(2)
        ],
    )

    result = audit_score_reasonableness.audit_report(report_path, tmp_path, threshold=60)

    assert result["status"] == "blocked"
    assert "low_score_requires_review" in result["blocking_reasons"]


def test_score_audit_detects_dynamic_endpoint_duplicate_suspicions(tmp_path: Path) -> None:
    import audit_score_reasonableness

    findings = [
        finding(id="u1", target="https://example.test/api/users/123/profile"),
        finding(id="u2", target="https://example.test/api/users/456/profile"),
        finding(id="u3", target="https://example.test/api/users/789/profile"),
    ]
    report_path = write_report(tmp_path, score=82, findings=findings)

    result = audit_score_reasonableness.audit_report(report_path, tmp_path, threshold=60)

    assert result["status"] == "blocked"
    assert "duplicate_penalty_suspected" in result["blocking_reasons"]
    suspicion = result["duplicate_suspicions"][0]
    assert suspicion["current_penalty"] == 18
    assert suspicion["suggested_single_penalty"] == 6
    assert suspicion["suspected_over_penalty"] == 12
    assert "cluster_key" in suspicion["suggested_merge_fields"]


def test_score_audit_blocks_score_mismatch(tmp_path: Path) -> None:
    import audit_score_reasonableness

    report_path = write_report(tmp_path, score=51, findings=[finding(category="module-runtime-failure", target="content")])

    result = audit_score_reasonableness.audit_report(report_path, tmp_path, threshold=60)

    assert result["status"] == "blocked"
    assert "score_mismatch" in result["blocking_reasons"]
    assert result["recomputed_score"] == 92


def test_score_audit_blocks_status_score_mismatch(tmp_path: Path) -> None:
    import audit_score_reasonableness

    report_path = write_status_report(
        tmp_path,
        score=100,
        status="warning",
        findings=[finding(category="admin-login-unconfirmed", confidence="automation-boundary", severity="low")],
    )

    result = audit_score_reasonableness.audit_report(report_path, tmp_path, threshold=60)

    assert result["status"] == "blocked"
    assert result["reported_status"] == "warning"
    assert result["expected_status"] == "healthy"
    assert "status_score_mismatch" in result["blocking_reasons"]
    assert result["status_reasons"]


def test_render_report_refuses_status_score_mismatch_even_with_score_audit(tmp_path: Path, monkeypatch) -> None:
    import audit_score_reasonableness
    import render_report

    report_path = write_status_report(
        tmp_path,
        score=100,
        status="warning",
        findings=[finding(category="admin-login-unconfirmed", confidence="automation-boundary", severity="low")],
    )
    audit_score_reasonableness.audit_report(report_path, tmp_path, threshold=60)
    monkeypatch.setattr(render_report, "run_optional", lambda command: True)

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
        "--no-pdf",
    ]
    try:
        with pytest.raises(SystemExit) as exc:
            render_report.main()
    finally:
        sys.argv = old_argv

    assert "score-audit" in str(exc.value)
    assert not (tmp_path / "final-report.html").exists()


def test_score_audit_cli_exits_nonzero_when_blocked(tmp_path: Path) -> None:
    import audit_score_reasonableness

    report_path = write_report(tmp_path, score=53, findings=[finding(category="confirmed-outage", severity="critical", target="x")])
    old_argv = sys.argv
    sys.argv = [
        "audit_score_reasonableness.py",
        "--report",
        str(report_path),
        "--out",
        str(tmp_path),
        "--threshold",
        "60",
    ]
    try:
        with pytest.raises(SystemExit) as exc:
            audit_score_reasonableness.main()
    finally:
        sys.argv = old_argv

    assert exc.value.code == 1


def test_inspect_sites_runs_score_audit_between_merge_and_render(tmp_path: Path, monkeypatch) -> None:
    import inspect_sites

    calls: list[str] = []
    inventory = tmp_path / "inventory.normalized.json"
    inventory.write_text(json.dumps({"systems": []}), encoding="utf-8")

    def fake_run_script(name: str, args: list[str]) -> int:
        calls.append(name)
        if name == "merge_reports.py":
            (tmp_path / "final-report.json").write_text("{}", encoding="utf-8")
        return 0

    monkeypatch.setattr(inspect_sites, "run_script", fake_run_script)
    old_argv = sys.argv
    sys.argv = [
        "inspect_sites.py",
        "--inventory",
        str(inventory),
        "--out",
        str(tmp_path),
        "--checks",
        "merge,render",
        "--guide-mode",
        "html-guide",
    ]
    try:
        inspect_sites.main()
    finally:
        sys.argv = old_argv

    assert calls == ["merge_reports.py", "audit_score_reasonableness.py", "render_report.py"]


def test_run_health_inspection_runs_score_audit_before_render(tmp_path: Path, monkeypatch) -> None:
    import run_health_inspection

    calls: list[str] = []

    def fake_run_step(label: str, script_name: str, args: list[str]) -> None:
        calls.append(script_name)

    monkeypatch.setattr(run_health_inspection, "require_pdf_runtime", lambda: None)
    monkeypatch.setattr(run_health_inspection, "run_step", fake_run_step)
    monkeypatch.setattr(run_health_inspection, "validate_formal_report", lambda out_dir: None)

    old_argv = sys.argv
    sys.argv = [
        "run_health_inspection.py",
        "--url",
        "https://example.test",
        "--out",
        str(tmp_path),
        "--guide-mode",
        "html-guide",
        "--no-quality-audit",
    ]
    try:
        run_health_inspection.main()
    finally:
        sys.argv = old_argv

    assert calls == [
        "build_adhoc_inventory.py",
        "inspect_sites.py",
        "audit_score_reasonableness.py",
        "render_report.py",
    ]


def test_render_report_refuses_low_score_without_passed_score_audit(tmp_path: Path, monkeypatch) -> None:
    import render_report

    report_path = write_report(tmp_path, score=53, findings=[finding(category="confirmed-outage", severity="critical", target="x")])
    monkeypatch.setattr(render_report, "run_optional", lambda command: True)

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
        "--no-pdf",
    ]
    try:
        with pytest.raises(SystemExit) as exc:
            render_report.main()
    finally:
        sys.argv = old_argv

    assert "score-audit" in str(exc.value)
    assert not (tmp_path / "final-report.html").exists()


def test_render_report_allows_approved_low_score_and_records_note(tmp_path: Path, monkeypatch) -> None:
    import render_report

    report_path = write_report(tmp_path, score=53, findings=[finding(category="confirmed-outage", severity="critical", target="x")])
    (tmp_path / "score-audit.json").write_text(
        json.dumps({"status": "blocked", "blocking_reasons": ["low_score_requires_review"], "score": 53}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "score-audit.md").write_text("blocked", encoding="utf-8")
    monkeypatch.setattr(render_report, "run_optional", lambda command: True)

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
        "--no-pdf",
        "--score-review-approved",
        "--score-review-note",
        "人工确认低分合理，未发现重复扣分",
    ]
    try:
        render_report.main()
    finally:
        sys.argv = old_argv

    rendered = json.loads(report_path.read_text(encoding="utf-8"))
    manifest = json.loads((tmp_path / "delivery-manifest.json").read_text(encoding="utf-8"))
    assert rendered["score_review"]["approved"] is True
    assert "人工确认低分合理" in rendered["score_review"]["note"]
    assert manifest["score_review"]["approved"] is True
    assert "score_audit" in manifest["artifacts"]


def test_render_report_does_not_allow_approval_to_bypass_duplicate_penalties(tmp_path: Path, monkeypatch) -> None:
    import render_report

    report_path = write_report(tmp_path, score=82, findings=[finding(target="https://example.test/api/users/123")])
    (tmp_path / "score-audit.json").write_text(
        json.dumps({"status": "blocked", "blocking_reasons": ["duplicate_penalty_suspected"], "score": 82}, ensure_ascii=False),
        encoding="utf-8",
    )
    (tmp_path / "score-audit.md").write_text("blocked", encoding="utf-8")
    monkeypatch.setattr(render_report, "run_optional", lambda command: True)

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
        "--no-pdf",
        "--score-review-approved",
        "--score-review-note",
        "人工确认低分合理，未发现重复扣分",
    ]
    try:
        with pytest.raises(SystemExit) as exc:
            render_report.main()
    finally:
        sys.argv = old_argv

    assert "cannot bypass" in str(exc.value)
    assert not (tmp_path / "final-report.html").exists()


def test_pipeline_manual_approval_only_allows_low_score_review(tmp_path: Path) -> None:
    import inspect_sites
    import run_health_inspection

    (tmp_path / "score-audit.json").write_text(
        json.dumps({"status": "blocked", "blocking_reasons": ["low_score_requires_review"]}, ensure_ascii=False),
        encoding="utf-8",
    )
    assert inspect_sites.score_audit_allows_manual_approval(tmp_path) is True
    assert run_health_inspection.score_audit_allows_manual_approval(tmp_path) is True

    (tmp_path / "score-audit.json").write_text(
        json.dumps(
            {"status": "blocked", "blocking_reasons": ["low_score_requires_review", "duplicate_penalty_suspected"]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    assert inspect_sites.score_audit_allows_manual_approval(tmp_path) is False
    assert run_health_inspection.score_audit_allows_manual_approval(tmp_path) is False
