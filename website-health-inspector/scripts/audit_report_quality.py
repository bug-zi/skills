from __future__ import annotations

import argparse
import collections
import hashlib
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

HTML_ASSET_DIR = "html-assets"
SCREENSHOT_ASSET_DIR = "screenshots"
DELIVERY_DIR = "delivery"
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}


def read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def clean_html_text(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def repeated_paragraphs(markup: str) -> list[tuple[int, str]]:
    paragraphs = []
    for raw in re.findall(r"<p[^>]*>(.*?)</p>", markup, flags=re.S):
        clean = clean_html_text(raw)
        if clean.startswith("证据：") or clean.startswith("下一份证据：") or clean.startswith("下一证据："):
            continue
        if len(clean) > 20:
            paragraphs.append(clean)
    counts = collections.Counter(paragraphs)
    return sorted(((count, text) for text, count in counts.items() if count > 1), reverse=True)


def missing_anchors(markup: str) -> list[str]:
    hrefs = re.findall(r'href="#([^"]+)"', markup)
    ids = set(re.findall(r'id="([^"]+)"', markup))
    return [item for item in hrefs if item not in ids]


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret)\\s*[:=]\\s*['\\\"]?[A-Za-z0-9_./+=-]{16,}"),
]

UNCLEAR_PLACEHOLDER_PATTERNS = [
    "可能影响部分页面体验或需要后续排查",
    "请检查",
    "建议尽快排查",
    "需进一步核查。",
    "Review needed",
    "Review and fix",
]


def unclear_placeholder_phrases(text: str) -> list[str]:
    value = str(text or "")
    hits = []
    for phrase in UNCLEAR_PLACEHOLDER_PATTERNS:
        if phrase in value:
            hits.append(phrase)
    return hits


def has_question_mark_garble(text: str) -> bool:
    return "???" in text or "？？？" in text or bool(re.search(r"[?？]{4,}", text))


def browser_screenshot_count(report: dict) -> int:
    for module in report.get("module_reports", []) or []:
        if module.get("report_type") != "browser-inspection":
            continue
        files: list[str] = []
        for item in module.get("screenshots") or []:
            if isinstance(item, str):
                files.append(item)
            elif isinstance(item, dict):
                path = item.get("path") or item.get("file") or item.get("screenshot")
                if path:
                    files.append(str(path))
        for page in module.get("visited_pages") or []:
            if page.get("screenshot"):
                files.append(str(page.get("screenshot")))
        return len(dict.fromkeys(item for item in files if item))
    return 0


def browser_performance_metrics_present(report: dict) -> bool:
    for module in report.get("module_reports", []) or []:
        if module.get("report_type") != "browser-inspection":
            continue
        metrics = module.get("metrics") or {}
        visited = module.get("visited_pages") or []
        has_summary_metrics = all(key in metrics for key in ["checked_pages", "avg_open_time_ms", "max_open_time_ms", "slow_pages"])
        has_page_metrics = any(isinstance(page.get("performance"), dict) and "open_time_ms" in page.get("performance", {}) for page in visited)
        checked_pages = metrics.get("checked_pages")
        if checked_pages == 0 and not visited:
            return has_summary_metrics
        return bool(has_summary_metrics and has_page_metrics)
    return True


def performance_snapshot_present(markup: str, md_text: str, report: dict) -> bool:
    has_browser = any((module.get("report_type") == "browser-inspection") for module in report.get("module_reports", []) or [])
    if not has_browser:
        return True
    combined = markup + "\n" + md_text
    return "性能快照" in combined and "打开时间" in combined


def absolute_image_refs(markup: str) -> list[str]:
    refs = re.findall(r'<img[^>]+src="([^"]+)"', markup, flags=re.I)
    bad = []
    for ref in refs:
        parsed = urlparse(ref)
        if parsed.scheme == "file" or re.match(r"^[A-Za-z]:[\\/]", ref) or ref.startswith("\\\\"):
            bad.append(ref)
    return bad


def guide_image_refs(markup: str) -> list[str]:
    refs = []
    for match in re.finditer(r'<img\b([^>]+)>', markup, flags=re.I):
        tag = match.group(0)
        src_match = re.search(r'src="([^"]+)"', tag, flags=re.I)
        if (
            "guide-cover-image" in tag
            or "GPT 生成的总报告文字导览架构图" in tag
            or (src_match and ("ai-report-guide" in src_match.group(1) or "ai_report_guide_image" in src_match.group(1)))
        ):
            refs.append(src_match.group(1) if src_match else tag)
    return refs


def html_guide_fallback_present(markup: str) -> bool:
    return 'class="html-guide-visual"' in markup and "报告图文导览" in markup and "阅读路径与重点证据" in markup


def report_contains_generation_prompt(markup: str) -> bool:
    prompts = [
        "OPENAI_API_KEY",
        "--guide-mode",
        "--skip-ai-guide-image",
        "配置 .env",
        "配置 <code>.env</code>",
        "图片接口 API Key",
        "AI 生图调用失败",
        "跳过 AI 生图",
        "请设置 OPENAI_API_KEY",
    ]
    return any(item in markup for item in prompts)


def non_packaged_image_refs(markup: str) -> list[str]:
    refs = re.findall(r'<img[^>]+src="([^"]+)"', markup, flags=re.I)
    bad = []
    for ref in refs:
        parsed = urlparse(ref)
        if parsed.scheme in {"http", "https", "blob"}:
            continue
        if parsed.scheme == "data":
            bad.append(ref[:80])
            continue
        normalized = ref.replace("\\", "/").lstrip("./")
        if not normalized.startswith(f"{HTML_ASSET_DIR}/"):
            bad.append(ref)
    return bad


def embedded_image_refs(markup: str) -> list[str]:
    refs = re.findall(r'<img[^>]+src="([^"]+)"', markup, flags=re.I)
    return [ref for ref in refs if ref.startswith("data:image/")]


def root_loose_images(path: Path) -> list[str]:
    if not path.exists():
        return []
    return sorted(item.name for item in path.iterdir() if item.is_file() and item.suffix.lower() in IMAGE_EXTENSIONS)


def secret_hits(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in SECRET_PATTERNS:
        for match in pattern.findall(text):
            value = match if isinstance(match, str) else "secret-like"
            hits.append(str(value)[:40])
    return hits[:10]


def load_manifest(run_dir: Path) -> dict:
    path = run_dir / "delivery-manifest.json"
    if not path.exists():
        return {}
    try:
        return read_json(path)
    except json.JSONDecodeError:
        return {"_invalid_json": True}


def delivery_paths(run_dir: Path) -> dict[str, Path]:
    delivery_dir = run_dir / DELIVERY_DIR
    return {
        "delivery_dir": delivery_dir,
        "html": delivery_dir / "final-report.html",
        "pdf": delivery_dir / "final-report.pdf",
        "json": delivery_dir / "final-report.json",
        "md": delivery_dir / "final-report.md",
        "html_assets": delivery_dir / HTML_ASSET_DIR,
        "screenshots": delivery_dir / SCREENSHOT_ASSET_DIR,
    }


def non_empty_file(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


def login_status_consistent(report: dict, markup: str) -> bool:
    browser_modules = [
        module for module in report.get("module_reports", []) or []
        if module.get("report_type") == "browser-inspection"
    ]
    has_success = any(str((module.get("login") or {}).get("status") or "").lower() == "success" for module in browser_modules)
    if not has_success:
        return True
    return "登录状态未确认" not in markup and "自动化登录态信号未确认" not in markup


def audit_structured(run_dir: Path, iteration: int, expected_quality_outputs: list[Path] | None = None) -> dict:
    report_path = run_dir / "final-report.json"
    html_path = run_dir / "final-report.html"
    md_path = run_dir / "final-report.md"
    qa_path = run_dir / "quality-audit.md"
    qa_json_path = run_dir / "quality-audit.json"
    manifest_json_path = run_dir / "delivery-manifest.json"
    manifest_md_path = run_dir / "delivery-manifest.md"
    expected_quality_outputs = [Path(item).resolve() for item in (expected_quality_outputs or [])]
    expected_qa_md = qa_path.resolve() in expected_quality_outputs
    expected_qa_json = qa_json_path.resolve() in expected_quality_outputs
    report = read_json(report_path) if report_path.exists() else {}
    markup = read_text(html_path)
    md_text = read_text(md_path)
    manifest = load_manifest(run_dir)
    delivery = delivery_paths(run_dir)
    delivery_markup = read_text(delivery["html"])
    delivery_json_text = read_text(delivery["json"])
    json_text = read_text(report_path)
    markup_for_images = delivery_markup or markup
    combined_reader_text = markup + "\n" + md_text + "\n" + json.dumps(report, ensure_ascii=False)
    unclear_phrases = unclear_placeholder_phrases(combined_reader_text)
    modules = [item.get("report_type") for item in report.get("module_reports", [])]
    findings = report.get("priority_findings", [])
    screenshot_count = browser_screenshot_count(report)
    screenshot_count = browser_screenshot_count(report)
    folds = markup.count('class="fold-section"')
    duplicate_paragraphs = repeated_paragraphs(markup)
    bad_anchors = missing_anchors(markup)
    bad_image_refs = absolute_image_refs(markup_for_images)
    unpackaged_image_refs = non_packaged_image_refs(markup_for_images)
    embedded_refs = embedded_image_refs(markup_for_images)
    guide_refs = len(guide_image_refs(markup))
    html_guide_ready = html_guide_fallback_present(markup)
    guide_visual_ready = html_guide_ready or guide_refs == 1
    old_missing_guide_only = "请设置 OPENAI_API_KEY 后重新运行 render_report.py" in markup and not html_guide_ready
    generation_prompt_in_report = report_contains_generation_prompt(markup)
    delivery_root_images = root_loose_images(delivery["delivery_dir"])
    delivery_html_asset_count = len(root_loose_images(delivery["html_assets"]))
    delivery_screenshot_count = len(root_loose_images(delivery["screenshots"]))
    browser_perf_ready = browser_performance_metrics_present(report)
    perf_snapshot_ready = performance_snapshot_present(markup, md_text, report)
    legacy_htmls = sorted(
        item.name
        for item in run_dir.glob("final-*-health-report.html")
        if item.name != "final-report.html"
    )
    archived_legacy_htmls = sorted(
        item.name for item in (run_dir / "_archived-nonfinal-html").glob("final-*-health-report.html")
    )
    missing_formal_markers = [
        label
        for label, marker in {
            "GPT 图文导览封面": '<section class="guide-cover"',
            "折叠式交互章节": 'class="fold-section"',
            "阅读导航": 'class="report-nav"',
            "正式审计报告样式": "--paper:",
        }.items()
        if marker not in markup
    ]
    checks = {
        "official_html_exists": html_path.exists(),
        "official_pdf_exists": non_empty_file(run_dir / "final-report.pdf"),
        "structured_json_exists": report_path.exists(),
        "markdown_summary_exists": md_path.exists(),
        "quality_audit_exists": qa_path.exists() or expected_qa_md,
        "quality_audit_json_exists": qa_json_path.exists() or expected_qa_json,
        "delivery_manifest_json_exists": manifest_json_path.exists(),
        "delivery_manifest_md_exists": manifest_md_path.exists(),
        "delivery_package_exists": delivery["delivery_dir"].exists(),
        "delivery_html_exists": delivery["html"].exists(),
        "delivery_pdf_exists": non_empty_file(delivery["pdf"]),
        "delivery_html_assets_exists": delivery["html_assets"].exists(),
        "delivery_screenshots_exists": screenshot_count == 0 or (delivery["screenshots"].exists() and delivery_screenshot_count > 0),
        "delivery_root_has_no_loose_images": not delivery_root_images,
        "formal_template_markers": not missing_formal_markers,
        "guide_cover_ready": (guide_refs == 1 or html_guide_ready) and '<section class="guide-cover"' in markup,
        "guide_image_once": guide_refs in {0, 1} and '<section class="guide-cover"' in markup,
        "html_guide_fallback_present": guide_visual_ready,
        "no_old_missing_guide_only": not old_missing_guide_only,
        "no_generation_prompt_in_report": not generation_prompt_in_report,
        "fold_sections_sufficient": folds >= 8 and "data-toggle-all" in markup,
        "no_duplicate_paragraphs": not duplicate_paragraphs,
        "no_bad_anchors": not bad_anchors,
        "browser_module_present": "browser-inspection" in modules,
        "root_has_no_nonfinal_html": not legacy_htmls,
        "manifest_ready": bool(manifest.get("ready_to_deliver")) if manifest else False,
        "no_replacement_char": "\ufffd" not in markup and "\ufffd" not in md_text,
        "no_question_mark_garble": not has_question_mark_garble(markup + "\n" + md_text + "\n" + json.dumps(report, ensure_ascii=False)),
        "clear_management_language": not unclear_phrases,
        "no_secret_like_text": not secret_hits(markup + "\n" + md_text + "\n" + json_text + "\n" + delivery_json_text),
        "login_status_consistent": login_status_consistent(report, markup),
        "nav_links_compact": markup.count('<a href="#') == 8,
        "screenshot_gallery_present": screenshot_count == 0 or ("哪些证据值得优先看" in markup and 'class="screenshot-gallery"' in markup and markup.count('class="evidence-shot"') >= min(4, screenshot_count)),
        "portable_image_refs": not bad_image_refs,
        "packaged_image_refs": not unpackaged_image_refs,
        "no_embedded_images": not embedded_refs,
        "health_baseline_present": "健康数据基线" in markup and "不健康与需关注数据" in markup,
        "browser_performance_metrics_present": browser_perf_ready,
        "performance_snapshot_present": perf_snapshot_ready,
        "attention_index_present": "不健康索引" in markup and "哪些内容进入重点分析" in markup,
        "advanced_delivery_components": all(
            marker in markup
            for marker in [
                "可直接放进工单或周报的一段话",
                "不健康项主要集中在哪里",
                'class="retest-timeline"',
                'class="evidence-pack"',
            ]
        ),
        "copy_summary_control": 'data-copy-target="handoff-summary"' in markup and 'data-copy-source="handoff-summary"' in markup,
        "active_nav_scrollspy": 'aria-current' in markup and "IntersectionObserver" in markup and "is-active" in markup,
    }
    critical_checks = [
        "official_html_exists",
        "official_pdf_exists",
        "structured_json_exists",
        "formal_template_markers",
        "root_has_no_nonfinal_html",
        "no_replacement_char",
        "no_question_mark_garble",
        "clear_management_language",
        "no_secret_like_text",
        "portable_image_refs",
        "packaged_image_refs",
        "no_embedded_images",
        "guide_cover_ready",
        "no_old_missing_guide_only",
        "no_generation_prompt_in_report",
        "delivery_package_exists",
        "delivery_html_exists",
        "delivery_pdf_exists",
        "delivery_html_assets_exists",
        "delivery_screenshots_exists",
        "delivery_root_has_no_loose_images",
    ]
    failed = [name for name, ok in checks.items() if not ok]
    status = "pass"
    if any(not checks.get(name) for name in critical_checks):
        status = "fail"
    elif failed:
        status = "warning"
    return {
        "schema_version": 1,
        "iteration": iteration,
        "status": status,
        "run_dir": str(run_dir),
        "html_report": str(html_path),
        "score": report.get("score", "N/A"),
        "overall_status": report.get("overall_status", "unknown"),
        "modules": modules,
        "metrics": {
            "folds": folds,
            "duplicate_paragraph_groups": len(duplicate_paragraphs),
            "bad_anchors": len(bad_anchors),
            "guide_refs": guide_refs,
            "html_guide_fallback": int(html_guide_ready),
            "nav_links": markup.count('<a href="#'),
            "browser_screenshots": screenshot_count,
            "evidence_shots": markup.count('class="evidence-shot"'),
            "absolute_image_refs": len(bad_image_refs),
            "unpackaged_image_refs": len(unpackaged_image_refs),
            "embedded_image_refs": len(embedded_refs),
            "delivery_root_loose_images": len(delivery_root_images),
            "delivery_html_assets": delivery_html_asset_count,
            "delivery_screenshots": delivery_screenshot_count,
            "browser_performance_metrics_present": int(browser_perf_ready),
            "performance_snapshot_present": int(perf_snapshot_ready),
            "findings": len(findings),
            "root_nonfinal_html": len(legacy_htmls),
            "archived_nonfinal_html": len(archived_legacy_htmls),
        },
        "checks": checks,
        "failed_checks": failed,
        "details": {
            "missing_formal_markers": missing_formal_markers,
            "legacy_htmls": legacy_htmls,
            "archived_legacy_htmls": archived_legacy_htmls,
            "bad_anchors": bad_anchors,
            "absolute_image_refs": bad_image_refs[:10],
            "unpackaged_image_refs": unpackaged_image_refs[:10],
            "embedded_image_refs": embedded_refs[:10],
            "old_missing_guide_only": old_missing_guide_only,
            "generation_prompt_in_report": generation_prompt_in_report,
            "delivery_root_loose_images": delivery_root_images[:10],
            "duplicate_paragraphs": duplicate_paragraphs[:3],
            "unclear_placeholder_phrases": unclear_phrases[:10],
            "secret_hits": secret_hits(markup + "\n" + md_text + "\n" + json_text + "\n" + delivery_json_text),
        },
    }


def refresh_delivery_manifest(run_dir: Path, structured: dict | None = None) -> None:
    manifest_path = run_dir / "delivery-manifest.json"
    if not manifest_path.exists():
        return
    payload = read_json(manifest_path)
    structured = structured or audit_structured(run_dir, 0)
    payload["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    artifacts = payload.get("artifacts", {})
    delivery = delivery_paths(run_dir)
    artifacts.setdefault("delivery_dir", {"path": str(delivery["delivery_dir"])})
    artifacts.setdefault("delivery_html", {"path": str(delivery["html"])})
    artifacts.setdefault("delivery_html_assets_dir", {"path": str(delivery["html_assets"])})
    artifacts.setdefault("delivery_screenshots_dir", {"path": str(delivery["screenshots"])})
    for item in artifacts.values():
        path = Path(str(item.get("path") or ""))
        item["exists"] = path.exists()
        if path.exists() and path.is_dir():
            files = [child for child in path.glob("*") if child.is_file()]
            item["files"] = len(files)
            item["bytes"] = sum(child.stat().st_size for child in files)
            item["sha256"] = ""
        else:
            item["bytes"] = path.stat().st_size if path.exists() and path.is_file() else 0
            item["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() and path.is_file() else ""
    payload["archived_nonfinal_html"] = [
        {
            "path": str(path),
            "exists": path.exists(),
            "bytes": path.stat().st_size if path.exists() else 0,
        }
        for path in sorted((run_dir / "_archived-nonfinal-html").glob("final-*-health-report.html"))
    ]
    root_nonfinal = sorted(
        path for path in run_dir.glob("final-*-health-report.html") if path.name != "final-report.html"
    )
    checks = payload.setdefault("checks", {})
    checks["quality_audit_exists"] = (run_dir / "quality-audit.md").exists()
    checks["quality_audit_json_exists"] = (run_dir / "quality-audit.json").exists()
    checks["root_has_no_nonfinal_html"] = not root_nonfinal
    checks["official_html_exists"] = (run_dir / "final-report.html").exists()
    checks["structured_json_exists"] = (run_dir / "final-report.json").exists()
    checks["markdown_summary_exists"] = (run_dir / "final-report.md").exists()
    checks["delivery_package_exists"] = delivery["delivery_dir"].exists()
    checks["delivery_html_exists"] = delivery["html"].exists()
    checks["delivery_pdf_exists"] = non_empty_file(delivery["pdf"])
    checks["delivery_html_assets_exists"] = delivery["html_assets"].exists()
    checks["delivery_screenshots_exists"] = delivery["screenshots"].exists()
    checks["delivery_root_has_no_loose_images"] = not root_loose_images(delivery["delivery_dir"])
    quality_status = str(structured.get("status") or "missing")
    checks["quality_gate_not_failed"] = quality_status != "fail"
    payload["counts"] = {
        "artifacts_present": sum(1 for item in artifacts.values() if item.get("exists")),
        "root_nonfinal_html": len(root_nonfinal),
        "archived_nonfinal_html": len(payload["archived_nonfinal_html"]),
        "delivery_html_assets": len(root_loose_images(delivery["html_assets"])),
        "delivery_screenshots": len(root_loose_images(delivery["screenshots"])),
    }
    payload["package_complete"] = all(
        checks.get(key)
        for key in [
            "official_html_exists",
            "structured_json_exists",
            "markdown_summary_exists",
            "root_has_no_nonfinal_html",
            "delivery_package_exists",
            "delivery_html_exists",
            "delivery_pdf_exists",
            "delivery_html_assets_exists",
            "delivery_screenshots_exists",
            "delivery_root_has_no_loose_images",
        ]
    )
    payload["quality_gate_status"] = quality_status
    payload["quality_gate_failed_checks"] = structured.get("failed_checks", [])
    payload["ready_to_deliver"] = bool(
        payload["package_complete"]
        and checks.get("quality_audit_exists")
        and checks.get("quality_audit_json_exists")
        and checks.get("quality_gate_not_failed")
    )
    payload["official_delivery_dir"] = str(delivery["delivery_dir"])
    payload["official_delivery_entry"] = str(delivery["html"])
    payload["delivery_rule"] = "Share the whole delivery/ folder. Open delivery/final-report.html. HTML images are under html-assets/ and complete screenshot evidence is under screenshots/."
    manifest_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = run_dir / "delivery-manifest.md"
    if md_path.exists():
        lines = [
            "# 报告交付清单",
            "",
            "## 交付状态",
            "",
            f"- 状态：{'可以交付' if payload.get('ready_to_deliver') else '暂缓交付'}",
            f"- 生成时间：`{payload.get('generated_at', '')}`",
            f"- 根目录非正式 HTML：{payload.get('counts', {}).get('root_nonfinal_html', 0)} 个",
            f"- 已归档非正式 HTML：{payload.get('counts', {}).get('archived_nonfinal_html', 0)} 个",
            f"- HTML 图片：{payload.get('counts', {}).get('delivery_html_assets', 0)} 个",
            f"- 截图证据：{payload.get('counts', {}).get('delivery_screenshots', 0)} 个",
            "",
            "## 正式入口",
            "",
            f"- 交付包：`{payload.get('official_delivery_dir', delivery['delivery_dir'])}`",
            f"- HTML：`{payload.get('official_delivery_entry', delivery['html'])}`",
            "- 规则：发送整个 `delivery/` 文件夹；不要只发送单个 HTML，也不要交付 `final-*-health-report.html`。",
            "- 图片目录：HTML 正文只引用 `html-assets/`；完整截图证据归档在 `screenshots/`。",
            "",
            "## 关键检查",
            "",
            *(f"- {key}：{'通过' if value else '未通过'}" for key, value in checks.items()),
            "",
            "## 交付文件",
            "",
        ]
        for key, item in artifacts.items():
            status = "存在" if item.get("exists") else "未生成"
            digest = f"，sha256 `{str(item.get('sha256') or '')[:12]}`" if item.get("sha256") else ""
            lines.append(f"- {key}：`{item.get('path')}`（{status}，{item.get('bytes', 0)} bytes{digest}）")
        lines.extend(["", "## 已归档的非正式 HTML", ""])
        if payload.get("archived_nonfinal_html"):
            for item in payload["archived_nonfinal_html"]:
                status = "存在" if item.get("exists") else "缺失"
                lines.append(f"- `{item.get('path')}`（{status}）")
        else:
            lines.append("- 无。")
        lines.append("")
        md_path.write_text("\n".join(lines), encoding="utf-8-sig")


def audit(run_dir: Path, iteration: int) -> str:
    structured = audit_structured(run_dir, iteration)
    report_path = run_dir / "final-report.json"
    html_path = run_dir / "final-report.html"
    report = read_json(report_path) if report_path.exists() else {}
    markup = read_text(html_path)
    modules = [item.get("report_type") for item in report.get("module_reports", [])]
    findings = report.get("priority_findings", [])
    screenshot_count = browser_screenshot_count(report)
    score = report.get("score", "N/A")
    status = report.get("overall_status", "unknown")
    folds = markup.count('class="fold-section"')
    duplicate_paragraphs = repeated_paragraphs(markup)
    bad_anchors = missing_anchors(markup)
    bad_image_refs = absolute_image_refs(markup)
    unpackaged_image_refs = non_packaged_image_refs(markup)
    embedded_refs = embedded_image_refs(markup)
    guide_refs = len(guide_image_refs(markup))
    html_guide_ready = html_guide_fallback_present(markup)
    old_missing_guide_only = "请设置 OPENAI_API_KEY 后重新运行 render_report.py" in markup and not html_guide_ready
    generation_prompt_in_report = report_contains_generation_prompt(markup)
    delivery = delivery_paths(run_dir)
    delivery_root_images = root_loose_images(delivery["delivery_dir"])
    delivery_html_asset_count = len(root_loose_images(delivery["html_assets"]))
    delivery_screenshot_count = len(root_loose_images(delivery["screenshots"]))
    browser_perf_ready = browser_performance_metrics_present(report)
    perf_snapshot_ready = performance_snapshot_present(markup, read_text(run_dir / "final-report.md"), report)
    delivery_manifest_json = run_dir / "delivery-manifest.json"
    delivery_manifest_md = run_dir / "delivery-manifest.md"
    legacy_htmls = sorted(
        item.name
        for item in run_dir.glob("final-*-health-report.html")
        if item.name != "final-report.html"
    )
    archived_legacy_htmls = sorted(
        item.name for item in (run_dir / "_archived-nonfinal-html").glob("final-*-health-report.html")
    )
    formal_markers = {
        "GPT 图文导览封面": '<section class="guide-cover"',
        "折叠式交互章节": 'class="fold-section"',
        "阅读导航": 'class="report-nav"',
        "正式审计报告样式": "--paper:",
    }
    missing_formal_markers = [
        label for label, marker in formal_markers.items() if marker not in markup
    ]

    strengths = []
    weaknesses = []
    upgrades = []

    if not missing_formal_markers:
        strengths.append("HTML 使用正式报告模板渲染，具备 GPT 导览封面、阅读导航、折叠章节和审计报告视觉体系。")
    else:
        weaknesses.append("HTML 缺少正式模板标记：" + "、".join(missing_formal_markers) + "，可能是临时手写报告或旧模板产物。")
        upgrades.append("必须重新运行 `render_report.py` 或 `run_health_inspection.py`，并只交付 `final-report.html`。")

    if legacy_htmls:
        weaknesses.append("运行目录存在非正式 HTML 产物：" + "、".join(legacy_htmls) + "，容易让读者误打开低质量临时报告。")
        upgrades.append("重新运行 `render_report.py`，渲染器会自动把临时 `final-*-health-report.html` 移入 `_archived-nonfinal-html`。")

    if "browser-inspection" in modules and browser_perf_ready and perf_snapshot_ready:
        strengths.append("浏览器实测报告已包含页面打开时间性能快照，可观察平均打开时间、最慢页面和慢页面数。")
    elif "browser-inspection" in modules:
        weaknesses.append("浏览器实测报告缺少页面打开时间性能快照或结构化性能指标，无法支撑网速/打开时间观测。")
        upgrades.append("重新运行深度浏览巡检并重新渲染报告，确保 `browser-inspection.metrics` 与正文性能快照同时存在。")
    elif archived_legacy_htmls:
        strengths.append("运行目录根部已清理非正式 HTML；历史草稿已归档到 `_archived-nonfinal-html`，降低误交付旧报告的风险。")
    else:
        strengths.append("运行目录根部未发现非正式 `final-*-health-report.html`，对外交付入口保持唯一。")

    if delivery_manifest_json.exists() and delivery_manifest_md.exists():
        strengths.append("报告已生成 `delivery-manifest.json` 与 `delivery-manifest.md`，正式入口、质量审计和归档草稿的交付关系清楚。")
    else:
        weaknesses.append("缺少交付清单 `delivery-manifest.json` 或 `delivery-manifest.md`，新对话或人工交付时仍可能拿错文件。")
        upgrades.append("重新运行 `render_report.py` 生成交付清单，并在最终回复中只引用清单标记的正式入口。")

    if delivery["html"].exists() and delivery_html_asset_count:
        strengths.append(f"已生成干净交付包 `delivery/`，HTML 图片集中在 `delivery/{HTML_ASSET_DIR}/`，可直接发送整个交付文件夹。")
    else:
        weaknesses.append("尚未形成完整 `delivery/` 交付包，或 `html-assets/` 中没有报告实际引用图片。")
        upgrades.append("重新运行 `render_report.py`，生成 `delivery/final-report.html`、`delivery/html-assets/` 和 `delivery/screenshots/`。")

    if screenshot_count == 0 or delivery_screenshot_count:
        strengths.append(f"完整截图证据已归档到 `delivery/{SCREENSHOT_ASSET_DIR}/`，当前归档 {delivery_screenshot_count} 个图片文件。")
    else:
        weaknesses.append("浏览器模块存在截图证据，但 `delivery/screenshots/` 未收集到对应图片。")
        upgrades.append("渲染阶段应从浏览器模块和证据文件中收集截图，统一复制到 `delivery/screenshots/`。")

    if not delivery_root_images:
        strengths.append("`delivery/` 根目录没有散乱图片，报告文件、HTML 图片和截图证据分区清晰。")
    else:
        weaknesses.append("`delivery/` 根目录仍有散乱图片：" + "、".join(delivery_root_images[:6]) + "。")
        upgrades.append("交付包根目录只保留 HTML/JSON/Markdown/清单文件，图片必须进入 `html-assets/` 或 `screenshots/`。")

    if guide_refs == 1 and '<section class="guide-cover"' in markup:
        strengths.append("GPT 图文导览已封面化，且导览图只引用一次，避免正文重复展示同一张图。")
    elif html_guide_ready and '<section class="guide-cover"' in markup:
        strengths.append("AI 导览图未生成时，首页已自动切换为 HTML 图文导览，报告仍具备首屏阅读架构图。")
    else:
        weaknesses.append("首页导览封面结构异常：既没有可用 AI 导览图，也没有 HTML 图文导览兜底。")
        upgrades.append("检查 `render_guide_cover`，确保 AI 图失败时自动渲染 `html-guide-visual`。")

    if old_missing_guide_only:
        weaknesses.append("首页仍只有旧版缺图提示，缺少 HTML 图文导览兜底。")
        upgrades.append("移除旧版单句缺图占位，改为在运行 skill 时前置确认生图方式，并在报告中渲染正式图文导览。")

    if generation_prompt_in_report:
        weaknesses.append("最终 HTML 中仍出现 API Key 配置或跳过生图提示，混入了运行过程说明。")
        upgrades.append("把生图方式选择放在 skill 调用过程里完成，最终报告只保留正式导览结果。")
    else:
        strengths.append("最终 HTML 未出现 API Key 配置或跳过生图提示，运行过程与正式报告表达已分离。")

    if folds >= 8 and "data-toggle-all" in markup:
        strengths.append(f"报告已使用 {folds} 个折叠章节，并提供展开/收起全部按钮，默认阅读长度显著缩短。")
    else:
        weaknesses.append("折叠章节不足或缺少全局展开按钮，长表格和技术证据仍可能压迫阅读。")
        upgrades.append("将评分、浏览器证据、系统矩阵、模块证据、复测脚本和技术附录默认折叠。")

    if not duplicate_paragraphs:
        strengths.append("未发现明显重复段落，结论和建议没有机械复述。")
    else:
        weaknesses.append(f"仍有 {len(duplicate_paragraphs)} 组重复段落，最典型重复为：{duplicate_paragraphs[0][1][:80]}。")
        upgrades.append("对相同建议、相同影响描述按文本去重，重复项改为引用同类处理路径。")

    if not bad_anchors:
        strengths.append("导航锚点均能定位到对应章节。")
    else:
        weaknesses.append(f"存在失效导航锚点：{', '.join(bad_anchors)}。")
        upgrades.append("折叠章节应保留原英文 id，避免导航跳转失效。")

    if structured["checks"].get("portable_image_refs"):
        strengths.append("HTML 图片均使用运行目录内相对路径，打包整个报告文件夹后可在其他电脑正常查看。")
    else:
        weaknesses.append(f"HTML 中仍存在 {len(bad_image_refs)} 个绝对图片路径，换电脑后会导致图片无法加载。")
        upgrades.append("渲染阶段应把 HTML 实际引用图片复制到 `html-assets/`，并把 HTML `img src` 改成相对路径。")

    if structured["checks"].get("packaged_image_refs"):
        strengths.append("HTML 图片已统一收敛到 `html-assets/`，对外转发时不依赖模块临时截图目录。")
    else:
        weaknesses.append(f"HTML 中仍有 {len(unpackaged_image_refs)} 个图片未收敛到 `html-assets/`，转发时容易漏文件。")
        upgrades.append("渲染阶段统一复制报告图片到 `html-assets/`，HTML 只引用 `./html-assets/...`。")

    if structured["checks"].get("no_embedded_images"):
        strengths.append("HTML 已恢复为相对路径引用图片，不再把大图内嵌进单个 HTML。")
    else:
        weaknesses.append(f"HTML 中仍有 {len(embedded_refs)} 个 data URI 内嵌图片，文件体积和可维护性会变差。")
        upgrades.append("移除图片内嵌逻辑，改为把 HTML 用图复制到 `html-assets/` 并使用相对路径。")

    if "browser-inspection" in modules:
        strengths.append("报告包含管理员浏览器实测模块，可支撑登录链路、截图和受保护页面证据链。")
    else:
        weaknesses.append("本轮缺少浏览器实测模块，报告只能说明 HTTP 或静态内容层面的健康情况。")
        upgrades.append("为深度巡检模式增加浏览器实测失败的显式提示与降级说明。")

    if structured["checks"].get("no_question_mark_garble"):
        strengths.append("报告未发现连续问号类乱码占位，旧编码异常已被规范文案替换。")
    else:
        weaknesses.append("报告或结构化 JSON 中仍存在连续问号类乱码，占位文本会破坏管理报告可信度。")
        upgrades.append("在合并和渲染阶段清理乱码字段，并优先补回可读的检测员解释。")

    if structured["checks"].get("screenshot_gallery_present"):
        strengths.append(f"截图证据画廊已生成，可从 {screenshot_count} 张浏览器截图中优先查看关键证据。")
    else:
        weaknesses.append("浏览器模块存在截图文件，但报告未生成“哪些证据值得优先看”的截图画廊。")
        upgrades.append("从 `visited_pages[].screenshot` 汇总截图，并挑选首页、登录、业务入口等关键截图展示。")

    if findings:
        strengths.append(f"报告聚合 {len(findings)} 个优先发现，并在正文中按根因与证据强度分层。")
    else:
        strengths.append("本轮未发现优先问题，报告适合作为健康基线留档。")

    has_health_baseline = "健康数据基线" in markup and "正常页面" in markup and "健康模块" in markup
    has_unhealthy_focus = "不健康与需关注数据" in markup and "不健康重点" in markup
    has_compact_health = "健康部分只保留基线证据" in markup or "健康项只保留数据" in markup
    if has_health_baseline and has_unhealthy_focus and has_compact_health:
        strengths.append("报告已按整体健康画像组织：健康数据完整展示，分析重点集中在不健康、需复核和自动化边界项。")
    else:
        weaknesses.append("报告尚未清晰区分健康数据基线与不健康重点分析，读者可能仍需在多处内容中自行拼接结论。")
        upgrades.append("在健康总览中同时展示健康/不健康数据，并将健康系统、健康模块收敛为基线摘要。")

    has_attention_index = "不健康索引" in markup and "哪些内容进入重点分析" in markup
    has_finding_meta = 'class="finding-meta-strip"' in markup
    has_attention_nav = 'href="#attention-index"' in markup
    if has_attention_index and has_finding_meta and has_attention_nav:
        strengths.append("报告已增加不健康索引、优先事项元信息和导航入口，健康基线与重点分析的阅读路径更清楚。")
    else:
        weaknesses.append("不健康重点分析的索引或优先事项元信息不足，读者可能难以快速定位责任域、证据缺口和下一步动作。")
        upgrades.append("为优先事项增加分类、责任域、影响范围和下一证据，并在导航中加入不健康索引。")

    advanced_markers = {
        "交付摘要": "可直接放进工单或周报的一段话",
        "风险域分布": "不健康项主要集中在哪里",
        "复测时间线": 'class="retest-timeline"',
        "证据包清单": 'class="evidence-pack"',
    }
    missing_advanced = [label for label, marker in advanced_markers.items() if marker not in markup]
    nav_links = markup.count('<a href="#')
    if not missing_advanced and nav_links == 8:
        strengths.append("报告已具备交付摘要、风险域分布、复测时间线和证据包清单，导航保持 8 项紧凑入口。")
    else:
        if missing_advanced:
            weaknesses.append("报告缺少高级交付组件：" + "、".join(missing_advanced) + "。")
            upgrades.append("补齐交付摘要、风险域分布、复测时间线和证据包清单。")
        if nav_links != 8:
            weaknesses.append(f"导航入口数量为 {nav_links}，不符合当前紧凑导航预期的 8 项。")
            upgrades.append("保持桌面端 8 项导航入口，避免导航折行或拥挤。")

    if structured["checks"].get("copy_summary_control"):
        strengths.append("交付摘要已提供复制按钮，便于直接转入工单、周报或复测沟通。")
    else:
        weaknesses.append("交付摘要缺少复制控件，报告作为交接工具时仍需要手动选中文字。")
        upgrades.append("为交付摘要增加复制按钮，并在浏览器脚本中处理复制成功/失败状态。")

    if structured["checks"].get("active_nav_scrollspy"):
        strengths.append("阅读导航已支持当前章节高亮，滚动到对应模块时导航会显示当前位置。")
    else:
        weaknesses.append("阅读导航缺少当前章节高亮，用户滚动阅读时不易判断自己所在模块。")
        upgrades.append("为导航入口增加滚动观察逻辑，使用 `aria-current` 和高亮样式标记当前模块。")

    if not weaknesses:
        weaknesses.append("未发现需要立即修正的报告质量风险。")
    if not upgrades:
        upgrades.append("本轮质量门禁已通过，后续可继续依据真实巡检反馈做定向优化。")

    lines = [
        f"# 第 {iteration:02d} 轮迭代升级报告",
        "",
        f"- 巡检目录：`{run_dir}`",
        f"- HTML 报告：`{html_path}`",
        f"- 当前状态：{status}",
        f"- 当前评分：{score}/100",
        f"- 覆盖模块：{', '.join(modules) if modules else '无'}",
        f"- 折叠章节：{folds}",
        f"- 重复段落组：{len(duplicate_paragraphs)}",
        f"- 失效锚点：{len(bad_anchors)}",
        f"- 质量门禁：{structured['status']}",
        "",
        "## 检测员审读结论",
        "",
        "本轮重点从“内容完整”转向“默认可读”：核心结论保持展开，长证据、表格和技术附录默认折叠。报告仍保留完整证据，但读者第一次打开时先看到管理判断和健康概览，再按需展开细节。",
        "",
        "## 做得好的地方",
        "",
        *(f"- {item}" for item in strengths),
        "",
        "## 不足与风险",
        "",
        *(f"- {item}" for item in weaknesses),
        "",
        "## 本轮升级动作",
        "",
        *(f"- {item}" for item in upgrades),
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit generated website health report quality.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--iteration", type=int, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    run_dir = Path(args.run_dir)
    json_out = out.with_suffix(".json")

    markdown = audit(run_dir, args.iteration)
    structured = audit_structured(run_dir, args.iteration, expected_quality_outputs=[out, json_out])
    out.write_text(markdown, encoding="utf-8-sig")
    json_out.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")
    refresh_delivery_manifest(run_dir, structured)
    print(out)
    if structured.get("status") == "fail":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
