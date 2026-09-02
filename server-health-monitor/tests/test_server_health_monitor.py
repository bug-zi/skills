import json
import importlib.util
import os
import subprocess
import sys
import threading
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from openpyxl import Workbook


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "run_server_health_monitor.py"
COLLECTOR = ROOT / "scripts" / "collect_doops_inventory.py"
TEXT_CHECK = ROOT / "scripts" / "check_text_integrity.py"
SAMPLE = ROOT / "assets" / "samples" / "zheyin-inventory.example.json"
INSTALLED_SKILL = Path("C:/Users/Administrator/.codex/skills/server-health-monitor")
SYNCED_FILES = [
    "SKILL.md",
    "agents/openai.yaml",
    "references/inventory-schema.md",
    "references/report-quality.md",
    "references/doops-monitoring.md",
    "scripts/check_text_integrity.py",
    "scripts/collect_doops_inventory.py",
    "scripts/run_server_health_monitor.py",
    "tests/test_server_health_monitor.py",
]


def load_runner_module(name="run_server_health_monitor_test"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_collector_module(name="collect_doops_inventory_test"):
    spec = importlib.util.spec_from_file_location(name, COLLECTOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_no_placeholder_text(text):
    assert "?" * 2 not in text
    assert "?" * 4 not in text


def write_fake_doops(tmp_path, body):
    fake_doops = tmp_path / "fake_doops.py"
    fake_doops.write_text(body, encoding="utf-8")
    fake_doops_cmd = tmp_path / "fake_doops.cmd"
    fake_doops_cmd.write_text(f'@echo off\r\n"{sys.executable}" "{fake_doops}" %*\r\n', encoding="utf-8")
    return fake_doops_cmd


def write_excel_inventory(path, rows):
    wb = Workbook()
    ws = wb.active
    ws.title = "服务器帐户和密码"
    ws.append(["业务系统名称", "IP地址", "操作系统", "服务器初始帐户/密码", "服务器描述", "日期", "是否存活"])
    for row in rows:
        ws.append(row)
    wb.save(path)


def subprocess_env(**overrides):
    return {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8", **overrides}


def test_sample_inventory_generates_delivery_reports(tmp_path):
    out_dir = tmp_path / "run"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--inventory",
            str(SAMPLE),
            "--out",
            str(out_dir),
            "--offline",
            "--guide-mode",
            "html-guide",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    delivery = out_dir / "delivery"
    assert (delivery / "final-report.html").is_file()
    assert (delivery / "final-report.pdf").is_file()
    assert (delivery / "final-report.md").is_file()
    assert (delivery / "final-report.json").is_file()
    assert (delivery / "quality-audit.md").is_file()
    assert (delivery / "delivery-manifest.json").is_file()
    assert (delivery / "delivery-manifest.md").is_file()

    report = json.loads((delivery / "final-report.json").read_text(encoding="utf-8"))
    assert report["environment"]["name"].startswith("Zhejiang Conservatory")
    assert report["summary"]["server_count"] == 3
    assert report["summary"]["coverage"]["network"] == "offline-simulated"
    assert report["summary"]["overall_status"] in {"healthy", "warning", "critical", "unknown"}


def test_delivery_artifacts_do_not_contain_placeholder_labels(tmp_path):
    out_dir = tmp_path / "run"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--inventory",
            str(SAMPLE),
            "--out",
            str(out_dir),
            "--offline",
            "--skip-guide-image",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    for artifact in [
        out_dir / "delivery" / "final-report.html",
        out_dir / "delivery" / "final-report.md",
        out_dir / "delivery" / "final-report.json",
        out_dir / "delivery" / "quality-audit.md",
        out_dir / "delivery" / "delivery-manifest.md",
    ]:
        assert_no_placeholder_text(artifact.read_text(encoding="utf-8"))


def test_delivery_manifest_is_chinese_and_complete(tmp_path):
    out_dir = tmp_path / "run"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--inventory",
            str(SAMPLE),
            "--out",
            str(out_dir),
            "--offline",
            "--skip-guide-image",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    delivery = out_dir / "delivery"
    manifest_md = (delivery / "delivery-manifest.md").read_text(encoding="utf-8")
    manifest = json.loads((delivery / "delivery-manifest.json").read_text(encoding="utf-8"))

    assert manifest_md.startswith("# 交付清单")
    assert "Delivery Manifest" not in manifest_md
    assert manifest["entrypoints"]["html"] == "delivery/final-report.html"
    assert manifest["entrypoints"]["pdf"] == "delivery/final-report.pdf"
    assert manifest["entrypoints"]["markdown"] == "delivery/final-report.md"
    assert manifest["entrypoints"]["json"] == "delivery/final-report.json"
    assert manifest["quality_status"] == "pass"


def test_multi_server_delivery_uses_n_plus_one_reports(tmp_path):
    inventory_path = tmp_path / "multi-server.json"
    inventory_path.write_text(
        json.dumps(
            {
                "environment": {"name": "Batch servers"},
                "servers": [
                    {
                        "name": "Portal web",
                        "address": "192.0.2.10",
                        "os_type": "linux",
                        "role": "web",
                        "collect": {"doops": True, "network": False},
                        "metrics": {"cpu_percent": 21.5, "memory_percent": 45.0, "disks": [{"mount": "/", "used_percent": 61.0}]},
                        "services": [{"name": "nginx", "status": "running", "expected": "running"}],
                    },
                    {
                        "name": "Database",
                        "address": "192.0.2.20",
                        "os_type": "linux",
                        "role": "database",
                        "collect": {"doops": True, "network": False},
                        "metrics": {"cpu_percent": 93.0, "memory_percent": 88.0, "disks": [{"mount": "/data", "used_percent": 91.0}]},
                        "services": [{"name": "mysql", "status": "failed", "expected": "running"}],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "run"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--inventory",
            str(inventory_path),
            "--out",
            str(out_dir),
            "--skip-guide-image",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    batch = out_dir / "delivery-batch"
    assert (batch / "index.html").is_file()
    assert (batch / "batch-summary.json").is_file()
    assert (batch / "overall" / "final-report.html").is_file()
    assert (batch / "overall" / "final-report.pdf").is_file()
    assert (batch / "servers" / "index.html").is_file()
    assert (batch / "servers" / "001-portal-web" / "delivery" / "final-report.html").is_file()
    assert (batch / "servers" / "002-database" / "delivery" / "final-report.html").is_file()

    index_html = (batch / "index.html").read_text(encoding="utf-8")
    server_index_html = (batch / "servers" / "index.html").read_text(encoding="utf-8")
    summary = json.loads((batch / "batch-summary.json").read_text(encoding="utf-8"))
    assert "服务器运行健康巡检批次报告" in index_html
    assert "compact-report" in index_html
    assert "guide-cover" in index_html
    assert "fallback-cover" in index_html
    assert "打开单机报告索引" in index_html
    assert "单机服务器运行健康报告索引" in server_index_html
    assert "server-report-index" in server_index_html
    assert "server-card critical" in server_index_html
    assert "overall/final-report.html" in index_html
    assert "servers/index.html" in index_html
    assert "servers/001-portal-web/delivery/final-report.html" in index_html
    assert "servers/002-database/delivery/final-report.html" in index_html
    assert summary["counts"]["total"] == 2
    assert summary["entrypoints"]["overall_html"] == "overall/final-report.html"
    assert summary["entrypoints"]["server_index"] == "servers/index.html"
    assert summary["servers"][0]["report"] == "servers/001-portal-web/delivery/final-report.html"
    assert summary["servers"][1]["status"] == "critical"


def test_quality_audit_fails_when_placeholder_labels_are_rendered(tmp_path):
    runner = load_runner_module("run_server_health_monitor_corrupt_labels")
    inventory = runner.load_inventory(SAMPLE)
    report = runner.build_report(inventory, offline=True, timeout=2.5)
    runner.STATUS_LABELS["unknown"] = "?" * 2
    runner.COVERAGE_LABELS["offline-simulated"] = "?" * 6
    runner.PORT_STATUS_LABELS["not-tested"] = "?" * 3

    try:
        runner.write_outputs(
            report,
            tmp_path / "run",
            skip_guide_image=True,
            image_model="gpt-image-2",
            image_size="1536x1024",
            image_quality="medium",
            guide_mode="auto",
        )
    except RuntimeError as exc:
        assert "quality audit failed" in str(exc)
    else:
        raise AssertionError("quality audit should fail when placeholder labels are rendered")


def test_reports_redact_sensitive_inventory_fields(tmp_path):
    inventory = json.loads(SAMPLE.read_text(encoding="utf-8"))
    inventory["servers"][0]["password"] = "PlainTextSecret123"
    inventory_path = tmp_path / "inventory.json"
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    out_dir = tmp_path / "run"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--inventory",
            str(inventory_path),
            "--out",
            str(out_dir),
            "--offline",
            "--guide-mode",
            "html-guide",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    for artifact in [
        out_dir / "delivery" / "final-report.html",
        out_dir / "delivery" / "final-report.md",
        out_dir / "delivery" / "final-report.json",
    ]:
        text = artifact.read_text(encoding="utf-8")
        assert "PlainTextSecret123" not in text
        assert "password" not in text.lower()


def test_reports_are_chinese_and_include_guide_image_slot(tmp_path):
    out_dir = tmp_path / "run"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--inventory",
            str(SAMPLE),
            "--out",
            str(out_dir),
            "--offline",
            "--skip-guide-image",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    delivery = out_dir / "delivery"
    html = (delivery / "final-report.html").read_text(encoding="utf-8")
    markdown = (delivery / "final-report.md").read_text(encoding="utf-8")
    status = json.loads((delivery / "guide-image-status.json").read_text(encoding="utf-8"))

    assert "服务器运行健康报告" in html
    assert "管理结论" in html
    assert "服务器矩阵" in markdown
    assert "Management Summary" not in html
    assert "Technical Evidence" not in html
    assert "Server Matrix" not in markdown
    assert "guide-visual" in html
    assert "html-guide-visual" in html
    assert status["status"] == "html_guide_selected"


def test_report_html_uses_management_layout_sections(tmp_path):
    out_dir = tmp_path / "run"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--inventory",
            str(SAMPLE),
            "--out",
            str(out_dir),
            "--offline",
            "--guide-mode",
            "html-guide",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=subprocess_env(),
    )

    assert result.returncode == 0, result.stderr
    html = (out_dir / "delivery" / "final-report.html").read_text(encoding="utf-8")

    for marker in (
        "compact-report",
        "executive-layout",
        "fallback-cover-grid",
        "cover-eyebrow",
        "hero-strip",
        "conclusion-panel",
        "coverage-strip",
        "trend-strip",
        "compact-core-metrics",
        "compact-key-services",
        "core-metric-grid",
        "key-service-grid",
        "table-scroll",
        "matrix-card-list",
        "matrix-card",
        "finding-meta",
        "evidence-grid",
    ):
        assert marker in html
    assert "负责人" not in html
    assert "业务部门" not in html
    assert "系统等级" not in html


def test_report_html_uses_ten_iteration_report_upgrades(tmp_path):
    out_dir = tmp_path / "run"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--inventory",
            str(SAMPLE),
            "--out",
            str(out_dir),
            "--offline",
            "--guide-mode",
            "html-guide",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=subprocess_env(),
    )

    assert result.returncode == 0, result.stderr
    delivery = out_dir / "delivery"
    html = (delivery / "final-report.html").read_text(encoding="utf-8")
    markdown = (delivery / "final-report.md").read_text(encoding="utf-8")
    report = json.loads((delivery / "final-report.json").read_text(encoding="utf-8"))
    audit = json.loads((delivery / "quality-audit.json").read_text(encoding="utf-8"))

    for marker in (
        "compact-summary",
        "compact-core-metrics",
        "compact-key-services",
        "compact-matrix",
        "compact-findings",
        "compact-evidence",
        "matrix-card-list",
    ):
        assert marker in html
    for heading in (
        "## 核心指标",
        "## 关键服务",
        "## 服务器矩阵",
        "## 问题与建议",
        "## 趋势与证据边界",
    ):
        assert heading in markdown
    for old_marker in (
        "executive-brief",
        "risk-queue",
        "coverage-gaps",
        "action-board",
        "advanced-report",
    ):
        assert old_marker not in html
    assert report["summary"]["report_insights"]["risk_queue"]
    assert report["summary"]["report_insights"]["coverage_gaps"]
    assert report["summary"]["report_insights"]["action_board"]
    assert report["summary"]["report_insights"]["quality_score"] >= 0
    assert audit["checks"]["layout_upgrade_markers"] == "pass"


def test_report_html_uses_twenty_more_report_upgrades(tmp_path):
    out_dir = tmp_path / "run"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--inventory",
            str(SAMPLE),
            "--out",
            str(out_dir),
            "--offline",
            "--guide-mode",
            "html-guide",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=subprocess_env(),
    )

    assert result.returncode == 0, result.stderr
    delivery = out_dir / "delivery"
    html = (delivery / "final-report.html").read_text(encoding="utf-8")
    markdown = (delivery / "final-report.md").read_text(encoding="utf-8")
    report = json.loads((delivery / "final-report.json").read_text(encoding="utf-8"))
    audit = json.loads((delivery / "quality-audit.json").read_text(encoding="utf-8"))

    advanced_markers = (
        "decision-summary",
        "risk-heatmap",
        "owner-brief",
        "sla-timeline",
        "evidence-ladder",
        "data-quality-panel",
        "remediation-roadmap",
        "change-watchlist",
        "service-health-panel",
        "process-health-panel",
        "capacity-panel",
        "asset-segmentation",
        "business-impact-panel",
        "control-checklist",
        "work-order-actions",
        "appendix-index",
        "readability-score",
        "report-narrative",
        "review-questions",
        "scope-statement",
        "next-report-plan",
    )
    assert "advanced-hidden-summary" not in html
    assert "id=\"decision-summary\"" not in html
    assert "id=\"evidence-ladder\"" not in html
    assert "id=\"data-quality-panel\"" not in html
    assert "id=\"risk-heatmap\"" not in html
    assert "id=\"service-health-panel\"" not in html
    assert "id=\"capacity-panel\"" not in html
    assert "id=\"work-order-actions\"" not in html
    assert "advanced-payload" not in html
    assert "advanced-kv" not in html
    assert "advanced-list" not in html
    assert '<h3>决策摘要</h3><pre>' not in html
    assert "{'layer':" not in markdown
    assert "&#x27;layer&#x27;" not in html

    for removed_heading in (
        "## 决策摘要",
        "## 优先级与时限",
        "## 证据与数据质量",
        "## 处置路线图",
        "## 复核问题清单",
    ):
        assert removed_heading not in markdown

    advanced = report["summary"]["report_insights"]["advanced"]
    for key in (
        "decision_summary",
        "risk_heatmap",
        "owner_brief",
        "sla_timeline",
        "evidence_ladder",
        "data_quality",
        "remediation_roadmap",
        "change_watchlist",
        "service_health",
        "process_health",
        "capacity_summary",
        "asset_segments",
        "business_impact",
        "control_checklist",
        "work_order_actions",
        "appendix_index",
        "readability_score",
        "report_narrative",
        "review_questions",
        "scope_statement",
        "next_report_plan",
    ):
        assert advanced[key]
    assert isinstance(advanced["risk_heatmap"], list)
    assert {"P1", "P2", "P3", "P4"}.issubset({row["priority"] for row in advanced["risk_heatmap"]})
    assert all({"priority", "critical", "warning", "review_required", "total"}.issubset(row) for row in advanced["risk_heatmap"])
    assert isinstance(advanced["data_quality"], dict)
    assert {"score", "missing_fields", "gaps", "summary"}.issubset(advanced["data_quality"])
    assert isinstance(advanced["remediation_roadmap"][0], dict)
    assert {"phase", "focus", "items"}.issubset(advanced["remediation_roadmap"][0])
    assert isinstance(advanced["work_order_actions"][0], dict)
    assert {"server", "priority", "due_time", "content"}.issubset(advanced["work_order_actions"][0])
    assert isinstance(advanced["readability_score"].get("signals"), list)
    assert isinstance(advanced["scope_statement"], dict)
    assert audit["checks"]["advanced_upgrade_markers"] == "pass"
    assert audit["checks"]["advanced_visible_signal"] == "pass"


def test_skip_guide_image_renders_html_css_guide_without_runtime_notice(tmp_path):
    out_dir = tmp_path / "run"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--inventory",
            str(SAMPLE),
            "--out",
            str(out_dir),
            "--offline",
            "--skip-guide-image",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=subprocess_env(OPENAI_API_KEY=""),
    )

    assert result.returncode == 0, result.stderr
    delivery = out_dir / "delivery"
    html = (delivery / "final-report.html").read_text(encoding="utf-8")
    status = json.loads((delivery / "guide-image-status.json").read_text(encoding="utf-8"))

    assert status["status"] == "html_guide_selected"
    assert "html-guide-visual" in html
    assert "本次按参数跳过 GPT 导览图生成" not in html
    assert "跳过 GPT" not in html
    assert "未检测到图像生成密钥" not in html
    assert "生成失败" not in html


def test_auto_missing_api_key_requires_explicit_guide_decision(tmp_path):
    out_dir = tmp_path / "run"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--inventory",
            str(SAMPLE),
            "--out",
            str(out_dir),
            "--offline",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=subprocess_env(OPENAI_API_KEY=""),
    )

    assert result.returncode != 0
    assert "默认 auto 模式不能在缺少 AI 导览图和 API Key 时静默降级为 HTML/CSS" in result.stderr
    assert "请先询问用户是否使用 AI 导览图" in result.stderr
    assert "确认接受内置导览图" in result.stderr
    assert not (out_dir / "delivery" / "final-report.html").exists()


def test_guide_image_is_generated_when_api_key_is_available(tmp_path):
    fake_openai = tmp_path / "openai.py"
    fake_openai.write_text(
        """
class _Image:
    b64_json = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="

class _Result:
    data = [_Image()]

class _Images:
    def generate(self, **kwargs):
        assert kwargs["model"] == "gpt-image-2"
        assert "服务器运行健康报告导览图" in kwargs["prompt"]
        return _Result()

class OpenAI:
    def __init__(self):
        self.images = _Images()
""",
        encoding="utf-8",
    )
    out_dir = tmp_path / "run"
    env = {
        **__import__("os").environ,
        "OPENAI_API_KEY": "sk-test-not-real",
        "PYTHONPATH": str(tmp_path),
    }

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--inventory",
            str(SAMPLE),
            "--out",
            str(out_dir),
            "--offline",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    delivery = out_dir / "delivery"
    status = json.loads((delivery / "guide-image-status.json").read_text(encoding="utf-8"))
    assert status["status"] == "generated"
    assert (delivery / "html-assets" / "guide-image.png").is_file()
    html = (delivery / "final-report.html").read_text(encoding="utf-8")
    assert './html-assets/guide-image.png' in html
    assert "ai-cover" in html
    assert "ai-guide-stage" in html
    assert "compact-report" in html


def test_doops_collector_resolves_zheyin_environment(tmp_path):
    fake_doops_cmd = write_fake_doops(
        tmp_path,
        """
import sys

if sys.argv[1:2] == ["targets"]:
    assert sys.argv[sys.argv.index("--target") + 1] == "zheyin"
    print("doops-zheyin/node-239 online")
    raise SystemExit(0)

assert "-session" in sys.argv
assert "exec" in sys.argv
assert sys.argv[sys.argv.index("--target") + 1] == "zheyin"
print("__SERVER_HEALTH_JSON_START__")
print('{"hostname":"zy-node","platform":"Linux","os_type":"linux","metrics":{"cpu_percent":12.5,"memory_percent":40.0,"disks":[{"mount":"/","used_percent":55.0}]},"services":[{"name":"doops-agent","status":"running","expected":"running"}],"collected_at":"2026-05-13T01:00:00+0800"}')
print("__SERVER_HEALTH_JSON_END__")
""",
    )
    inventory_path = tmp_path / "inventory.json"
    result = subprocess.run(
        [
            sys.executable,
            str(COLLECTOR),
            "--environment",
            "浙音",
            "--doops",
            str(fake_doops_cmd),
            "--out",
            str(inventory_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=subprocess_env(),
    )

    assert result.returncode == 0, result.stderr
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    server = inventory["servers"][0]
    assert inventory["environment"]["name"].startswith("Zhejiang Conservatory of Music")
    assert server["name"] == "zy-node"
    assert server["address"] == "zheyin"
    assert server["metrics"]["cpu_percent"] == 12.5
    assert server["services"][0]["name"] == "doops-agent"


def test_managed_hdu_environment_uses_doops_only_self_node_metrics(tmp_path):
    command_log = tmp_path / "commands.jsonl"
    fake_doops_cmd = write_fake_doops(
        tmp_path,
        f"""
import json
import pathlib
import sys

log = pathlib.Path({str(command_log)!r})
line = json.dumps({{"args": sys.argv[1:]}}, ensure_ascii=False) + "\\n"
log.write_text((log.read_text(encoding="utf-8") if log.exists() else "") + line, encoding="utf-8")
args = sys.argv[1:]

if args[:2] == ["targets", "--target"]:
    assert args[args.index("--target") + 1] == "hdu"
    print("CLUSTER INSTANCE BUSY LAST_SEEN")
    print("doops-hdu node-101 false 2026-05-14T00:10:00+08:00")
    raise SystemExit(0)
if "info" in args:
    print("collector=hdu uptime=10d memory=40%")
    raise SystemExit(0)
if "push" in args or "read" in args or "clean" in args:
    raise SystemExit(0)
if "exec" in args:
    assert args[args.index("--target") + 1] == "hdu"
    print("__SERVER_HEALTH_JSON_START__")
    print('{{"hostname":"hdu-node","platform":"Linux","os_type":"linux","metrics":{{"cpu_percent":8.5,"memory_percent":31.0,"disks":[{{"mount":"/","used_percent":48.0}}]}},"services":[{{"name":"doops-agent","status":"running","expected":"running"}}],"collected_at":"2026-05-14T00:10:00+0800"}}')
    print("__SERVER_HEALTH_JSON_END__")
    raise SystemExit(0)

raise AssertionError("managed hdu self-node check must not call SSH/WinRM/SNMPv3 extension commands")
""",
    )
    inventory_path = tmp_path / "hdu-inventory.json"

    result = subprocess.run(
        [
            sys.executable,
            str(COLLECTOR),
            "--environment",
            "杭电",
            "--doops",
            str(fake_doops_cmd),
            "--out",
            str(inventory_path),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=subprocess_env(),
    )

    assert result.returncode == 0, result.stderr
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    server = inventory["servers"][0]
    commands = [json.loads(line)["args"] for line in command_log.read_text(encoding="utf-8").splitlines()]
    flattened = " ".join(" ".join(args) for args in commands)
    assert inventory["doops_channel"]["target"] == "hdu"
    assert server["address"] == "hdu"
    assert server["collect"]["self_node_metrics"] is True
    assert server["collect"]["doops"] is True
    assert server["metrics"]["cpu_percent"] == 8.5
    assert "--host-metrics" not in flattened
    assert "--snmp-metrics" not in flattened
    assert "ssh" not in flattened.lower()
    assert "winrm" not in flattened.lower()
    assert "snmp" not in flattened.lower()


def test_doops_collector_accepts_user_server_inventory(tmp_path):
    fake_doops_cmd = write_fake_doops(
        tmp_path,
        """
import json
import sys

target = sys.argv[sys.argv.index("--target") + 1]

if sys.argv[1:2] == ["targets"]:
    print(f"{target} online")
    raise SystemExit(0)

payloads = {
    "web-01-target": {
        "hostname": "web-01",
        "platform": "Linux web",
        "os_type": "linux",
        "metrics": {"cpu_percent": 21.5, "memory_percent": 45.0, "disks": [{"mount": "/", "used_percent": 61.0}]},
        "services": [{"name": "nginx", "status": "running", "expected": "running"}],
        "collected_at": "2026-05-13T01:10:00+0800",
    },
    "db-01-target": {
        "hostname": "db-01",
        "platform": "Linux db",
        "os_type": "linux",
        "metrics": {"cpu_percent": 34.0, "memory_percent": 72.0, "disks": [{"mount": "/data", "used_percent": 83.0}]},
        "services": [{"name": "mysql", "status": "running", "expected": "running"}],
        "collected_at": "2026-05-13T01:10:10+0800",
    },
}

print("__SERVER_HEALTH_JSON_START__")
print(json.dumps(payloads[target], ensure_ascii=False))
print("__SERVER_HEALTH_JSON_END__")
""",
    )
    source_inventory = tmp_path / "source.json"
    source_inventory.write_text(
        json.dumps(
            {
                "environment": {"name": "User supplied doops servers", "owner": "ops"},
                "servers": [
                    {"name": "Portal web", "doops_target": "web-01-target", "role": "web", "owner": "portal"},
                    {"name": "Database", "doops_target": "db-01-target", "role": "database", "owner": "dba"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    collected_inventory = tmp_path / "collected.json"

    result = subprocess.run(
        [
            sys.executable,
            str(COLLECTOR),
            "--inventory",
            str(source_inventory),
            "--doops",
            str(fake_doops_cmd),
            "--out",
            str(collected_inventory),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        env=subprocess_env(),
    )

    assert result.returncode == 0, result.stderr
    inventory = json.loads(collected_inventory.read_text(encoding="utf-8"))
    assert inventory["environment"]["name"] == "User supplied doops servers"
    assert [server["name"] for server in inventory["servers"]] == ["Portal web", "Database"]
    assert [server["address"] for server in inventory["servers"]] == ["web-01-target", "db-01-target"]
    assert inventory["servers"][0]["metrics"]["cpu_percent"] == 21.5
    assert inventory["servers"][1]["metrics"]["disks"][0]["used_percent"] == 83.0
    assert all(server["collect"]["doops"] for server in inventory["servers"])


def test_excel_inventory_loader_maps_first_rows_and_redacts_credentials(tmp_path):
    collector = load_collector_module("collect_doops_inventory_excel_loader")
    excel_path = tmp_path / "servers.xlsx"
    write_excel_inventory(
        excel_path,
        [
            ["Portal", "172.16.70.4", "linux7", "root/TopSecret123", "portal app", "", ""],
            ["FTP", "172.16.70.15", "windows08_64", "administrator/AnotherSecret", "ftp server", "", ""],
            ["Ignored", "172.16.70.99", "linux", "root/ShouldNotAppear", "ignored by limit", "", ""],
        ],
    )

    inventory = collector.load_source_inventory(excel_path, limit=2)

    assert inventory["environment"]["name"] == "servers"
    assert len(inventory["servers"]) == 2
    assert inventory["servers"][0]["name"] == "Portal"
    assert inventory["servers"][0]["address"] == "172.16.70.4"
    assert inventory["servers"][0]["os_type"] == "linux"
    assert inventory["servers"][0]["ports"] == [22]
    assert inventory["servers"][1]["ports"] == [21, 3389]
    text = json.dumps(inventory, ensure_ascii=False)
    assert "TopSecret123" not in text
    assert "AnotherSecret" not in text
    assert "ShouldNotAppear" not in text
    assert "credential-redacted" in text


def test_excel_inventory_can_keep_runtime_auth_when_explicitly_requested(tmp_path):
    collector = load_collector_module("collect_doops_inventory_runtime_auth")
    excel_path = tmp_path / "servers.xlsx"
    write_excel_inventory(
        excel_path,
        [
            ["Portal", "172.16.70.4", "linux7", "root/TopSecret123", "portal app", "", ""],
        ],
    )

    inventory = collector.load_source_inventory(excel_path, limit=1, include_runtime_auth=True)

    server = inventory["servers"][0]
    assert server["runtime_auth"]["username"] == "root"
    assert server["runtime_auth"]["password"] == "TopSecret123"
    public_text = json.dumps({key: value for key, value in server.items() if key != "runtime_auth"}, ensure_ascii=False)
    assert "TopSecret123" not in public_text


def test_runtime_auth_parser_handles_labels_and_multiple_usernames():
    collector = load_collector_module("collect_doops_inventory_runtime_auth_variants")

    labeled = collector.parse_runtime_auth("数据中心：administrator/TopSecret123")
    assert labeled["username"] == "administrator"
    assert labeled["password"] == "TopSecret123"

    multi_user = collector.parse_runtime_auth("auser,root/TopSecret123")
    assert multi_user["username"] == "auser"
    assert multi_user["password"] == "TopSecret123"
    assert [item["username"] for item in multi_user["candidates"]] == ["auser", "root"]


def test_auth_security_parses_linux_failed_then_success_pattern():
    collector = load_collector_module("collect_doops_inventory_auth_security_linux")
    sample = "\n".join(
        [
            "May 15 08:01:00 host sshd[100]: Failed password for invalid user admin from 203.0.113.9 port 50111 ssh2",
            "May 15 08:02:00 host sshd[101]: Failed password for root from 203.0.113.9 port 50112 ssh2",
            "May 15 08:03:00 host sshd[102]: authentication failure; logname= uid=0 euid=0 tty=ssh ruser= rhost=203.0.113.9 user=root",
            "May 15 08:40:00 host sshd[103]: Accepted password for root from 203.0.113.9 port 50113 ssh2",
        ]
    )

    evidence = collector.parse_linux_auth_log(sample)

    assert evidence["failed_login_count"] == 3
    assert evidence["successful_login_count"] == 1
    assert evidence["unique_source_count"] == 1
    assert evidence["top_sources"][0]["source"] == "203.0.113.9"
    assert any(pattern["type"] == "failed-then-success" for pattern in evidence["patterns"])


def test_password_strength_audit_scores_without_leaking_plaintext():
    collector = load_collector_module("collect_doops_inventory_password_strength")
    source = {
        "servers": [
            {
                "name": "门户服务器",
                "address": "10.0.0.8",
                "os_type": "linux",
                "runtime_auth": {"username": "admin", "password": "admin123"},
            },
            {
                "name": "备份服务器",
                "address": "10.0.0.9",
                "os_type": "linux",
                "runtime_auth": {"username": "backup", "password": "admin123"},
            },
        ]
    }
    inventory = {"environment": {"name": "测试环境"}, "servers": [dict(item) for item in source["servers"]]}

    audited = collector.apply_password_strength_inventory(inventory, source, enabled=True, source_name="runtime-auth")
    payload = json.dumps(audited, ensure_ascii=False)

    assert "admin123" not in payload
    assert audited["servers"][0]["auth_security"]["password_strength"]["weak_count"] == 1
    assert audited["servers"][0]["auth_security"]["password_strength"]["reuse_group_count"] == 1
    assert any("包含用户名" in item["rule"] for item in audited["servers"][0]["auth_security"]["password_strength"]["findings"])
    assert "runtime_auth" not in audited["servers"][0]


def test_auth_security_findings_summary_and_report_rendering():
    runner = load_runner_module("run_server_health_monitor_auth_security")
    inventory = {
        "environment": {"name": "认证安全测试环境"},
        "servers": [
            {
                "name": "统一认证服务器",
                "address": "10.0.0.10",
                "os_type": "linux",
                "role": "identity",
                "ports": [22],
                "network_observation": {"mode": "doops-network-probe", "ports": [{"port": 22, "status": "open"}]},
                "auth_security": {
                    "status": "collected",
                    "window_days": 7,
                    "method": "ssh",
                    "log_evidence": {
                        "failed_login_count": 55,
                        "successful_login_count": 1,
                        "unique_source_count": 1,
                        "top_sources": [{"source": "203.0.113.9", "count": 55}],
                        "top_users": [{"user": "root", "count": 55}],
                        "patterns": [{"type": "failed-then-success", "source": "203.0.113.9", "user": "root", "failed_count": 55}],
                    },
                    "protection_config": {
                        "password_login_enabled": True,
                        "root_login_enabled": True,
                        "max_auth_tries": 6,
                        "account_lockout_enabled": False,
                        "fail2ban_enabled": False,
                    },
                    "password_strength": {
                        "status": "scored",
                        "weak_count": 1,
                        "medium_count": 0,
                        "strong_count": 0,
                        "reuse_group_count": 0,
                        "findings": [{"account": "roo***", "severity": "weak", "rule": "长度不足"}],
                    },
                },
            }
        ],
    }

    report = runner.build_report(inventory, offline=False, timeout=0.1)
    html = runner.render_html(report, runner.render_markdown(report), {"status": "fallback"})

    assert report["summary"]["auth_security"]["covered_servers"] == 1
    assert report["summary"]["auth_security"]["brute_force_servers"] == 1
    assert report["summary"]["overall_status"] == "critical"
    assert any(item["category"] == "auth-security" and item["severity"] == "critical" for item in report["servers"][0]["findings"])
    assert "compact-auth-security" in html
    assert "认证安全" in html


def test_auth_security_unavailable_is_evidence_boundary_not_healthy():
    runner = load_runner_module("run_server_health_monitor_auth_security_unavailable")
    inventory = {
        "environment": {"name": "认证安全证据边界"},
        "servers": [
            {
                "name": "SNMP 服务器",
                "address": "10.0.0.11",
                "os_type": "linux",
                "collect": {"host_metrics": True, "metrics_method": "snmpv3", "host_metrics_status": "collected"},
                "metrics": {"cpu_percent": 10.0, "memory_percent": 20.0},
                "auth_security": {"status": "unavailable", "window_days": 7, "method": "unavailable"},
            }
        ],
    }

    report = runner.build_report(inventory, offline=False, timeout=0.1)

    assert report["summary"]["auth_security"]["uncovered_servers"] == 1
    assert report["servers"][0]["status"] == "warning"
    assert any(item["category"] == "auth-security" and item["review_required"] for item in report["servers"][0]["findings"])


def test_host_metrics_ssh_password_disables_publickey_auth():
    collector = load_collector_module("collect_doops_inventory_runtime_auth_ssh_options")

    script = collector.build_host_metrics_script(
        [
            {
                "name": "Portal",
                "address": "172.16.70.4",
                "os_type": "linux",
                "ports": [22],
                "runtime_auth": {"username": "root", "password": "TopSecret123"},
            }
        ],
        metrics_target="zheyin",
        profile="excel-runtime-credentials",
        metrics_timeout=20,
    )

    assert "PreferredAuthentications=password,keyboard-interactive" in script
    assert "PubkeyAuthentication=no" in script
    assert "NumberOfPasswordPrompts=1" in script
    assert "SSH_ASKPASS" in script
    assert "HostKeyAlgorithms=+ssh-rsa,ssh-dss" in script


def test_doops_probe_target_collects_excel_network_status(tmp_path):
    payload = {
        "probe_target": "zheyin",
        "probe_hostname": "probe-node",
        "checked_at": "2026-05-13T02:30:00+0800",
        "servers": [
            {
                "index": 1,
                "address": "172.16.70.4",
                "reachable": True,
                "ping": {"status": "alive", "latency_ms": 8},
                "ports": [{"port": 22, "status": "open", "latency_ms": 12}],
            },
            {
                "index": 2,
                "address": "",
                "reachable": False,
                "ping": {"status": "skipped", "latency_ms": None, "error": "invalid-address"},
                "ports": [],
            },
        ],
    }
    fake_doops_cmd = write_fake_doops(
        tmp_path,
        f"""
import base64
import json
import sys

if sys.argv[1:2] == ["targets"]:
    assert sys.argv[sys.argv.index("--target") + 1] == "zheyin"
    print("doops-zheyin/node-239 online token=secret-token")
    raise SystemExit(0)

assert "-session" in sys.argv
assert "exec" in sys.argv
assert sys.argv[sys.argv.index("--target") + 1] == "zheyin"
command = sys.argv[sys.argv.index("--cmd") + 1]
assert "base64 -d" in command
encoded = base64.b64encode(json.dumps({payload!r}).encode()).decode()
print("__SERVER_HEALTH_JSON_START__")
print("SERVER_HEALTH_B64:" + encoded)
print("__SERVER_HEALTH_JSON_END__")
""",
    )
    excel_path = tmp_path / "servers.xlsx"
    write_excel_inventory(
        excel_path,
        [
            ["Portal", "172.16.70.4", "linux7", "root/TopSecret123", "portal app", "", ""],
            ["BadIP", "/", "", "administrator/AnotherSecret", "bad ip", "", ""],
        ],
    )
    collected_inventory = tmp_path / "collected.json"
    evidence_path = tmp_path / "evidence.json"

    result = subprocess.run(
        [
            sys.executable,
            str(COLLECTOR),
            "--inventory",
            str(excel_path),
            "--probe-target",
            "zheyin",
            "--limit",
            "2",
            "--doops",
            str(fake_doops_cmd),
            "--out",
            str(collected_inventory),
            "--evidence-out",
            str(evidence_path),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=subprocess_env(),
    )

    assert result.returncode == 0, result.stderr
    inventory = json.loads(collected_inventory.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert [server["name"] for server in inventory["servers"]] == ["Portal", "BadIP"]
    assert inventory["servers"][0]["collect"]["doops_probe"] is True
    assert inventory["servers"][0]["network_observation"]["reachable"] is True
    assert inventory["servers"][1]["network_observation"]["ping"]["error"] == "invalid-address"
    assert evidence["probe_target"] == "zheyin"
    assert "secret-token" not in evidence_path.read_text(encoding="utf-8")
    assert "TopSecret123" not in collected_inventory.read_text(encoding="utf-8")


def test_doops_host_metrics_collects_ssh_and_winrm_from_excel(tmp_path):
    payload = {
        "metrics_target": "zheyin",
        "profile": "zheyin-monitor",
        "checked_at": "2026-05-13T03:10:00+0800",
        "servers": [
            {
                "index": 1,
                "address": "172.16.70.4",
                "metrics_method": "ssh",
                "status": "collected",
                "metrics": {
                    "cpu_percent": 11.5,
                    "memory_percent": 43.0,
                    "load_per_core": 0.12,
                    "uptime_days": 18.2,
                    "disks": [{"mount": "/", "used_percent": 61.0}],
                },
                "services": [{"name": "sshd", "status": "running", "expected": "running"}],
                "processes": [{"pid": 100, "name": "nginx", "user": "root", "state": "S", "cpu_percent": 1.2, "memory_percent": 0.5}],
                "collection_errors": [],
            },
            {
                "index": 2,
                "address": "172.16.70.88",
                "metrics_method": "winrm",
                "status": "collected",
                "metrics": {
                    "cpu_percent": 21.0,
                    "memory_percent": 55.5,
                    "uptime_days": 42.0,
                    "disks": [{"mount": "C:", "used_percent": 70.0}],
                },
                "services": [{"name": "WinRM", "status": "running", "expected": "running"}],
                "processes": [{"pid": 200, "name": "w3wp", "state": "running", "cpu_seconds": 12.0, "memory_mb": 256.0}],
                "collection_errors": [],
            },
        ],
    }
    fake_doops_cmd = write_fake_doops(
        tmp_path,
        f"""
import base64
import json
import sys

if sys.argv[1:2] == ["targets"]:
    assert sys.argv[sys.argv.index("--target") + 1] == "zheyin"
    print("doops-zheyin/node-239 online token=host-secret-token")
    raise SystemExit(0)

assert "-session" in sys.argv
assert "exec" in sys.argv
assert sys.argv[sys.argv.index("--target") + 1] == "zheyin"
command = sys.argv[sys.argv.index("--cmd") + 1]
assert "HOST_METRICS_PROFILE" in command
assert "base64 -d" in command
assert "gzip -dc" in command
encoded = base64.b64encode(json.dumps({payload!r}).encode()).decode()
print("__SERVER_HEALTH_JSON_START__")
print("SERVER_HEALTH_B64:" + encoded)
print("__SERVER_HEALTH_JSON_END__")
""",
    )
    excel_path = tmp_path / "servers.xlsx"
    write_excel_inventory(
        excel_path,
        [
            ["Portal", "172.16.70.4", "linux7", "root/TopSecret123", "portal app", "", ""],
            ["Assets", "172.16.70.88", "windows2016", "administrator/AnotherSecret", "assets app", "", ""],
        ],
    )
    collected_inventory = tmp_path / "collected.json"
    evidence_path = tmp_path / "evidence.json"

    result = subprocess.run(
        [
            sys.executable,
            str(COLLECTOR),
            "--inventory",
            str(excel_path),
            "--host-metrics",
            "--host-metrics-target",
            "zheyin",
            "--host-metrics-profile",
            "zheyin-monitor",
            "--limit",
            "2",
            "--doops",
            str(fake_doops_cmd),
            "--out",
            str(collected_inventory),
            "--evidence-out",
            str(evidence_path),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=subprocess_env(),
    )

    assert result.returncode == 0, result.stderr
    inventory = json.loads(collected_inventory.read_text(encoding="utf-8"))
    evidence_text = evidence_path.read_text(encoding="utf-8")
    assert [server["name"] for server in inventory["servers"]] == ["Portal", "Assets"]
    assert inventory["servers"][0]["collect"]["host_metrics"] is True
    assert inventory["servers"][0]["collect"]["metrics_method"] == "ssh"
    assert inventory["servers"][1]["collect"]["metrics_method"] == "winrm"
    assert inventory["servers"][0]["metrics"]["cpu_percent"] == 11.5
    assert inventory["servers"][1]["metrics"]["disks"][0]["mount"] == "C:"
    assert inventory["servers"][0]["services"][0]["name"] == "sshd"
    assert inventory["servers"][0]["processes"][0]["name"] == "nginx"
    assert inventory["servers"][1]["processes"][0]["memory_mb"] == 256.0
    assert "TopSecret123" not in collected_inventory.read_text(encoding="utf-8")
    assert "AnotherSecret" not in collected_inventory.read_text(encoding="utf-8")
    assert "host-secret-token" not in evidence_text


def test_metric_payload_sanitizes_processes_without_command_arguments():
    collector = load_collector_module("collect_doops_inventory_processes")

    payload = collector.sanitize_metric_payload(
        {
            "status": "collected",
            "metrics_method": "ssh",
            "metrics": {"cpu_percent": 20.0},
            "services": [],
            "processes": [
                {
                    "pid": 123,
                    "name": "java",
                    "user": "app",
                    "state": "R",
                    "cpu_percent": 88.5,
                    "memory_percent": 16.2,
                    "command": "java -jar app.jar --password TopSecret123",
                }
            ],
        }
    )

    process = payload["processes"][0]
    assert process["name"] == "java"
    assert process["cpu_percent"] == 88.5
    assert "command" not in process
    assert "TopSecret123" not in json.dumps(payload, ensure_ascii=False)


def test_doops_snmp_metrics_collects_basic_host_metrics_from_excel(tmp_path):
    snmp_payload = {
        "metrics_target": "zheyin",
        "profile": "zheyin-snmpv3-monitor",
        "checked_at": "2026-05-13T04:10:00+0800",
        "servers": [
            {
                "index": 1,
                "address": "172.16.70.4",
                "metrics_method": "snmpv3",
                "status": "collected",
                "metrics": {
                    "cpu_percent": 12.5,
                    "memory_percent": 44.0,
                    "uptime_days": 7.25,
                    "disks": [{"mount": "/", "used_percent": 55.0}],
                },
                "services": [],
                "collection_errors": [],
            }
        ],
    }
    probe_payload = {
        "probe_target": "zheyin",
        "servers": [
            {
                "index": 1,
                "address": "172.16.70.4",
                "reachable": True,
                "ping": {"status": "alive", "latency_ms": 4},
                "ports": [{"port": 161, "status": "open", "latency_ms": 2}],
            }
        ],
    }
    fake_doops_cmd = write_fake_doops(
        tmp_path,
        f"""
import base64
import json
import sys

if sys.argv[1:2] == ["targets"]:
    assert sys.argv[sys.argv.index("--target") + 1] == "zheyin"
    print("zheyin online token=snmp-secret-token")
    raise SystemExit(0)

assert "-session" in sys.argv
assert "exec" in sys.argv
assert sys.argv[sys.argv.index("--target") + 1] == "zheyin"
command = sys.argv[sys.argv.index("--cmd") + 1]
assert "auth_key" not in command
assert "priv_key" not in command
assert "community" not in command
if "SNMP_METRICS_PROFILE" in command:
    assert "base64 -d" in command
    assert "gzip -dc" in command
    payload = {snmp_payload!r}
else:
    payload = {probe_payload!r}
encoded = base64.b64encode(json.dumps(payload).encode()).decode()
print("__SERVER_HEALTH_JSON_START__")
print("SERVER_HEALTH_B64:" + encoded)
print("__SERVER_HEALTH_JSON_END__")
""",
    )
    excel_path = tmp_path / "servers.xlsx"
    write_excel_inventory(
        excel_path,
        [["Portal", "172.16.70.4", "linux7", "root/TopSecret123", "portal app", "", ""]],
    )
    collected_inventory = tmp_path / "collected.json"
    evidence_path = tmp_path / "evidence.json"

    result = subprocess.run(
        [
            sys.executable,
            str(COLLECTOR),
            "--inventory",
            str(excel_path),
            "--probe-target",
            "zheyin",
            "--snmp-metrics",
            "--snmp-target",
            "zheyin",
            "--snmp-profile",
            "zheyin-snmpv3-monitor",
            "--limit",
            "1",
            "--doops",
            str(fake_doops_cmd),
            "--out",
            str(collected_inventory),
            "--evidence-out",
            str(evidence_path),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=subprocess_env(),
    )

    assert result.returncode == 0, result.stderr
    inventory_text = collected_inventory.read_text(encoding="utf-8")
    evidence_text = evidence_path.read_text(encoding="utf-8")
    inventory = json.loads(inventory_text)
    assert inventory["servers"][0]["collect"]["host_metrics"] is True
    assert inventory["servers"][0]["collect"]["metrics_method"] == "snmpv3"
    assert inventory["servers"][0]["collect"]["metrics_probe_target"] == "zheyin"
    assert inventory["servers"][0]["collect"]["host_metrics_status"] == "collected"
    assert inventory["servers"][0]["metrics"]["cpu_percent"] == 12.5
    assert inventory["servers"][0]["metrics"]["disks"][0]["mount"] == "/"
    assert "TopSecret123" not in inventory_text
    assert "auth_key" not in inventory_text
    assert "priv_key" not in inventory_text
    assert "community" not in inventory_text
    assert "snmp-secret-token" not in evidence_text
    assert "auth_key" not in evidence_text
    assert "priv_key" not in evidence_text
    assert "community" not in evidence_text


def test_probe_then_host_metrics_preserves_runtime_auth_in_memory_only(tmp_path):
    fake_doops_cmd = write_fake_doops(
        tmp_path,
        """
import base64
import gzip
import json
import re
import sys

if sys.argv[1:2] == ["targets"]:
    print("zheyin online")
    raise SystemExit(0)

command = sys.argv[sys.argv.index("--cmd") + 1]
print("__SERVER_HEALTH_JSON_START__")
if "gzip -dc" in command:
    match = re.search(r"printf ([A-Za-z0-9+/=]+) \\| base64 -d \\| gzip -dc \\| python3", command)
    assert match, command
    script = gzip.decompress(base64.b64decode(match.group(1))).decode("utf-8")
    servers_match = re.search(r'SERVERS = json\\.loads\\(base64\\.b64decode\\("([^"]+)"\\)\\.decode\\("utf-8"\\)\\)', script)
    assert servers_match, script
    servers = json.loads(base64.b64decode(servers_match.group(1)).decode("utf-8"))
    has_runtime_secret = servers[0].get("runtime_auth", {}).get("password") == "TopSecret123"
    payload = {
        "metrics_target": "zheyin",
        "profile": "zheyin-monitor",
        "servers": [
            {
                "index": 1,
                "address": "172.16.70.4",
                "metrics_method": "ssh",
                "status": "collected" if has_runtime_secret else "failed",
                "metrics": {"cpu_percent": 7.0} if has_runtime_secret else {},
                "services": [{"name": "sshd", "status": "running", "expected": "running"}] if has_runtime_secret else [],
                "collection_errors": [] if has_runtime_secret else [{"stage": "host-metrics", "type": "missing-runtime-auth"}],
            }
        ],
    }
else:
    payload = {
        "probe_target": "zheyin",
        "servers": [
            {
                "index": 1,
                "address": "172.16.70.4",
                "reachable": True,
                "ping": {"status": "not-available"},
                "ports": [{"port": 22, "status": "open", "latency_ms": 2}],
            }
        ],
    }
print("SERVER_HEALTH_B64:" + base64.b64encode(json.dumps(payload).encode()).decode())
print("__SERVER_HEALTH_JSON_END__")
""",
    )
    excel_path = tmp_path / "servers.xlsx"
    write_excel_inventory(
        excel_path,
        [["Portal", "172.16.70.4", "linux7", "root/TopSecret123", "portal app", "", ""]],
    )
    collected_inventory = tmp_path / "collected.json"
    evidence_path = tmp_path / "evidence.json"

    result = subprocess.run(
        [
            sys.executable,
            str(COLLECTOR),
            "--inventory",
            str(excel_path),
            "--probe-target",
            "zheyin",
            "--host-metrics",
            "--host-metrics-target",
            "zheyin",
            "--use-excel-runtime-credentials",
            "--limit",
            "1",
            "--doops",
            str(fake_doops_cmd),
            "--out",
            str(collected_inventory),
            "--evidence-out",
            str(evidence_path),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=subprocess_env(),
    )

    assert result.returncode == 0, result.stderr
    inventory_text = collected_inventory.read_text(encoding="utf-8")
    evidence_text = evidence_path.read_text(encoding="utf-8")
    inventory = json.loads(inventory_text)
    assert inventory["servers"][0]["metrics"]["cpu_percent"] == 7.0
    assert inventory["servers"][0]["collect"]["host_metrics_status"] == "collected"
    assert "runtime_auth" not in inventory_text
    assert "TopSecret123" not in inventory_text
    assert "TopSecret123" not in evidence_text


def test_classified_inventory_writes_group_csvs_and_keeps_monitorable_reports(tmp_path):
    fake_doops_cmd = write_fake_doops(
        tmp_path,
        """
import base64
import gzip
import json
import re
import sys

if sys.argv[1:2] == ["targets"]:
    print("zheyin online")
    raise SystemExit(0)

command = sys.argv[sys.argv.index("--cmd") + 1]
print("__SERVER_HEALTH_JSON_START__")
match = re.search(r"printf ([A-Za-z0-9+/=]+) \\| base64 -d \\| gzip -dc \\| python3", command)
plain_match = re.search(r"printf ([A-Za-z0-9+/=]+) \\| base64 -d \\| python3", command)
assert match or plain_match, command
script = gzip.decompress(base64.b64decode(match.group(1))).decode("utf-8") if match else base64.b64decode(plain_match.group(1)).decode("utf-8")
servers_match = re.search(r'SERVERS = json\\.loads\\(base64\\.b64decode\\("([^"]+)"\\)\\.decode\\("utf-8"\\)\\)', script)
assert servers_match, script
servers = json.loads(base64.b64decode(servers_match.group(1)).decode("utf-8"))
if "HOST_METRICS_PROFILE" in script:
    payload_servers = []
    for item in servers:
        collected = item["address"] == "172.16.70.4"
        payload_servers.append(
            {
                "index": item["index"],
                "address": item["address"],
                "metrics_method": "ssh",
                "status": "collected" if collected else "failed",
                "metrics": {"cpu_percent": 8.0, "memory_percent": 35.0} if collected else {},
                "services": [{"name": "sshd", "status": "running", "expected": "running"}] if collected else [],
                "collection_errors": [] if collected else [{"stage": "host-metrics", "type": "ssh-auth-failed"}],
            }
        )
    payload = {"metrics_target": "zheyin", "profile": "excel-runtime-credentials", "servers": payload_servers}
else:
    payload = {
        "probe_target": "zheyin",
        "servers": [
            {
                "index": item["index"],
                "address": item["address"],
                "reachable": True,
                "ping": {"status": "alive"},
                "ports": [{"port": 22, "status": "open", "latency_ms": 2}],
            }
            for item in servers
        ],
    }
print("SERVER_HEALTH_B64:" + base64.b64encode(json.dumps(payload).encode()).decode())
print("__SERVER_HEALTH_JSON_END__")
""",
    )
    excel_path = tmp_path / "servers.xlsx"
    write_excel_inventory(
        excel_path,
        [
            ["Monitorable", "172.16.70.4", "linux", "root/TopSecret123", "portal", "", ""],
            ["Unmonitorable", "172.16.70.5", "linux", "root/TopSecret123", "portal", "", ""],
            ["Stopped", "172.16.70.6", "linux", "root/TopSecret123", "portal", "", "否"],
        ],
    )
    collected_inventory = tmp_path / "classified" / "inventory.json"
    evidence_path = tmp_path / "classified" / "evidence.json"

    result = subprocess.run(
        [
            sys.executable,
            str(COLLECTOR),
            "--inventory",
            str(excel_path),
            "--probe-target",
            "zheyin",
            "--host-metrics",
            "--host-metrics-target",
            "zheyin",
            "--host-metrics-profile",
            "excel-runtime-credentials",
            "--use-excel-runtime-credentials",
            "--classify-inventory",
            "--doops-workspace-mode",
            "inline",
            "--doops",
            str(fake_doops_cmd),
            "--out",
            str(collected_inventory),
            "--evidence-out",
            str(evidence_path),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=subprocess_env(),
    )

    assert result.returncode == 0, result.stderr
    inventory_text = collected_inventory.read_text(encoding="utf-8")
    evidence_text = evidence_path.read_text(encoding="utf-8")
    inventory = json.loads(inventory_text)
    groups = inventory["inventory_groups"]
    assert groups["total_servers"] == 3
    assert groups["active_servers"] == 2
    assert groups["inactive_servers"] == 1
    assert groups["monitorable_servers"] == 1
    assert groups["unmonitorable_servers"] == 1
    assert [server["name"] for server in inventory["servers"]] == ["Monitorable"]
    for filename in (
        "inventory-active-servers.csv",
        "inventory-inactive-servers.csv",
        "inventory-monitorable-servers.csv",
        "inventory-unmonitorable-servers.csv",
    ):
        assert (collected_inventory.parent / filename).is_file()
    assert "TopSecret123" not in inventory_text
    assert "TopSecret123" not in evidence_text

    out_dir = tmp_path / "classified-report"
    render = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--inventory",
            str(collected_inventory),
            "--out",
            str(out_dir),
            "--guide-mode",
            "html-guide",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=subprocess_env(),
    )
    assert render.returncode == 0, render.stderr
    overall_report = json.loads((out_dir / "delivery-batch" / "overall" / "final-report.json").read_text(encoding="utf-8"))
    batch_summary = json.loads((out_dir / "delivery-batch" / "batch-summary.json").read_text(encoding="utf-8"))
    assert overall_report["summary"]["inventory_groups"]["inactive_servers"] == 1
    assert overall_report["summary"]["inventory_groups"]["unmonitorable_servers"] == 1
    assert len(batch_summary["servers"]) == 1
    assert (out_dir / "delivery-batch" / "servers" / "001-monitorable" / "delivery" / "final-report.html").is_file()


def test_host_metrics_command_avoids_nested_python_c_quotes():
    collector = load_collector_module("collect_doops_inventory_host_metrics_command")

    command = collector.build_host_metrics_command(
        [
            {
                "metrics_index": 1,
                "name": "Portal",
                "address": "172.16.70.4",
                "os_type": "linux",
                "ports": [22],
            }
        ],
        "zheyin",
        "zheyin-monitor",
        20,
    )

    assert "python3 -c" not in command
    assert "python -c" not in command
    assert "base64 -d" in command
    assert "gzip -dc" in command
    assert "| python3" in command
    assert "$PY" not in command
    assert len(command) < 7600


def test_doops_self_metrics_command_uses_base64_transport():
    collector = load_collector_module("collect_doops_inventory_self_metrics_command")

    command = collector.build_remote_command()

    assert "python3 -c" not in command
    assert "python -c" not in command
    assert "<<'PY'" not in command
    assert "base64 -d" in command
    assert "gzip -dc" in command
    assert "| python3" in command
    assert "__SERVER_HEALTH_JSON_START__" in command
    assert "__SERVER_HEALTH_JSON_END__" in command
    assert len(command) < 7600


def test_doops_push_path_normalizes_windows_paths(monkeypatch):
    collector = load_collector_module("collect_doops_inventory_push_path")

    monkeypatch.setattr(collector.os, "name", "nt", raising=False)

    assert collector.doops_local_src_path(r"D:\Code\repo\pkg") == "/mnt/d/Code/repo/pkg"


def test_collector_parse_json_accepts_noisy_ssh_pty_output():
    collector = load_collector_module("collect_doops_inventory_parse_noisy_ssh")
    payload = '{"metrics":{"cpu_percent":12.5},"services":[{"name":"sshd","status":"running","expected":"running"}]}'

    parsed = collector.parse_json(
        "Warning: Permanently added host\r\n"
        "root@172.16.70.4's password:\r\n"
        + payload
        + "\r\nConnection to 172.16.70.4 closed.\r\n"
    )

    assert parsed["metrics"]["cpu_percent"] == 12.5
    assert parsed["services"][0]["name"] == "sshd"


def test_windows_metrics_falls_back_to_python_wsman_basic_when_pwsh_missing():
    collector = load_collector_module("collect_doops_inventory_wsman_basic")

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            self.server.requests.append((dict(self.headers), body.decode("utf-8", errors="ignore")))
            response = (
                '<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope">'
                "<s:Body>"
                '<rsp:Stream Name="stdout" xmlns:rsp="http://schemas.microsoft.com/wbem/wsman/1/windows/shell">'
                '{"metrics":{"cpu_percent":9,"memory_percent":41,"uptime_days":3.5,'
                '"disks":[{"mount":"C:","used_percent":66}]},'
                '"services":[{"name":"WinRM","status":"running","expected":"running"}]}'
                "</rsp:Stream>"
                '<rsp:CommandState State="http://schemas.microsoft.com/wbem/wsman/1/windows/shell/CommandState/Done" '
                'xmlns:rsp="http://schemas.microsoft.com/wbem/wsman/1/windows/shell">'
                "<rsp:ExitCode>0</rsp:ExitCode>"
                "</rsp:CommandState>"
                "</s:Body></s:Envelope>"
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/soap+xml;charset=UTF-8")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)

        def log_message(self, *args):
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.requests = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        command = collector.build_host_metrics_command(
            [
                {
                    "metrics_index": 1,
                    "name": "Windows",
                    "address": "127.0.0.1",
                    "os_type": "windows",
                    "ports": [server.server_port],
                    "runtime_auth": {
                        "username": "monitor",
                        "password": "TopSecret123",
                        "winrm_ports": [server.server_port],
                    },
                }
            ],
            "zheyin",
            "zheyin-monitor",
            3,
        )
        encoded = command.split("printf ", 1)[1].split(" | base64 -d", 1)[0]
        script = __import__("gzip").decompress(__import__("base64").b64decode(encoded)).decode("utf-8")
        result = subprocess.run(
            [sys.executable],
            input=script,
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=subprocess_env(PATH=""),
            timeout=15,
        )
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()

    assert result.returncode == 0, result.stderr
    payload_line = next(line for line in result.stdout.splitlines() if line.startswith("SERVER_HEALTH_B64:"))
    payload = json.loads(__import__("base64").b64decode(payload_line.split(":", 1)[1]).decode("utf-8"))
    observed = payload["servers"][0]
    assert observed["status"] == "collected"
    assert observed["metrics"]["cpu_percent"] == 9
    assert observed["metrics"]["disks"][0]["mount"] == "C:"
    assert observed["services"][0]["name"] == "WinRM"
    assert server.requests
    request_headers, request_body = server.requests[0]
    assert "Basic " in request_headers["Authorization"]
    assert "TopSecret123" not in request_body


def test_doops_host_metrics_failures_are_sanitized_and_do_not_block(tmp_path):
    payload = {
        "metrics_target": "zheyin",
        "profile": "zheyin-monitor",
        "servers": [
            {
                "index": 1,
                "address": "172.16.70.20",
                "metrics_method": "ssh",
                "status": "failed",
                "metrics": {},
                "services": [],
                "collection_errors": [{"stage": "host-metrics", "type": "ssh-auth-failed"}],
                "debug": "password=ShouldNotLeak",
            },
            {
                "index": 2,
                "address": "",
                "metrics_method": "not-supported",
                "status": "failed",
                "metrics": {},
                "services": [],
                "collection_errors": [{"stage": "host-metrics", "type": "invalid-address"}],
            },
        ],
    }
    fake_doops_cmd = write_fake_doops(
        tmp_path,
        f"""
import base64
import json
import sys

if sys.argv[1:2] == ["targets"]:
    print("zheyin online password=TargetsSecret")
    raise SystemExit(0)

encoded = base64.b64encode(json.dumps({payload!r}).encode()).decode()
print("__SERVER_HEALTH_JSON_START__")
print("SERVER_HEALTH_B64:" + encoded)
print("__SERVER_HEALTH_JSON_END__")
""",
    )
    excel_path = tmp_path / "servers.xlsx"
    write_excel_inventory(
        excel_path,
        [
            ["Linux", "172.16.70.20", "linux", "root/TopSecret123", "linux app", "", ""],
            ["BadIP", "/", "", "administrator/AnotherSecret", "bad ip", "", ""],
        ],
    )
    collected_inventory = tmp_path / "collected.json"
    evidence_path = tmp_path / "evidence.json"

    result = subprocess.run(
        [
            sys.executable,
            str(COLLECTOR),
            "--inventory",
            str(excel_path),
            "--host-metrics",
            "--host-metrics-target",
            "zheyin",
            "--limit",
            "2",
            "--doops",
            str(fake_doops_cmd),
            "--out",
            str(collected_inventory),
            "--evidence-out",
            str(evidence_path),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=subprocess_env(),
    )

    assert result.returncode == 0, result.stderr
    inventory_text = collected_inventory.read_text(encoding="utf-8")
    evidence_text = evidence_path.read_text(encoding="utf-8")
    inventory = json.loads(inventory_text)
    assert inventory["servers"][0]["collect"]["host_metrics_status"] == "failed"
    assert inventory["servers"][0]["collection_errors"][0]["type"] == "ssh-auth-failed"
    assert inventory["servers"][1]["collection_errors"][0]["type"] == "invalid-address"
    assert "ShouldNotLeak" not in inventory_text
    assert "ShouldNotLeak" not in evidence_text
    assert "TargetsSecret" not in evidence_text
    assert "TopSecret123" not in inventory_text


def test_doops_snmp_metrics_failures_are_sanitized_and_do_not_block(tmp_path):
    payload = {
        "metrics_target": "zheyin",
        "profile": "zheyin-snmpv3-monitor",
        "servers": [
            {
                "index": 1,
                "address": "172.16.70.20",
                "metrics_method": "snmpv3",
                "status": "failed",
                "metrics": {},
                "services": [],
                "collection_errors": [{"stage": "snmp-metrics", "type": "snmp-auth-failed"}],
                "debug": "auth_key=ShouldNotLeak",
            },
            {
                "index": 2,
                "address": "/",
                "metrics_method": "snmpv3",
                "status": "failed",
                "metrics": {},
                "services": [],
                "collection_errors": [{"stage": "snmp-metrics", "type": "invalid-address"}],
            },
        ],
    }
    fake_doops_cmd = write_fake_doops(
        tmp_path,
        f"""
import base64
import json
import sys

if sys.argv[1:2] == ["targets"]:
    print("zheyin online password=TargetsSecret")
    raise SystemExit(0)

command = sys.argv[sys.argv.index("--cmd") + 1]
assert "SNMP_METRICS_PROFILE" in command
encoded = base64.b64encode(json.dumps({payload!r}).encode()).decode()
print("__SERVER_HEALTH_JSON_START__")
print("SERVER_HEALTH_B64:" + encoded)
print("__SERVER_HEALTH_JSON_END__")
""",
    )
    excel_path = tmp_path / "servers.xlsx"
    write_excel_inventory(
        excel_path,
        [
            ["Linux", "172.16.70.20", "linux", "root/TopSecret123", "linux app", "", ""],
            ["BadIP", "/", "", "administrator/AnotherSecret", "bad ip", "", ""],
        ],
    )
    collected_inventory = tmp_path / "collected.json"
    evidence_path = tmp_path / "evidence.json"

    result = subprocess.run(
        [
            sys.executable,
            str(COLLECTOR),
            "--inventory",
            str(excel_path),
            "--snmp-metrics",
            "--snmp-target",
            "zheyin",
            "--limit",
            "2",
            "--doops",
            str(fake_doops_cmd),
            "--out",
            str(collected_inventory),
            "--evidence-out",
            str(evidence_path),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=subprocess_env(),
    )

    assert result.returncode == 0, result.stderr
    inventory_text = collected_inventory.read_text(encoding="utf-8")
    evidence_text = evidence_path.read_text(encoding="utf-8")
    inventory = json.loads(inventory_text)
    assert inventory["servers"][0]["collect"]["host_metrics_status"] == "failed"
    assert inventory["servers"][0]["collect"]["metrics_method"] == "snmpv3"
    assert inventory["servers"][0]["collection_errors"][0] == {"stage": "snmp-metrics", "type": "snmp-auth-failed"}
    assert inventory["servers"][1]["collection_errors"][0] == {"stage": "snmp-metrics", "type": "invalid-address"}
    assert "ShouldNotLeak" not in inventory_text
    assert "ShouldNotLeak" not in evidence_text
    assert "TargetsSecret" not in evidence_text
    assert "TopSecret123" not in inventory_text
    assert "AnotherSecret" not in inventory_text


def test_report_marks_missing_monitor_credentials_as_unmonitorable():
    runner = load_runner_module("run_server_health_monitor_missing_monitor_credentials")

    report = runner.build_report(
        {
            "environment": {"name": "Credential gaps"},
            "servers": [
                {
                    "name": "Linux",
                    "address": "172.16.70.4",
                    "os_type": "linux",
                    "collect": {
                        "host_metrics": True,
                        "metrics_method": "ssh",
                        "metrics_probe_target": "zheyin",
                        "host_metrics_status": "failed",
                    },
                    "collection_errors": [{"stage": "host-metrics", "type": "ssh-key-missing"}],
                },
                {
                    "name": "Windows",
                    "address": "172.16.70.2",
                    "os_type": "windows",
                    "collect": {
                        "host_metrics": True,
                        "metrics_method": "winrm",
                        "metrics_probe_target": "zheyin",
                        "host_metrics_status": "failed",
                    },
                    "collection_errors": [{"stage": "host-metrics", "type": "winrm-credential-missing"}],
                },
            ],
        },
        offline=False,
        timeout=0.1,
    )

    assert report["summary"]["coverage"]["host_metrics"] == "partial-host-metrics"
    assert [server["status"] for server in report["servers"]] == ["warning", "warning"]
    assert all(server["findings"][0]["title"] == "主机指标无法监测" for server in report["servers"])


def test_doops_host_metrics_missing_payload_marks_each_server_unmonitorable(tmp_path):
    fake_doops_cmd = write_fake_doops(
        tmp_path,
        """
import sys

if sys.argv[1:2] == ["targets"]:
    print("zheyin online")
    raise SystemExit(0)

print("__SERVER_HEALTH_JSON_START__")
print("__SERVER_HEALTH_JSON_END__")
""",
    )
    excel_path = tmp_path / "servers.xlsx"
    write_excel_inventory(
        excel_path,
        [
            ["Linux", "172.16.70.20", "linux", "root/TopSecret123", "linux app", "", ""],
            ["Windows", "172.16.70.88", "windows", "administrator/AnotherSecret", "windows app", "", ""],
        ],
    )
    collected_inventory = tmp_path / "collected.json"

    result = subprocess.run(
        [
            sys.executable,
            str(COLLECTOR),
            "--inventory",
            str(excel_path),
            "--host-metrics",
            "--host-metrics-target",
            "zheyin",
            "--limit",
            "2",
            "--doops",
            str(fake_doops_cmd),
            "--out",
            str(collected_inventory),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=subprocess_env(),
    )

    assert result.returncode == 0, result.stderr
    inventory = json.loads(collected_inventory.read_text(encoding="utf-8"))
    assert [server["collect"]["host_metrics_status"] for server in inventory["servers"]] == ["failed", "failed"]
    assert [server["collection_errors"][0]["type"] for server in inventory["servers"]] == [
        "host-metrics-payload-missing",
        "host-metrics-payload-missing",
    ]


def test_report_consumes_doops_network_observation():
    runner = load_runner_module("run_server_health_monitor_doops_probe")
    report = runner.build_report(
        {
            "environment": {"name": "Doops probe"},
            "servers": [
                {
                    "name": "Portal",
                    "address": "172.16.70.4",
                    "os_type": "linux",
                    "ports": [22],
                    "collect": {"doops_probe": True, "probe_target": "zheyin"},
                    "network_observation": {
                        "mode": "doops-network-probe",
                        "probe_target": "zheyin",
                        "reachable": True,
                        "ping": {"status": "alive", "latency_ms": 8},
                        "ports": [{"port": 22, "status": "open", "latency_ms": 12}],
                    },
                },
                {
                    "name": "Legacy",
                    "address": "172.16.70.2",
                    "os_type": "windows",
                    "ports": [3389],
                    "collect": {"doops_probe": True, "probe_target": "zheyin"},
                    "network_observation": {
                        "mode": "doops-network-probe",
                        "probe_target": "zheyin",
                        "reachable": False,
                        "ping": {"status": "unreachable", "latency_ms": None},
                        "ports": [{"port": 3389, "status": "timeout", "latency_ms": None}],
                    },
                },
            ],
        },
        offline=False,
        timeout=0.1,
    )

    assert report["summary"]["coverage"]["network"] == "doops-network-probe"
    assert report["servers"][0]["status"] == "healthy"
    assert report["servers"][1]["status"] == "warning"
    finding = report["servers"][1]["findings"][0]
    assert finding["severity"] == "warning"
    assert finding["review_required"] is True
    assert finding["priority"] == "P3"
    assert finding["port_source"] == "legacy"
    assert "管理端口不可达" in finding["title"]
    assert report["servers"][0]["network"]["mode"] == "doops-network-probe"
    assert "zheyin" in report["servers"][0]["evidence_boundary"]


def test_explicit_business_port_unreachable_is_critical_with_impact_and_actions():
    runner = load_runner_module("run_server_health_monitor_business_port")
    report = runner.build_report(
        {
            "environment": {"name": "Business impact"},
            "servers": [
                {
                    "name": "Portal",
                    "address": "172.16.70.4",
                    "os_type": "linux",
                    "role": "portal web",
                    "owner": "portal-ops",
                    "department": "信息中心",
                    "business_system": "信息门户",
                    "business_domain": "办公",
                    "user_group": "全校师生",
                    "criticality": "core",
                    "has_redundancy": False,
                    "impact_note": "门户入口不可用会影响统一办事入口。",
                    "port_obligations": [
                        {"port": 443, "usage": "business", "source": "explicit", "required": True},
                    ],
                    "collect": {"doops_probe": True, "probe_target": "zheyin"},
                    "network_observation": {
                        "mode": "doops-network-probe",
                        "probe_target": "zheyin",
                        "reachable": False,
                        "ping": {"status": "unreachable", "latency_ms": None},
                        "ports": [{"port": 443, "status": "timeout", "latency_ms": None}],
                    },
                }
            ],
        },
        offline=False,
        timeout=0.1,
    )

    server = report["servers"][0]
    finding = server["findings"][0]
    assert server["status"] == "critical"
    assert server["owner"] == "portal-ops"
    assert server["department"] == "信息中心"
    assert server["priority"] == "P1"
    assert finding["severity"] == "critical"
    assert finding["priority"] == "P1"
    assert finding["due_time"] == "当日处理"
    assert finding["impact"]["business_system"] == "信息门户"
    assert finding["impact"]["user_group"] == "全校师生"
    assert "确认应用进程" in finding["recommendation"]
    assert "清单显式声明" in finding["evidence"]


def test_missing_impact_information_is_not_invented():
    runner = load_runner_module("run_server_health_monitor_missing_impact")
    report = runner.build_report(
        {
            "environment": {"name": "Missing impact"},
            "servers": [
                {
                    "name": "Unknown web",
                    "address": "172.16.70.50",
                    "os_type": "linux",
                    "port_obligations": [{"port": 443, "usage": "business", "source": "explicit", "required": True}],
                    "collect": {"doops_probe": True, "probe_target": "zheyin"},
                    "network_observation": {
                        "mode": "doops-network-probe",
                        "probe_target": "zheyin",
                        "reachable": False,
                        "ports": [{"port": 443, "status": "closed", "latency_ms": None}],
                    },
                }
            ],
        },
        offline=False,
        timeout=0.1,
    )

    finding = report["servers"][0]["findings"][0]
    assert finding["impact"]["summary"] == "业务影响未在清单中提供，需由业务侧确认。"
    assert "业务影响未在清单中提供" in finding["impact_summary"]


def test_report_compares_previous_findings_for_trends():
    runner = load_runner_module("run_server_health_monitor_trends")
    previous = {
        "servers": [
            {
                "name": "Portal",
                "address": "172.16.70.4",
                "status": "critical",
                "findings": [
                    {"title": "业务端口 443 不可达", "severity": "critical", "port": 443, "category": "network"}
                ],
            },
            {
                "name": "Legacy",
                "address": "172.16.70.2",
                "status": "warning",
                "findings": [
                    {"title": "管理端口不可达，需复核是否符合安全策略", "severity": "warning", "port": 3389, "category": "network"}
                ],
            },
        ]
    }
    report = runner.build_report(
        {
            "environment": {"name": "Trend current"},
            "servers": [
                {
                    "name": "Portal",
                    "address": "172.16.70.4",
                    "os_type": "linux",
                    "port_obligations": [{"port": 443, "usage": "business", "source": "explicit", "required": True}],
                    "collect": {"doops_probe": True, "probe_target": "zheyin"},
                    "network_observation": {
                        "mode": "doops-network-probe",
                        "probe_target": "zheyin",
                        "reachable": False,
                        "ports": [{"port": 443, "status": "closed", "latency_ms": None}],
                    },
                },
                {
                    "name": "New API",
                    "address": "172.16.70.5",
                    "os_type": "linux",
                    "port_obligations": [{"port": 8443, "usage": "business", "source": "explicit", "required": True}],
                    "collect": {"doops_probe": True, "probe_target": "zheyin"},
                    "network_observation": {
                        "mode": "doops-network-probe",
                        "probe_target": "zheyin",
                        "reachable": False,
                        "ports": [{"port": 8443, "status": "timeout", "latency_ms": None}],
                    },
                },
            ],
        },
        offline=False,
        timeout=0.1,
        previous_report=previous,
    )

    trend = report["summary"]["trend"]
    assert trend["mode"] == "compared"
    assert trend["new_findings"] == 1
    assert trend["resolved_findings"] == 1
    assert trend["persistent_findings"] == 1
    assert trend["status_changed_servers"] == 0


def test_markdown_includes_port_source_priority_recommendation_and_baseline_trend():
    runner = load_runner_module("run_server_health_monitor_markdown_details")
    report = runner.build_report(
        {
            "environment": {"name": "Markdown details"},
            "servers": [
                {
                    "name": "Legacy",
                    "address": "172.16.70.2",
                    "os_type": "windows",
                    "owner": "",
                    "department": "信息中心",
                    "ports": [3389],
                    "collect": {"doops_probe": True, "probe_target": "zheyin"},
                    "network_observation": {
                        "mode": "doops-network-probe",
                        "probe_target": "zheyin",
                        "reachable": False,
                        "ports": [{"port": 3389, "status": "timeout", "latency_ms": None}],
                    },
                }
            ],
        },
        offline=False,
        timeout=0.1,
    )
    markdown = runner.render_markdown(report)

    assert "负责人" not in markdown
    assert "业务部门" not in markdown
    assert "系统等级" not in markdown
    assert "优先级" in markdown
    assert "建议处理时限" in markdown
    assert "端口来源" in markdown
    assert "管理端口不可达，需复核是否符合安全策略" in markdown
    assert "确认是否为安全策略关闭" in markdown
    assert "业务影响未在清单中提供" in markdown
    assert "本次为基线巡检，暂无趋势对比" in markdown


def test_report_marks_ssh_winrm_and_partial_host_metrics_coverage():
    runner = load_runner_module("run_server_health_monitor_host_metrics")
    report = runner.build_report(
        {
            "environment": {"name": "Host metrics"},
            "servers": [
                {
                    "name": "Linux",
                    "address": "172.16.70.4",
                    "os_type": "linux",
                    "collect": {
                        "host_metrics": True,
                        "metrics_method": "ssh",
                        "metrics_probe_target": "zheyin",
                        "host_metrics_status": "collected",
                    },
                    "metrics": {"cpu_percent": 10, "memory_percent": 30, "disks": [{"mount": "/", "used_percent": 44}]},
                    "services": [{"name": "sshd", "status": "running", "expected": "running"}],
                },
                {
                    "name": "Windows",
                    "address": "172.16.70.88",
                    "os_type": "windows",
                    "collect": {
                        "host_metrics": True,
                        "metrics_method": "winrm",
                        "metrics_probe_target": "zheyin",
                        "host_metrics_status": "collected",
                    },
                    "metrics": {"cpu_percent": 15, "memory_percent": 50, "disks": [{"mount": "C:", "used_percent": 66}]},
                    "services": [{"name": "WinRM", "status": "running", "expected": "running"}],
                },
            ],
        },
        offline=False,
        timeout=0.1,
    )

    assert report["summary"]["coverage"]["host_metrics"] == "ssh-winrm-collected"
    assert report["summary"]["coverage"]["services"] == "ssh-winrm-collected"
    assert "zheyin" in report["servers"][0]["evidence_boundary"]
    assert "主机指标" in report["servers"][0]["evidence_boundary"]

    partial_report = runner.build_report(
        {
            "environment": {"name": "Partial metrics"},
            "servers": [
                {
                    "name": "Linux",
                    "address": "172.16.70.20",
                    "os_type": "linux",
                    "collect": {
                        "host_metrics": True,
                        "metrics_method": "ssh",
                        "metrics_probe_target": "zheyin",
                        "host_metrics_status": "failed",
                    },
                    "collection_errors": [{"stage": "host-metrics", "type": "ssh-auth-failed"}],
                }
            ],
        },
        offline=False,
        timeout=0.1,
    )

    assert partial_report["summary"]["coverage"]["host_metrics"] == "partial-host-metrics"
    assert partial_report["summary"]["coverage"]["services"] == "partial-host-metrics"
    assert partial_report["servers"][0]["status"] == "warning"
    assert partial_report["servers"][0]["findings"][0]["title"] == "主机指标无法监测"
    assert "无法监测" in partial_report["servers"][0]["evidence_boundary"]


def test_report_marks_snmp_and_partial_snmp_metrics_coverage():
    runner = load_runner_module("run_server_health_monitor_snmp_metrics")
    report = runner.build_report(
        {
            "environment": {"name": "SNMP metrics"},
            "servers": [
                {
                    "name": "Linux",
                    "address": "172.16.70.4",
                    "os_type": "linux",
                    "collect": {
                        "host_metrics": True,
                        "metrics_method": "snmpv3",
                        "metrics_probe_target": "zheyin",
                        "host_metrics_status": "collected",
                    },
                    "metrics": {"cpu_percent": 10, "memory_percent": 30, "disks": [{"mount": "/", "used_percent": 44}]},
                }
            ],
        },
        offline=False,
        timeout=0.1,
    )

    assert report["summary"]["coverage"]["host_metrics"] == "snmp-collected"
    assert report["summary"]["coverage"]["services"] == "not-supplied"
    assert "snmpv3" in report["servers"][0]["evidence_boundary"]

    partial_report = runner.build_report(
        {
            "environment": {"name": "Partial SNMP metrics"},
            "servers": [
                {
                    "name": "Linux",
                    "address": "172.16.70.20",
                    "os_type": "linux",
                    "collect": {
                        "host_metrics": True,
                        "metrics_method": "snmpv3",
                        "metrics_probe_target": "zheyin",
                        "host_metrics_status": "failed",
                    },
                    "collection_errors": [{"stage": "snmp-metrics", "type": "snmp-auth-failed"}],
                }
            ],
        },
        offline=False,
        timeout=0.1,
    )

    assert partial_report["summary"]["coverage"]["host_metrics"] == "partial-snmp-metrics"
    assert partial_report["summary"]["coverage"]["services"] == "not-supplied"
    assert partial_report["servers"][0]["status"] == "warning"
    assert any("CPU" in item for item in partial_report["summary"]["report_insights"]["coverage_gaps"])
    assert any("SNMPv3" in item for item in partial_report["summary"]["report_insights"]["metric_insights"])
    assert "无法监测" in partial_report["servers"][0]["findings"][0]["title"]


def test_report_keeps_processes_and_flags_abnormal_processes():
    runner = load_runner_module("run_server_health_monitor_processes")
    report = runner.build_report(
        {
            "environment": {"name": "Process health"},
            "servers": [
                {
                    "name": "App",
                    "address": "172.16.70.4",
                    "os_type": "linux",
                    "collect": {
                        "host_metrics": True,
                        "metrics_method": "ssh",
                        "metrics_probe_target": "zheyin",
                        "host_metrics_status": "collected",
                    },
                    "metrics": {"cpu_percent": 96.0, "memory_percent": 72.0, "disks": [{"mount": "/", "used_percent": 44}]},
                    "processes": [
                        {"pid": 101, "name": "java", "user": "app", "state": "R", "cpu_percent": 180.0, "memory_percent": 18.0},
                        {"pid": 202, "name": "legacy-worker", "user": "app", "state": "Z", "cpu_percent": 0.0, "memory_percent": 0.1},
                    ],
                }
            ],
        },
        offline=False,
        timeout=0.1,
    )
    markdown = runner.render_markdown(report)
    html = runner.render_html(report, markdown, {"status": "html_guide_selected"})

    server = report["servers"][0]
    assert report["summary"]["coverage"]["processes"] == "ssh-collected"
    assert server["processes"][0]["name"] == "java"
    assert any(item["title"] == "主要进程 CPU 占用达到严重阈值" and item["severity"] == "critical" for item in server["findings"])
    assert any(item["title"] == "发现异常进程状态" for item in server["findings"])
    assert "主要进程" in markdown
    assert "java" in html
    assert "legacy-worker" in html


def test_doops_inventory_is_marked_as_doops_collected():
    runner = load_runner_module("run_server_health_monitor_doops_inventory")
    report = runner.build_report(
        {
            "environment": {"name": "Doops live"},
            "servers": [
                {
                    "name": "hdu-node",
                    "address": "hdu",
                    "os_type": "linux",
                    "collect": {"doops": True, "network": False},
                    "metrics": {"cpu_percent": 10, "memory_percent": 25, "disks": [{"mount": "/", "used_percent": 45}]},
                    "services": [{"name": "doops-agent", "status": "running", "expected": "running"}],
                }
            ],
        },
        offline=False,
        timeout=0.1,
    )

    server = report["servers"][0]
    assert report["summary"]["coverage"]["network"] == "doops-collected"
    assert report["summary"]["coverage"]["host_metrics"] == "doops-collected"
    assert report["summary"]["coverage"]["services"] == "doops-collected"
    assert server["network"]["mode"] == "doops-collected"
    assert "doops" in server["evidence_boundary"]


def test_zheyin_self_node_report_explains_direct_doops_metrics():
    runner = load_runner_module("run_server_health_monitor_zheyin_self_node")
    inventory = {
        "environment": {"name": "Zhejiang Conservatory of Music - doops live inspection"},
        "doops_channel": {
            "target": "zheyin",
            "session": "server-health-20260514-001000",
            "transport_mode": "workspace-push",
            "target_online": True,
            "target_busy": False,
            "last_seen": "2026-05-14T00:10:00+08:00",
            "collector_info_status": "collected",
            "cleanup_status": "failed",
        },
        "servers": [
            {
                "name": "cluster-node0014.172.16.50.239",
                "address": "zheyin",
                "os_type": "linux",
                "role": "doops collector node",
                "collect": {"doops": True, "network": False, "self_node_metrics": True, "doops_target": "zheyin"},
                "metrics": {
                    "cpu_percent": 0.3,
                    "memory_percent": 3.0,
                    "load_per_core": 0.01,
                    "uptime_days": 96.27,
                    "disks": [{"mount": "/", "used_percent": 74.0}],
                },
                "services": [
                    {"name": "doops-agent", "status": "running", "expected": "running"},
                    {"name": "kubelet", "status": "running", "expected": "running"},
                ],
                "processes": [
                    {"pid": 1, "name": "systemd", "user": "root", "state": "S", "cpu_percent": 0.1, "memory_percent": 0.2},
                    {"pid": 1234, "name": "doops-agent", "user": "root", "state": "S", "cpu_percent": 0.2, "memory_percent": 0.5},
                ],
            }
        ],
    }

    report = runner.build_report(inventory, offline=False, timeout=0.1)
    markdown = runner.render_markdown(report)
    html = runner.render_html(report, markdown, {"status": "html_guide_selected"})
    ai_html = runner.render_html(report, markdown, {"status": "generated"})
    prompt = runner.build_guide_prompt(report)

    assert report["summary"]["coverage"]["host_metrics"] == "doops-self-collected"
    assert report["summary"]["coverage"]["processes"] == "doops-self-collected"
    assert report["summary"]["coverage"]["services"] == "doops-self-collected"
    assert "无需 SSH/WinRM/SNMP" in report["servers"][0]["evidence_boundary"]
    assert "zheyin doops 节点自身" in report["management_conclusion"]
    assert "zheyin doops 节点自身" in report["summary"]["management_summary"]
    assert "doops 节点自身监测" in markdown
    assert "zheyin 自身节点" in html
    assert "## 核心指标" in markdown
    assert "CPU 使用率" in html
    assert "主要进程" in markdown
    assert "doops-agent" in html
    assert "关键服务" in html
    assert "compact-report" in html
    assert "fallback-cover" in html
    assert "html-guide-visual" in html
    assert "ai-cover" in ai_html
    assert "ai-guide-stage" in ai_html
    assert "./html-assets/guide-image.png" in ai_html
    assert '<div class="guide-visual html-guide-visual"' not in ai_html
    assert "服务器矩阵" not in markdown
    assert "责任人与时限" not in markdown
    assert "复核问题清单" not in markdown
    assert "升级分析模块" not in html
    assert "负责人" not in html
    assert "业务部门" not in html
    assert "CPU" in prompt and "内存" in prompt and "磁盘" in prompt
    assert "zheyin doops 节点自身" in prompt


def test_doops_preflight_reports_sanitized_target_status(tmp_path):
    fake_doops_cmd = write_fake_doops(
        tmp_path,
        """
import sys

if sys.argv[1:2] == ["targets"]:
    assert sys.argv[sys.argv.index("--target") + 1] == "hdu"
    print("hdu online token=super-secret-token")
    raise SystemExit(0)

raise AssertionError("preflight must not execute remote commands")
""",
    )
    missing_config = tmp_path / "missing-config.json"

    result = subprocess.run(
        [
            sys.executable,
            str(COLLECTOR),
            "--preflight",
            "--environment",
            "杭电",
            "--doops",
            str(fake_doops_cmd),
            "--out",
            str(tmp_path / "unused.json"),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=subprocess_env(DOOPS_CONFIG=str(missing_config)),
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["target"] == "hdu"
    assert payload["doops_path"] == str(fake_doops_cmd)
    assert "super-secret-token" not in result.stdout
    assert "<redacted>" in result.stdout


def test_doops_targets_failure_stops_before_exec(tmp_path):
    marker = tmp_path / "exec-ran.txt"
    fake_doops_cmd = write_fake_doops(
        tmp_path,
        f"""
import sys
from pathlib import Path

if sys.argv[1:2] == ["targets"]:
    print("target offline token=top-secret")
    raise SystemExit(7)

Path({str(marker)!r}).write_text("exec ran", encoding="utf-8")
print("__SERVER_HEALTH_JSON_START__")
print('{{"hostname":"should-not-run","metrics":{{}},"services":[]}}')
print("__SERVER_HEALTH_JSON_END__")
""",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(COLLECTOR),
            "--environment",
            "zheyin",
            "--doops",
            str(fake_doops_cmd),
            "--out",
            str(tmp_path / "inventory.json"),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=subprocess_env(),
    )

    assert result.returncode != 0
    assert not marker.exists()
    assert "top-secret" not in result.stderr
    assert "targets check failed" in result.stderr


def test_collector_parses_structured_doops_targets():
    collector = load_collector_module("collect_doops_inventory_targets_parser")

    parsed = collector.parse_doops_targets(
        """
CLUSTER      INSTANCE    BUSY   LAST_SEEN
doops-zheyin node-239    false  2026-05-13T18:00:00+08:00
doops-hdu    node-101    true   2026-05-13T17:59:30+08:00 token=secret-token
"""
    )

    assert parsed["target_online"] is True
    assert parsed["target_busy"] is True
    assert parsed["gateway_mode_detected"] is True
    assert parsed["targets"][0]["cluster"] == "doops-zheyin"
    assert parsed["targets"][0]["instance"] == "node-239"
    assert "secret-token" not in parsed["raw_excerpt_redacted"]


def test_doops_workspace_mode_uses_push_read_clean_and_records_channel(tmp_path):
    excel_path = tmp_path / "servers.xlsx"
    write_excel_inventory(
        excel_path,
        [
            ["统一门户", "10.0.0.10", "Linux", "", "业务入口", "2026-05-13", "是"],
        ],
    )
    command_log = tmp_path / "commands.jsonl"
    payload = {
        "probe_target": "zheyin",
        "checked_at": "2026-05-13T18:00:00+08:00",
        "servers": [
            {
                "index": 1,
                "address": "10.0.0.10",
                "reachable": True,
                "ping": {"status": "alive", "latency_ms": 9},
                "ports": [{"port": 22, "status": "open", "latency_ms": 12}],
            }
        ],
    }
    fake_doops_cmd = write_fake_doops(
        tmp_path,
        f"""
import json
import pathlib
import sys

log = pathlib.Path({str(command_log)!r})
line = json.dumps({{"args": sys.argv[1:]}}, ensure_ascii=False) + "\\n"
log.write_text((log.read_text(encoding="utf-8") if log.exists() else "") + line, encoding="utf-8")
args = sys.argv[1:]

if args[:2] == ["targets", "--target"]:
    print("CLUSTER INSTANCE BUSY LAST_SEEN")
    print("doops-zheyin node-239 false 2026-05-13T18:00:00+08:00 token=secret-token")
    raise SystemExit(0)
if "info" in args:
    print("collector=node-239 uptime=10d memory=40%")
    raise SystemExit(0)
if "push" in args:
    raise SystemExit(0)
if "exec" in args:
    print("__SERVER_HEALTH_JSON_START__")
    print("{{}}")
    print("__SERVER_HEALTH_JSON_END__")
    raise SystemExit(0)
if "read" in args:
    path = args[args.index("--path") + 1] if "--path" in args else ""
    if path.endswith("result.json"):
        print({json.dumps(json.dumps(payload, ensure_ascii=False))})
    elif path.endswith("evidence.json"):
        print('{{"remote_collector_status":0}}')
    else:
        print("collector log token=secret-token")
    raise SystemExit(0)
if "clean" in args:
    raise SystemExit(0)
raise SystemExit(2)
""",
    )
    collected_inventory = tmp_path / "inventory.json"
    evidence_path = tmp_path / "evidence.json"

    result = subprocess.run(
        [
            sys.executable,
            str(COLLECTOR),
            "--inventory",
            str(excel_path),
            "--probe-target",
            "zheyin",
            "--doops-workspace-mode",
            "workspace",
            "--doops",
            str(fake_doops_cmd),
            "--out",
            str(collected_inventory),
            "--evidence-out",
            str(evidence_path),
            "--timeout",
            "20",
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env=subprocess_env(DOOPS_CONFIG=str(tmp_path / "missing.json")),
    )

    assert result.returncode == 0, result.stderr
    commands = [json.loads(line)["args"] for line in command_log.read_text(encoding="utf-8").splitlines()]
    assert any("push" in args for args in commands)
    assert any("read" in args for args in commands)
    assert any("clean" in args for args in commands)
    inventory = json.loads(collected_inventory.read_text(encoding="utf-8"))
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    assert inventory["doops_channel"]["target_online"] is True
    assert inventory["doops_channel"]["transport_mode"] == "workspace-push"
    assert inventory["servers"][0]["collection_trace"]["transport_mode"] == "workspace-push"
    assert inventory["servers"][0]["collection_trace"]["cleanup_status"] == "cleaned"
    assert evidence["chunks"][0]["transport_mode"] == "workspace-push"
    assert "secret-token" not in evidence_path.read_text(encoding="utf-8")


def test_doops_application_check_is_collected_as_observation(tmp_path):
    source_inventory = tmp_path / "app-inventory.json"
    source_inventory.write_text(
        json.dumps(
            {
                "environment": {"name": "应用巡检"},
                "servers": [
                    {
                        "name": "统一身份认证",
                        "doops_target": "identity-node",
                        "address": "10.0.0.10",
                        "role": "identity",
                        "criticality": "core",
                        "application_checks": [
                            {
                                "type": "k8s-deployment-image",
                                "doops_target": "zheyin",
                                "namespace": "identity",
                                "deployment": "sso-api",
                                "expected_image": "repo.example.com/sso-api:20260513",
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    fake_doops_cmd = write_fake_doops(
        tmp_path,
        """
import sys
args = sys.argv[1:]
if args[:2] == ["targets", "--target"]:
    print("CLUSTER INSTANCE BUSY LAST_SEEN")
    print("doops-zheyin node-239 false 2026-05-13T18:00:00+08:00")
    raise SystemExit(0)
if "info" in args:
    print("collector ok")
    raise SystemExit(0)
if "exec" in args:
    print("__SERVER_HEALTH_JSON_START__")
    print('{"hostname":"identity-node","platform":"Linux","os_type":"linux","metrics":{},"services":[],"collected_at":"2026-05-13T18:00:00+0800"}')
    print("__SERVER_HEALTH_JSON_END__")
    raise SystemExit(0)
if "check" in args:
    print("image mismatch: expected repo.example.com/sso-api:20260513 actual repo.example.com/sso-api:old")
    raise SystemExit(9)
raise SystemExit(2)
""",
    )
    collected_inventory = tmp_path / "inventory.json"

    result = subprocess.run(
        [
            sys.executable,
            str(COLLECTOR),
            "--inventory",
            str(source_inventory),
            "--doops",
            str(fake_doops_cmd),
            "--out",
            str(collected_inventory),
        ],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        env=subprocess_env(DOOPS_CONFIG=str(tmp_path / "missing.json")),
    )

    assert result.returncode == 0, result.stderr
    inventory = json.loads(collected_inventory.read_text(encoding="utf-8"))
    observation = inventory["servers"][0]["application_observation"][0]
    assert observation["type"] == "k8s-deployment-image"
    assert observation["status"] == "mismatch"
    assert "repo.example.com/sso-api:20260513" in observation["message"]


def test_report_renders_doops_channel_application_and_ai_review_without_changing_severity():
    runner = load_runner_module("run_server_health_monitor_doops_channel_app_ai")
    inventory = {
        "environment": {"name": "doops 应用巡检"},
        "doops_channel": {
            "target": "zheyin",
            "session": "server-health-20260513-180000",
            "transport_mode": "workspace-push",
            "target_online": True,
            "target_busy": False,
            "last_seen": "2026-05-13T18:00:00+08:00",
            "collector_info_status": "collected",
        },
        "ai_review": {
            "status": "collected",
            "scope": "summary",
            "advice": "建议先复核业务端口清单，再闭环责任人。",
        },
        "servers": [
            {
                "name": "统一身份认证",
                "address": "10.0.0.10",
                "role": "identity",
                "criticality": "core",
                "owner": "identity-owner",
                "business_system": "统一身份认证",
                "ports": [443],
                "port_obligations": [{"port": 443, "usage": "business", "source": "explicit", "required": True}],
                "collect": {"doops_probe": True, "probe_target": "zheyin"},
                "network_observation": {
                    "mode": "doops-network-probe",
                    "probe_target": "zheyin",
                    "reachable": False,
                    "ports": [{"port": 443, "status": "closed", "latency_ms": None}],
                },
                "collection_trace": {
                    "doops_target": "zheyin",
                    "session": "server-health-20260513-180000",
                    "transport_mode": "workspace-push",
                    "cleanup_status": "cleaned",
                    "remote_result_path": "/root/ws/server-health-20260513-180000/server-health/result.json",
                },
                "application_observation": [
                    {
                        "type": "k8s-deployment-image",
                        "status": "mismatch",
                        "namespace": "identity",
                        "deployment": "sso-api",
                        "expected_image": "repo.example.com/sso-api:20260513",
                        "message": "image mismatch",
                    }
                ],
            }
        ],
    }

    report = runner.build_report(inventory, offline=False, timeout=1)
    severities_before = [item["severity"] for item in report["servers"][0]["findings"]]
    markdown = runner.render_markdown(report)
    html = runner.render_html(report, markdown, {"mode": "html-guide", "status": "generated"})
    severities_after = [item["severity"] for item in report["servers"][0]["findings"]]

    assert severities_after == severities_before
    assert report["summary"]["doops_channel"]["transport_mode"] == "workspace-push"
    assert any(item["title"] == "应用部署版本与清单不一致" and item["severity"] == "critical" for item in report["servers"][0]["findings"])
    assert "doops 采集通道" in markdown
    assert "workspace-push" in markdown
    assert "AI 辅助复核" in markdown
    assert "应用一致性" in markdown
    assert "AI 辅助复核" in html


def test_text_integrity_checker_rejects_bad_markers(tmp_path):
    bad_marker = "".join(chr(codepoint) for codepoint in (0x951F, 0x65A4, 0x62F7))
    bad_file = tmp_path / "bad.md"
    bad_file.write_text("这是一段坏文本：" + bad_marker + " and " + "?" * 2, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(TEXT_CHECK), "--path", str(bad_file)],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=subprocess_env(),
    )

    assert result.returncode == 1
    assert bad_marker in result.stdout
    assert "?" * 2 in result.stdout


def test_text_integrity_checker_accepts_skill_sources():
    result = subprocess.run(
        [sys.executable, str(TEXT_CHECK)],
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=subprocess_env(),
    )

    assert result.returncode == 0, result.stdout + result.stderr


def test_skill_requires_user_confirmation_before_html_css_guide():
    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    doops_reference = (ROOT / "references" / "doops-monitoring.md").read_text(encoding="utf-8")
    runner_text = (ROOT / "scripts" / "run_server_health_monitor.py").read_text(encoding="utf-8")

    first = "生成导览图必须优先由 Codex/助手自主使用 GPT 生图能力"
    fallback = "若自主 GPT 生图失败，再询问用户是否提供 API Key"
    html_confirmation = "用户不提供 API Key 或明确不使用 AI 导览图时，必须先询问并取得用户确认"

    assert first in skill_text
    assert fallback in skill_text
    assert html_confirmation in skill_text
    assert skill_text.index(first) < skill_text.index(fallback) < skill_text.index(html_confirmation)
    assert "不提供 API Key 时，直接使用内置中文 HTML/CSS 导览图" not in skill_text
    assert "--out reports/zheyin-self-node --guide-mode html-guide" not in skill_text
    assert "--out reports/zheyin-self-node --guide-mode html-guide" not in doops_reference
    assert "否则 HTML/CSS" not in runner_text
    assert "auto 缺少明确导览图决策时中止" in runner_text


def test_skill_documents_zheyin_self_node_as_default_monitoring_path():
    skill_text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
    doops_reference = (ROOT / "references" / "doops-monitoring.md").read_text(encoding="utf-8")
    schema_reference = (ROOT / "references" / "inventory-schema.md").read_text(encoding="utf-8")
    quality_reference = (ROOT / "references" / "report-quality.md").read_text(encoding="utf-8")

    assert "zheyin 自身节点健康巡检" in skill_text
    assert "hdu 自身节点健康巡检" in skill_text
    assert "doops-only" in skill_text
    assert "do not enable `--host-metrics`, `--snmp-metrics`, SSH, WinRM, or SNMPv3" in skill_text
    assert "python scripts/collect_doops_inventory.py --environment zheyin --out <REPORT_HOME>/zheyin-self-node/inventory.json" in skill_text
    assert "python scripts/collect_doops_inventory.py --environment hdu --out <REPORT_HOME>/hdu-self-node/inventory.json" in skill_text
    assert "Report Output Location (Hard Rule)" in skill_text
    assert "vibe实验室" in skill_text and "巡检报告report" in skill_text
    assert "--out reports/" not in skill_text
    assert "doops 节点自身" in doops_reference
    assert "无需 SSH/WinRM/SNMPv3" in doops_reference
    assert "Do not run SSH/WinRM/SNMPv3 when the user asks to test zheyin or 杭电 managed node CPU/memory/disk health" in doops_reference
    assert '"self_node_metrics": true' in schema_reference
    assert "doops-self-collected" in schema_reference
    assert "导览图提示词必须明确" in quality_reference


def test_source_and_installed_skill_files_are_synced():
    assert INSTALLED_SKILL.is_dir()
    for relative in SYNCED_FILES:
        source = (ROOT / relative).read_text(encoding="utf-8")
        installed = (INSTALLED_SKILL / relative).read_text(encoding="utf-8")
        assert installed == source, f"installed file drifted: {relative}"
