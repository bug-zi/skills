from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))


def write_minimal_html(run_dir: Path) -> None:
    html = """
    <html><head><style>:root { --paper: #fff; }</style></head><body>
    <section class="guide-cover"><div class="html-guide-visual">Guide</div></section>
    <nav class="report-nav">
      <a href="#a">1</a><a href="#b">2</a><a href="#c">3</a><a href="#d">4</a>
      <a href="#e">5</a><a href="#f">6</a><a href="#g">7</a><a href="#h">8</a>
    </nav>
    <button data-toggle-all>all</button>
    <section class="fold-section" id="a"></section><section class="fold-section" id="b"></section>
    <section class="fold-section" id="c"></section><section class="fold-section" id="d"></section>
    <section class="fold-section" id="e"></section><section class="fold-section" id="f"></section>
    <section class="fold-section" id="g"></section><section class="fold-section" id="h"></section>
    </body></html>
    """
    (run_dir / "final-report.html").write_text(html, encoding="utf-8")
    (run_dir / "final-report.md").write_text("ok", encoding="utf-8")


def write_minimal_report(run_dir: Path) -> Path:
    report = {
        "overall_status": "warning",
        "score": 80,
        "priority_findings": [],
        "module_reports": [],
    }
    path = run_dir / "final-report.json"
    path.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return path


def test_inspect_sites_records_failed_noncritical_module_and_continues(tmp_path: Path, monkeypatch) -> None:
    import inspect_sites

    inventory = tmp_path / "inventory.normalized.json"
    inventory.write_text(json.dumps({"systems": []}), encoding="utf-8")

    def fake_run_script(name: str, args: list[str]) -> int:
        if name == "check_content.py":
            return 7
        if name == "merge_reports.py":
            out_dir = Path(args[args.index("--in") + 1])
            module_path = out_dir / "content-review-report.json"
            report = {
                "overall_status": "warning",
                "score": 90,
                "priority_findings": [],
                "module_reports": [json.loads(module_path.read_text(encoding="utf-8"))],
            }
            (out_dir / "final-report.json").write_text(json.dumps(report), encoding="utf-8")
            return 0
        if name == "audit_score_reasonableness.py":
            return 0
        raise AssertionError(name)

    monkeypatch.setattr(inspect_sites, "run_script", fake_run_script)
    old_argv = sys.argv
    sys.argv = [
        "inspect_sites.py",
        "--inventory",
        str(inventory),
        "--out",
        str(tmp_path),
        "--checks",
        "content,merge",
    ]
    try:
        inspect_sites.main()
    finally:
        sys.argv = old_argv

    final_report = json.loads((tmp_path / "final-report.json").read_text(encoding="utf-8"))
    failed_module = final_report["module_reports"][0]
    assert failed_module["report_type"] == "content-review"
    assert "runtime" in failed_module["findings"][0]["id"]
    assert "exited with code 7" in failed_module["findings"][0]["technical_evidence"]


def test_inspect_sites_merge_failure_exits_nonzero(tmp_path: Path, monkeypatch) -> None:
    import inspect_sites

    inventory = tmp_path / "inventory.normalized.json"
    inventory.write_text(json.dumps({"systems": []}), encoding="utf-8")
    monkeypatch.setattr(inspect_sites, "run_script", lambda name, args: 5)
    old_argv = sys.argv
    sys.argv = [
        "inspect_sites.py",
        "--inventory",
        str(inventory),
        "--out",
        str(tmp_path),
        "--checks",
        "merge",
    ]
    try:
        with pytest.raises(SystemExit) as exc:
            inspect_sites.main()
    finally:
        sys.argv = old_argv

    assert exc.value.code != 0
    assert not (tmp_path / "final-report.json").exists()


def test_audit_cli_exits_nonzero_on_failed_gate_and_refreshes_delivery(tmp_path: Path) -> None:
    import audit_report_quality

    write_minimal_report(tmp_path)
    write_minimal_html(tmp_path)
    (tmp_path / "delivery").mkdir()
    (tmp_path / "delivery" / "final-report.html").write_text("broken", encoding="utf-8")
    (tmp_path / "delivery-manifest.json").write_text(
        json.dumps({"checks": {}, "artifacts": {}, "ready_to_deliver": True}),
        encoding="utf-8",
    )

    old_argv = sys.argv
    sys.argv = [
        "audit_report_quality.py",
        "--run-dir",
        str(tmp_path),
        "--iteration",
        "1",
        "--out",
        str(tmp_path / "quality-audit.md"),
    ]
    try:
        with pytest.raises(SystemExit) as exc:
            audit_report_quality.main()
    finally:
        sys.argv = old_argv

    assert exc.value.code == 1
    assert (tmp_path / "quality-audit.json").exists()
    manifest = json.loads((tmp_path / "delivery-manifest.json").read_text(encoding="utf-8"))
    assert manifest["checks"]["quality_audit_exists"] is True
    assert manifest["checks"]["quality_audit_json_exists"] is True
    assert manifest["quality_gate_status"] == "fail"
    assert manifest["ready_to_deliver"] is False


def test_audit_structured_treats_current_run_audit_outputs_as_present(tmp_path: Path) -> None:
    import audit_report_quality

    write_minimal_report(tmp_path)
    write_minimal_html(tmp_path)
    (tmp_path / "final-report.pdf").write_bytes(b"%PDF-1.4\n")
    (tmp_path / "delivery-manifest.json").write_text("{}", encoding="utf-8")
    (tmp_path / "delivery-manifest.md").write_text("manifest", encoding="utf-8")
    delivery = tmp_path / "delivery"
    delivery.mkdir()
    (delivery / "final-report.html").write_text(
        (tmp_path / "final-report.html").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (delivery / "final-report.pdf").write_bytes(b"%PDF-1.4\n")
    (delivery / "final-report.json").write_text((tmp_path / "final-report.json").read_text(encoding="utf-8"), encoding="utf-8")
    (delivery / "final-report.md").write_text("ok", encoding="utf-8")
    (delivery / "html-assets").mkdir()
    (delivery / "screenshots").mkdir()

    structured = audit_report_quality.audit_structured(
        tmp_path,
        iteration=1,
        expected_quality_outputs=[
            tmp_path / "quality-audit.md",
            tmp_path / "quality-audit.json",
        ],
    )

    assert structured["checks"]["quality_audit_exists"] is True
    assert structured["checks"]["quality_audit_json_exists"] is True


def test_audit_does_not_warn_for_missing_html_fallback_when_ai_guide_exists(tmp_path: Path) -> None:
    import audit_report_quality

    write_minimal_report(tmp_path)
    write_minimal_html(tmp_path)
    html = (tmp_path / "final-report.html").read_text(encoding="utf-8")
    html = html.replace('<div class="html-guide-visual">Guide</div>', '<img class="guide-cover-image" src="./html-assets/ai-report-guide.png" alt="GPT 生成的总报告文字导览架构图">')
    (tmp_path / "final-report.html").write_text(html, encoding="utf-8")

    structured = audit_report_quality.audit_structured(tmp_path, iteration=1)

    assert structured["checks"]["guide_cover_ready"] is True
    assert structured["checks"]["html_guide_fallback_present"] is True


def test_render_sync_delivery_package_handles_deep_paths(tmp_path: Path) -> None:
    import render_report

    (tmp_path / "final-report.html").write_text('<img src="./html-assets/guide-cover.png">', encoding="utf-8")
    (tmp_path / "final-report.pdf").write_bytes(b"%PDF-1.4\n")
    (tmp_path / "final-report.md").write_text("ok", encoding="utf-8")
    (tmp_path / "final-report.json").write_text("{}", encoding="utf-8")
    (tmp_path / "delivery-manifest.md").write_text("manifest", encoding="utf-8")
    (tmp_path / "delivery-manifest.json").write_text("{}", encoding="utf-8")
    html_assets = tmp_path / "html-assets"
    screenshots = tmp_path / "screenshots"
    html_assets.mkdir()
    screenshots.mkdir()
    (html_assets / "guide-cover.png").write_bytes(b"guide")
    deep_name = "screenshot-" + "x" * 120 + ".png"
    (screenshots / deep_name).write_bytes(b"shot")

    delivery = render_report.sync_delivery_package(tmp_path)

    assert (delivery / "html-assets" / "guide-cover.png").read_bytes() == b"guide"
    copied = list((delivery / "screenshots").glob("*.png"))
    assert len(copied) == 1
    assert copied[0].read_bytes() == b"shot"
    assert len(copied[0].name) < len(deep_name)


def test_audit_reads_utf8_bom_json(tmp_path: Path) -> None:
    import audit_report_quality

    report = {
        "overall_status": "warning",
        "score": 80,
        "priority_findings": [],
        "module_reports": [],
    }
    (tmp_path / "final-report.json").write_text(json.dumps(report), encoding="utf-8-sig")
    write_minimal_html(tmp_path)

    structured = audit_report_quality.audit_structured(tmp_path, iteration=1)

    assert structured["overall_status"] == "warning"


def test_render_pdf_report_fails_without_browser_instead_of_placeholder(tmp_path: Path, monkeypatch) -> None:
    import render_report

    html_path = tmp_path / "final-report.html"
    pdf_path = tmp_path / "final-report.pdf"
    html_path.write_text("<html><body>ok</body></html>", encoding="utf-8")
    original_exists = render_report.Path.exists

    def fake_exists(self: Path) -> bool:
        text = str(self)
        if "Google\\Chrome" in text or "Microsoft\\Edge" in text:
            return False
        return original_exists(self)

    monkeypatch.delenv("CHROME_PATH", raising=False)
    monkeypatch.setattr(render_report.Path, "exists", fake_exists)

    with pytest.raises(SystemExit) as exc:
        render_report.render_pdf_report(html_path, pdf_path)

    assert exc.value.code != 0
    assert not pdf_path.exists()
    assert (tmp_path / "pdf-generation-error.txt").is_file()


def test_render_manifest_not_ready_until_quality_gate_passes(tmp_path: Path, monkeypatch) -> None:
    import render_report
    from test_api_key_fallback_workflow import write_report

    report_path = write_report(tmp_path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fake_render_pdf_report(html_path: Path, pdf_path: Path) -> None:
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
    assert manifest["package_complete"] is True
    assert manifest["quality_gate_status"] == "missing"
    assert manifest["ready_to_deliver"] is False


def test_run_health_inspection_forwards_reuse_existing_guide_mode(tmp_path: Path, monkeypatch) -> None:
    import run_health_inspection

    calls: list[tuple[str, str, list[str]]] = []

    def fake_run_step(label: str, script_name: str, args: list[str]) -> None:
        calls.append((label, script_name, args))

    monkeypatch.setattr(run_health_inspection, "require_pdf_runtime", lambda: None)
    monkeypatch.setattr(run_health_inspection, "run_step", fake_run_step)
    monkeypatch.setattr(run_health_inspection, "validate_formal_report", lambda out_dir: None)

    old_argv = sys.argv
    sys.argv = [
        "run_health_inspection.py",
        "--url",
        "https://example.com/admin",
        "--out",
        str(tmp_path),
        "--guide-mode",
        "reuse-existing",
        "--no-quality-audit",
    ]
    try:
        run_health_inspection.main()
    finally:
        sys.argv = old_argv

    render_call = next(args for _, script_name, args in calls if script_name == "render_report.py")
    assert "--guide-mode" in render_call
    assert render_call[render_call.index("--guide-mode") + 1] == "reuse-existing"
    assert "--skip-ai-guide-image" not in render_call


def test_runtime_dependency_checks_report_missing_optional_openpyxl(monkeypatch) -> None:
    import builtins
    import check_runtime_dependencies

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "openpyxl":
            raise ImportError("missing openpyxl")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    optional = check_runtime_dependencies.check_openpyxl(required=False)
    required = check_runtime_dependencies.check_openpyxl(required=True)

    assert optional["ok"] is True
    assert optional["required"] is False
    assert required["ok"] is False
    assert "pip install openpyxl" in required["message"]
