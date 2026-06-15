from __future__ import annotations

import argparse
import collections
import html
import importlib
import importlib.util
import json
import os
import re
import hashlib
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from health_common import ensure_dir, read_json, write_json
from env_utils import load_project_env
from scoring_model import (
    classify_finding,
    clustered_findings,
    evidence_strength_counts,
    finding_cluster_key,
    root_cause_penalty,
    score_breakdown,
)


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
ASSETS = ROOT / "assets"

STATUS_LABELS = {
    "healthy": "正常",
    "warning": "告警",
    "critical": "严重",
    "unknown": "未知",
}

STATUS_TONES = {
    "healthy": "运行状态稳定，建议保持例行巡检节奏。",
    "warning": "存在需要跟进的告警项，建议安排负责人复核并闭环。",
    "critical": "存在严重风险，建议立即进入应急处置或专项修复。",
    "unknown": "巡检信息不足，建议先补齐检查范围与凭证配置。",
}

MODULE_LABELS = {
    "content-review": "网站内容完整性审查",
    "function-availability": "管理员功能可用性检查",
    "host-service-health": "主机与微服务健康检查",
    "site-discovery": "受控页面发现",
    "browser-inspection": "管理员浏览器实测",
    "browser-inspection-report.json": "管理员浏览器实测",
    "content-report.json": "网站内容完整性审查",
    "function-report.json": "管理员功能可用性检查",
    "host-report.json": "主机与微服务健康检查",
}

METRIC_LABELS = {
    "checked_pages": "检查页面数",
    "failed_pages": "失败页面数",
    "avg_latency_ms": "平均响应时间（毫秒）",
    "max_latency_ms": "最大响应时间（毫秒）",
    "avg_open_time_ms": "平均打开时间（毫秒）",
    "max_open_time_ms": "最慢打开时间（毫秒）",
    "slow_pages": "慢页面数",
    "avg_ttfb_ms": "平均 TTFB（毫秒）",
    "max_ttfb_ms": "最大 TTFB（毫秒）",
    "checked_flows": "检查流程数",
    "checked_services": "检查服务数",
    "flows": "流程数",
}

TECHNICAL_COLLECTIONS = {
    "console_messages": "浏览器控制台错误",
    "request_failures": "资源请求失败",
    "abnormal_responses": "异常 HTTP 响应",
    "visited_pages": "浏览器访问页面",
    "screenshots": "证据截图",
}

MAX_BROWSER_TABLE_ROWS = 6
MAX_PRIORITY_FINDINGS = 6
MAX_EVIDENCE_FILES = 6
MAX_SCREENSHOT_GALLERY = 4
MAX_TECH_APPENDIX_ROWS = 8
HTML_ASSET_DIR = "html-assets"
SCREENSHOT_ASSET_DIR = "screenshots"
DELIVERY_DIR = "delivery"
LEGACY_ASSET_DIR = "report-assets"
PORTABLE_ASSET_DIR = HTML_ASSET_DIR
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".svg"}
GUIDE_STATUS_FILE = "ai-report-guide-status.json"


def esc(value) -> str:
    return html.escape("" if value is None else str(value))


def has_garbled_placeholder(value) -> bool:
    text = str(value or "")
    return "\ufffd" in text or "???" in text or "？？？" in text or bool(re.search(r"[?？]{4,}", text))


VAGUE_IMPACT_TEXTS = {
    "",
    "可能影响部分页面体验或需要后续排查。",
    "可能影响部分页面体验或需要后续排查",
    "Review needed.",
    "Review needed",
}

VAGUE_RECOMMENDATION_TEXTS = {
    "",
    "请检查。",
    "请检查",
    "Review and fix.",
    "Review and fix",
    "建议尽快排查。",
    "建议尽快排查",
}


def fs_path(path: str | Path) -> str:
    target = Path(path).expanduser().resolve()
    text = str(target)
    if sys.platform != "win32" or text.startswith("\\\\?\\"):
        return text
    if text.startswith("\\\\"):
        return "\\\\?\\UNC\\" + text.lstrip("\\")
    return "\\\\?\\" + text


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fs_path(source), fs_path(target))


def remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(fs_path(path))


def copy_tree(source: Path, target: Path) -> None:
    remove_tree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(fs_path(source), fs_path(target))


def compact_delivery_asset_name(source: Path, prefix: str, max_name_length: int = 96) -> str:
    name = source.name
    if len(name) <= max_name_length:
        return name
    suffix = source.suffix or ".png"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    stem_budget = max(12, max_name_length - len(prefix) - len(digest) - len(suffix) - 2)
    stem = safe_asset_stem(source.stem, "asset")[:stem_budget].strip("-") or "asset"
    return f"{safe_asset_stem(prefix, 'asset')}-{stem}-{digest}{suffix}"


def normalize_spa_text_check_finding(finding: dict) -> None:
    evidence = str(finding.get("technical_evidence") or finding.get("evidence") or "")
    title = str(finding.get("title") or "")
    blob = f"{title} {evidence} {finding.get('id', '')}"
    if "body_length" not in blob and "页面内容过短" not in title and "content-" not in str(finding.get("id", "")):
        return
    if has_garbled_placeholder(title) or "页面内容过短" in title or not title:
        finding["title"] = "HTTP 文本检查疑似单页应用误报"
    if has_garbled_placeholder(finding.get("business_impact")) or not finding.get("business_impact"):
        finding["business_impact"] = (
            "普通 HTTP 文本检查未执行前端 JavaScript，不能单独证明页面内容异常；"
            "应以浏览器渲染截图、DOM 文本和关键路径复测作为最终判断依据。"
        )
    if has_garbled_placeholder(finding.get("recommendation")) or not finding.get("recommendation"):
        finding["recommendation"] = (
            "对照浏览器截图和渲染后文本复核；若截图显示首页或入口内容正常，"
            "本项应降级为 SPA 内容检查边界，不进入主要故障分析。"
        )
    if has_garbled_placeholder(evidence):
        match = re.search(r"body_length=\d+,\s*min_length=\d+", evidence)
        prefix = match.group(0) if match else "body_length/min_length 未通过"
        finding["technical_evidence"] = (
            f"{prefix}；普通 HTTP 文本检查未执行 JavaScript，结合浏览器截图按低可信 SPA 提示处理。"
        )
    finding.setdefault("confidence", "automation-boundary")


def normalize_garbled_finding(finding: dict) -> None:
    normalize_spa_text_check_finding(finding)
    replacements = {
        "title": "原始发现标题存在编码异常",
        "business_impact": "原始影响描述存在编码异常，已隐藏乱码；请结合结构化证据和技术附录复核。",
        "technical_evidence": "原始证据文本存在编码异常，已隐藏乱码；请查看对应截图、URL、状态码或原始 JSON。",
        "recommendation": "原始建议文本存在编码异常，建议根据证据类型重新复核并补充人工判断。",
    }
    for key, fallback in replacements.items():
        if has_garbled_placeholder(finding.get(key)):
            finding[key] = fallback


def normalize_placeholder_finding_language(finding: dict) -> None:
    if str(finding.get("business_impact") or "").strip() in VAGUE_IMPACT_TEXTS:
        finding["business_impact"] = business_impact_for_finding(finding)
    if str(finding.get("recommendation") or "").strip() in VAGUE_RECOMMENDATION_TEXTS:
        finding["recommendation"] = recommendation_line_for_finding(finding, str(finding.get("recommendation") or ""))


def garbled_fallback(key: str, value: str, parent: dict | None = None) -> str:
    parent = parent or {}
    if key == "summary":
        report_type = parent.get("report_type") or parent.get("file")
        if report_type == "content-review" or report_type == "content-report.json":
            return "网站内容完整性审查完成，发现疑似 SPA 文本检查边界项；应以浏览器渲染截图作为主要判断依据。"
        if report_type == "browser-inspection" or report_type == "browser-inspection-report.json":
            return "管理员浏览器实测完成，已采集页面访问、截图和浏览器侧异常信号。"
        return "模块摘要存在编码异常，已替换为可读占位说明。"
    if key == "label":
        return "未命名证据"
    if key == "title":
        return "原始标题存在编码异常"
    if key == "business_impact":
        return "原始影响描述存在编码异常，已隐藏乱码；请结合截图、状态码和结构化证据复核。"
    if key == "recommendation":
        return "原始建议存在编码异常，建议根据证据类型重新复核并补充人工判断。"
    if key in {"technical_evidence", "evidence"}:
        match = re.search(r"body_length=\d+,\s*min_length=\d+", value)
        if match:
            return f"{match.group(0)}；普通 HTTP 文本检查未执行 JavaScript，需结合浏览器截图复核。"
        return "原始证据文本存在编码异常，已隐藏乱码；请查看截图、URL、状态码或原始 JSON。"
    if key in {"note", "message", "text", "text_excerpt"}:
        return "原始文本存在编码异常，已隐藏乱码。"
    return "原始文本存在编码异常，已隐藏乱码。"


def scrub_garbled_values(value, key: str = "", parent: dict | None = None):
    if isinstance(value, dict):
        for child_key, child_value in list(value.items()):
            value[child_key] = scrub_garbled_values(child_value, str(child_key), value)
        return value
    if isinstance(value, list):
        return [scrub_garbled_values(item, key, parent) for item in value]
    if isinstance(value, str) and has_garbled_placeholder(value):
        return garbled_fallback(key, value, parent)
    return value


def normalize_report_for_render(report: dict) -> dict:
    for finding in report.get("priority_findings", []) or []:
        normalize_garbled_finding(finding)
        normalize_placeholder_finding_language(finding)
    for module in report.get("module_reports", []) or []:
        for finding in module.get("findings", []) or []:
            normalize_garbled_finding(finding)
            normalize_placeholder_finding_language(finding)
    return scrub_garbled_values(report)


def browser_screenshot_files(module: dict) -> list[str]:
    files: list[str] = []
    for item in module.get("screenshots") or []:
        if isinstance(item, str) and item.strip():
            files.append(item.strip())
        elif isinstance(item, dict):
            path = item.get("path") or item.get("file") or item.get("screenshot")
            if path:
                files.append(str(path).strip())
    for page in module.get("visited_pages") or []:
        screenshot = page.get("screenshot")
        if screenshot:
            files.append(str(screenshot).strip())
    seen: set[str] = set()
    unique: list[str] = []
    for filename in files:
        if filename and filename not in seen:
            seen.add(filename)
            unique.append(filename)
    return unique


def is_absolute_asset_ref(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    parsed = urlparse(text)
    return parsed.scheme == "file" or bool(re.match(r"^[A-Za-z]:[\\/]", text)) or text.startswith("\\\\")


def asset_ref_to_path(value: str) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme == "file":
        return Path(unquote(parsed.path).lstrip("/"))
    if re.match(r"^[A-Za-z]:[\\/]", text) or text.startswith("\\\\"):
        return Path(text)
    return None


def normalized_relative_ref(value: str) -> str:
    text = str(value or "").strip()
    parsed = urlparse(text)
    raw = parsed.path if parsed.scheme else text
    return unquote(raw).replace("\\", "/").lstrip("./")


def resolve_asset_source(value: str, out_dir: Path) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = urlparse(text)
    if parsed.scheme in {"http", "https", "data", "blob"}:
        return None
    if is_absolute_asset_ref(text):
        return asset_ref_to_path(text)

    normalized = normalized_relative_ref(text)
    candidates = [
        out_dir / normalized,
        out_dir / Path(normalized).name,
        out_dir / HTML_ASSET_DIR / Path(normalized).name,
        out_dir / SCREENSHOT_ASSET_DIR / Path(normalized).name,
        out_dir / LEGACY_ASSET_DIR / Path(normalized).name,
        out_dir / DELIVERY_DIR / HTML_ASSET_DIR / Path(normalized).name,
        out_dir / DELIVERY_DIR / SCREENSHOT_ASSET_DIR / Path(normalized).name,
        out_dir / f"{SCREENSHOT_ASSET_DIR}-previous" / Path(normalized).name,
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def candidate_asset_sources(value: str, out_dir: Path) -> list[Path]:
    text = str(value or "").strip()
    if not text:
        return []
    parsed = urlparse(text)
    if parsed.scheme in {"http", "https", "data", "blob"}:
        return []
    if is_absolute_asset_ref(text):
        source = asset_ref_to_path(text)
        return [source] if source else []
    normalized = normalized_relative_ref(text)
    name = Path(normalized).name
    return [
        out_dir / normalized,
        out_dir / name,
        out_dir / HTML_ASSET_DIR / name,
        out_dir / SCREENSHOT_ASSET_DIR / name,
        out_dir / LEGACY_ASSET_DIR / name,
        out_dir / DELIVERY_DIR / HTML_ASSET_DIR / name,
        out_dir / DELIVERY_DIR / SCREENSHOT_ASSET_DIR / name,
        out_dir / f"{SCREENSHOT_ASSET_DIR}-previous" / name,
    ]


def image_name_core(name: str) -> str:
    stem = Path(name).stem.lower()
    stem = re.sub(r"^(shot|screenshot|file|image|asset|evidence-shot|evidence)[-_]+", "", stem)
    stem = re.sub(r"[-_][a-f0-9]{8,16}$", "", stem)
    return re.sub(r"[^a-z0-9]+", "-", stem).strip("-")


def image_hash_token(name: str) -> str:
    match = re.search(r"[-_]([a-f0-9]{8,16})(?:\.[a-z0-9]+)?$", name.lower())
    return match.group(1) if match else ""


def image_name_matches(query: str, candidate: str) -> bool:
    query_lower = query.lower()
    candidate_lower = candidate.lower()
    if candidate_lower == query_lower or candidate_lower.endswith(query_lower) or query_lower.endswith(candidate_lower):
        return True
    query_hash = image_hash_token(query_lower)
    candidate_hash = image_hash_token(candidate_lower)
    if query_hash and candidate_hash and query_hash == candidate_hash:
        return True
    query_core = image_name_core(query_lower)
    candidate_core = image_name_core(candidate_lower)
    if not query_core or not candidate_core:
        return False
    return query_core == candidate_core or candidate_core.endswith(query_core) or query_core.endswith(candidate_core)


def find_image_by_suffix(out_dir: Path, name: str) -> Path | None:
    search_dirs = [
        out_dir / HTML_ASSET_DIR,
        out_dir / SCREENSHOT_ASSET_DIR,
        out_dir / f"{SCREENSHOT_ASSET_DIR}-previous",
        out_dir / DELIVERY_DIR / SCREENSHOT_ASSET_DIR,
        out_dir / DELIVERY_DIR / HTML_ASSET_DIR,
        out_dir / LEGACY_ASSET_DIR,
        out_dir / "custom-interactive",
    ]
    for folder in search_dirs:
        if not folder.exists():
            continue
        matches = sorted(
            item
            for item in folder.glob("*")
            if item.is_file()
            and item.suffix.lower() in IMAGE_EXTENSIONS
            and image_name_matches(name, item.name)
        )
        if matches:
            return matches[0]
    return None


def safe_asset_stem(value: str, fallback: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "")).strip("-") or fallback


def copy_image_to_dir(source: Path, target_dir: Path, prefix: str, preferred_name: str | None = None) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    suffix = source.suffix if source.suffix else ".png"
    if preferred_name:
        preferred = safe_asset_stem(Path(preferred_name).stem, prefix)
        target = target_dir / f"{preferred}{suffix}"
    else:
        digest = hashlib.sha256(source.read_bytes()).hexdigest()[:10]
        target = target_dir / f"{safe_asset_stem(prefix, 'asset')}-{safe_asset_stem(source.stem, 'image')}-{digest}{suffix}"
    if source.resolve() != target.resolve():
        copy_file(source, target)
    return target


def portable_asset_ref(
    value: str,
    out_dir: Path,
    prefix: str = "asset",
    preferred_name: str | None = None,
    asset_dir_name: str = HTML_ASSET_DIR,
) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme in {"http", "https", "data", "blob"}:
        return text
    normalized = normalized_relative_ref(text)
    if not preferred_name and normalized.startswith(f"{asset_dir_name}/"):
        return f"./{normalized}"
    source = resolve_asset_source(text, out_dir)
    if not source or not source.exists() or not source.is_file():
        return normalized or Path(text).name.replace("\\", "/")
    if source.suffix.lower() not in IMAGE_EXTENSIONS:
        return text.replace("\\", "/")
    target = copy_image_to_dir(source, out_dir / asset_dir_name, prefix, preferred_name)
    return f"./{asset_dir_name}/{target.name}"


def best_effort_image_ref(
    value: str,
    out_dir: Path,
    prefix: str,
    preferred_name: str,
    asset_dir_name: str = HTML_ASSET_DIR,
) -> str:
    for source in candidate_asset_sources(value, out_dir):
        if source and source.exists() and source.is_file() and source.suffix.lower() in IMAGE_EXTENSIONS:
            target = copy_image_to_dir(source, out_dir / asset_dir_name, prefix, preferred_name)
            return f"./{asset_dir_name}/{target.name}"
    fallback = find_image_by_suffix(out_dir, Path(normalized_relative_ref(value)).name)
    if fallback:
        target = copy_image_to_dir(fallback, out_dir / asset_dir_name, prefix, preferred_name)
        return f"./{asset_dir_name}/{target.name}"
    return portable_asset_ref(value, out_dir, prefix, preferred_name, asset_dir_name)


def ensure_report_image_ref(value: str, out_dir: Path, prefix: str = "image", preferred_name: str | None = None) -> str:
    return portable_asset_ref(value, out_dir, prefix, preferred_name, HTML_ASSET_DIR)


def ensure_screenshot_ref(value: str, out_dir: Path, prefix: str = "screenshot", preferred_name: str | None = None) -> str:
    return portable_asset_ref(value, out_dir, prefix, preferred_name, SCREENSHOT_ASSET_DIR)


def normalize_image_refs_for_portable_html(value, out_dir: Path, key: str = ""):
    if isinstance(value, dict):
        for child_key, child_value in list(value.items()):
            value[child_key] = normalize_image_refs_for_portable_html(child_value, out_dir, str(child_key))
        return value
    if isinstance(value, list):
        return [normalize_image_refs_for_portable_html(item, out_dir, key) for item in value]
    if isinstance(value, str) and Path(value).suffix.lower() in IMAGE_EXTENSIONS:
        if key in {"screenshot", "screenshots", "path", "file"}:
            return ensure_screenshot_ref(value, out_dir, key or "screenshot")
        if key in {"image", "image_path"}:
            return value.replace("\\", "/")
    return value


def report_image_candidates(report: dict) -> list[str]:
    candidates: list[str] = []
    for module in report.get("module_reports", []) or []:
        candidates.extend(browser_screenshot_files(module))
        for item in module.get("evidence_files") or []:
            if Path(str(item)).suffix.lower() in IMAGE_EXTENSIONS:
                candidates.append(str(item))
    for finding in report.get("priority_findings", []) or []:
        for item in finding.get("evidence_files") or []:
            if Path(str(item)).suffix.lower() in IMAGE_EXTENSIONS:
                candidates.append(str(item))
    seen: set[str] = set()
    unique: list[str] = []
    for item in candidates:
        if item and item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def likely_screenshot_file(path: Path) -> bool:
    if path.suffix.lower() not in IMAGE_EXTENSIONS:
        return False
    name = path.name.lower()
    if name in {"ai-report-guide.png", "executive-summary.png"}:
        return False
    return any(token in name for token in ["screenshot", "entry", "login", "route", "page-", "control", "custom", "certificate", "evidence"])


def collect_screenshot_assets(report: dict, out_dir: Path) -> list[Path]:
    target_dir = out_dir / SCREENSHOT_ASSET_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    sources: list[Path] = []
    for ref in report_image_candidates(report):
        source = resolve_asset_source(ref, out_dir)
        if source and source.exists() and source.is_file() and source.suffix.lower() in IMAGE_EXTENSIONS:
            sources.append(source)
    for pattern_root in [out_dir, out_dir / "custom-interactive", out_dir / LEGACY_ASSET_DIR]:
        if pattern_root.exists():
            for source in pattern_root.glob("*.png"):
                if likely_screenshot_file(source):
                    sources.append(source)

    copied: list[Path] = []
    seen_sources: set[str] = set()
    for source in sources:
        try:
            source_key = str(source.resolve()).lower()
        except OSError:
            source_key = str(source).lower()
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)
        try:
            already_in_target = source.resolve().parent == target_dir.resolve()
        except OSError:
            already_in_target = False
        copied.append(source if already_in_target else copy_image_to_dir(source, target_dir, "shot"))
    return sorted(target_dir.glob("*"))


def html_image_refs(markup: str) -> list[str]:
    return re.findall(r'<img[^>]+src="([^"]+)"', markup, flags=re.I)


def sync_delivery_package(out_dir: Path) -> Path:
    delivery_dir = out_dir / DELIVERY_DIR
    staging = out_dir / f"{DELIVERY_DIR}-next"
    if staging.exists():
        remove_tree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    (staging / HTML_ASSET_DIR).mkdir(parents=True, exist_ok=True)
    (staging / SCREENSHOT_ASSET_DIR).mkdir(parents=True, exist_ok=True)

    for filename in [
        "final-report.html",
        "final-report.pdf",
        "final-report.md",
        "final-report.json",
        "quality-audit.md",
        "quality-audit.json",
        "score-audit.md",
        "score-audit.json",
        "delivery-manifest.md",
        "delivery-manifest.json",
        GUIDE_STATUS_FILE,
    ]:
        source = out_dir / filename
        if source.exists() and source.is_file():
            copy_file(source, staging / filename)

    markup = (out_dir / "final-report.html").read_text(encoding="utf-8") if (out_dir / "final-report.html").exists() else ""
    for ref in html_image_refs(markup):
        parsed = urlparse(ref)
        if parsed.scheme in {"http", "https", "data", "blob"}:
            continue
        source = resolve_asset_source(ref, out_dir)
        if not source or not source.exists() or not source.is_file():
            continue
        target = staging / HTML_ASSET_DIR / Path(normalized_relative_ref(ref)).name
        if not target.name:
            target = staging / HTML_ASSET_DIR / source.name
        copy_file(source, target)

    screenshot_dir = out_dir / SCREENSHOT_ASSET_DIR
    if screenshot_dir.exists():
        for source in sorted(screenshot_dir.iterdir()):
            if source.is_file() and source.suffix.lower() in IMAGE_EXTENSIONS:
                copy_file(source, staging / SCREENSHOT_ASSET_DIR / compact_delivery_asset_name(source, "shot"))

    if delivery_dir.exists():
        remove_tree(delivery_dir)
    staging.replace(delivery_dir)
    return delivery_dir


def write_guide_status(out_dir: Path, status: str, reason: str, message: str = "", error_file: str = "") -> dict:
    requires_user_api_key = status in {"needs_user_choice", "missing_api_key"}
    payload = {
        "status": status,
        "reason": reason,
        "message": message,
        "error_file": error_file,
        "requires_user_api_key": requires_user_api_key,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "choices": [
            "用户提供自己的图片接口 API Key 后，使用 --guide-mode ai-image 生成 AI 导览图。",
            "用户明确选择不提供 API Key 时，使用 --guide-mode html-guide 生成 HTML 图文导览。",
            "用户明确选择复用已有导览图时，使用 --guide-mode reuse-existing。",
        ],
    }
    (out_dir / GUIDE_STATUS_FILE).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def usable_openai_api_key(value: str | None = None) -> bool:
    key = str(os.getenv("OPENAI_API_KEY") if value is None else value or "").strip()
    if not key:
        return False
    lowered = key.lower()
    placeholders = {
        "sk-" + "your-key-here",
        "your-api-key",
        "your-openai-api-key",
        "replace-me",
        "changeme",
        "none",
        "null",
    }
    if lowered in placeholders or "your-key" in lowered or "placeholder" in lowered:
        return False
    return bool(re.match(r"^sk-[A-Za-z0-9_-]{12,}$", key))


def has_usable_openai_api_key() -> bool:
    return usable_openai_api_key()


def has_openai_python_package() -> bool:
    return importlib.util.find_spec("openai") is not None


def install_openai_python_package(out_dir: Path) -> bool:
    command = [sys.executable, "-m", "pip", "install", "openai"]
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.stdout.strip():
        print(scrub_runtime_text(result.stdout.strip()))
    if result.returncode != 0:
        record_optional_error(out_dir, "ai-report-guide-dependency-error.txt", command, result)
        message = result.stderr.strip().splitlines()[-1:] or result.stdout.strip().splitlines()[-1:]
        if message:
            print(f"Failed to install AI guide dependency: {scrub_runtime_text(message[0])}", file=sys.stderr)
        return False
    importlib.invalidate_caches()
    if has_openai_python_package():
        return True
    verify_command = [sys.executable, "-c", "import openai"]
    verify_result = subprocess.run(verify_command, check=False, capture_output=True, text=True)
    if verify_result.returncode == 0:
        return True
    record_optional_error(out_dir, "ai-report-guide-dependency-error.txt", verify_command, verify_result)
    return False


def ensure_openai_python_package(out_dir: Path) -> bool:
    if has_openai_python_package():
        return True
    return install_openai_python_package(out_dir)


def valid_ai_guide_image(guide_path: Path, out_dir: Path) -> tuple[bool, str]:
    if not guide_path.exists() or not guide_path.is_file():
        return False, "missing"
    if guide_path.stat().st_size <= 0:
        return False, "empty"
    summary_candidates = [
        out_dir / "executive-summary.png",
        out_dir / HTML_ASSET_DIR / "executive-summary.png",
        out_dir / HTML_ASSET_DIR / "executive-summary-image.png",
    ]
    guide_bytes = guide_path.read_bytes()
    for candidate in summary_candidates:
        if candidate.exists() and candidate.is_file() and candidate.read_bytes() == guide_bytes:
            return False, "matches_executive_summary"
    return True, "ok"


def read_guide_status(out_dir: Path) -> dict:
    path = out_dir / GUIDE_STATUS_FILE
    if not path.exists():
        return {}
    try:
        return read_json(path)
    except Exception:
        return {}


def cleanup_asset_dirs(out_dir: Path) -> None:
    remove_tree(out_dir / HTML_ASSET_DIR)
    screenshot_dir = out_dir / SCREENSHOT_ASSET_DIR
    delivery_screenshots = out_dir / DELIVERY_DIR / SCREENSHOT_ASSET_DIR
    if delivery_screenshots.exists():
        backup = out_dir / f"{SCREENSHOT_ASSET_DIR}-previous"
        remove_tree(backup)
        copy_tree(delivery_screenshots, backup)
    remove_tree(screenshot_dir)


def format_report_time(value) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    normalized = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        return dt.strftime("%Y年%m月%d日 %H:%M")
    except ValueError:
        if "T" in text:
            date_part, time_part = text.split("T", 1)
            return f"{date_part} {time_part[:5]}"
        return text[:16]


def status_badge(status: str) -> str:
    label = STATUS_LABELS.get(status, status)
    return f'<span class="badge {esc(status)}">{esc(label)}</span>'


def is_multi_site_overall(report: dict) -> bool:
    return report.get("report_kind") == "multi-site-overall"


def int_value(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def compact_site_name(value, max_chars: int = 14) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    if len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


def multi_site_subject(report: dict, *, max_names: int = 3) -> str:
    sites = report.get("site_results") or report.get("systems") or []
    names: list[str] = []
    for site in sites:
        name = compact_site_name(
            site.get("name") or site.get("site_name") or site.get("system_name") or site.get("slug") or site.get("id")
        )
        if name and name not in names:
            names.append(name)
        if len(names) >= max_names:
            break
    metrics = report.get("batch_metrics") or {}
    summary = report.get("summary") or {}
    total = int_value(metrics.get("site_count"), int_value(summary.get("total_systems"), len(sites)))
    if names and total > len(names):
        return f"{'、'.join(names)}等{total}个站点"
    if names:
        return "、".join(names)
    if total:
        return f"{total}个站点"
    return "本批次站点"


def multi_site_report_title(report: dict) -> str:
    return f"{multi_site_subject(report)}健康巡检总体报告"


def localize_summary(summary: str) -> str:
    text = str(summary or "")
    for raw, label in MODULE_LABELS.items():
        text = text.replace(raw, label)
    return text


ATTENTION_RANK = {
    "已确认故障": 1,
    "高可信风险": 2,
    "需人工复核": 3,
    "自动化能力边界": 4,
    "自动化识别不足": 5,
}


def attention_rank(finding: dict) -> tuple[int, int, str]:
    label, _ = classify_finding(finding)
    priority = str(finding.get("priority") or "P9").upper()
    priority_rank = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}.get(priority, 9)
    return (ATTENTION_RANK.get(label, 9), priority_rank, str(finding.get("title") or ""))


def attention_clusters(findings: list[dict]) -> list[dict]:
    return sorted(clustered_findings(findings), key=attention_rank)


def attention_summary(report: dict) -> list[dict]:
    rows = []
    for finding in attention_clusters(report.get("priority_findings", [])):
        label, note = classify_finding(finding)
        rows.append(
            {
                "classification": label,
                "title": finding.get("title", "未命名问题"),
                "priority": finding.get("priority", "-"),
                "severity": finding.get("severity", "-"),
                "count": finding.get("_cluster_count", 1),
                "owner": owner_role_for_finding(finding),
                "domain": impact_domain_for_finding(finding),
                "next_evidence": next_evidence_for_finding(finding),
                "note": note,
            }
        )
    return rows


def risk_domain_counts(report: dict) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for finding in attention_clusters(report.get("priority_findings", [])):
        domain = impact_domain_for_finding(finding)
        counts[domain] = counts.get(domain, 0) + int(finding.get("_cluster_count", 1) or 1)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def handoff_summary_text(report: dict) -> str:
    score = int(report.get("score") or 0)
    status = STATUS_LABELS.get(report.get("overall_status"), report.get("overall_status"))
    verdict = current_health_verdict(report)
    domains = "、".join(name for name, _ in risk_domain_counts(report)[:3]) or "暂无优先风险域"
    return f"本次巡检状态为{status}，评分 {score}/100。{verdict['production']}。重点复核范围：{domains}。健康数据已作为基线展示，后续处置应优先围绕不健康索引中的需复核项、自动化能力边界和接口异常闭环。"


def evidence_pack_items(report: dict) -> list[tuple[str, str, str]]:
    browser = browser_inspection_module(report) or {}
    screenshot_count = len(browser_screenshot_files(browser))
    return [
        ("最终 HTML", "final-report.html", "管理层和技术人员共同阅读的正式报告。"),
        ("结构化总报告", "final-report.json", "用于二次分析、重新渲染和自动化审计。"),
        ("Markdown 摘要", "final-report.md", "用于粘贴到工单、周报或复测记录。"),
        ("质量审计", "quality-audit.md", "用于确认模板、锚点、重复段落和导览图引用。"),
        ("截图证据", f"{screenshot_count} 张", "用于核对首页、登录入口、提交后页面和受保护入口。"),
    ]


def health_picture(report: dict) -> dict:
    summary = report.get("summary", {})
    findings = report.get("priority_findings", [])
    modules = report.get("module_reports", [])
    systems = report.get("systems", [])
    browser = browser_inspection_module(report) or {}
    visited = browser.get("visited_pages") or []
    screenshot_count = len(browser_screenshot_files(browser))
    normal_pages = [item for item in visited if page_judgement(item) == "正常可访问"]
    protected_pages = [item for item in visited if page_judgement(item) == "受保护跳转"]
    warning_modules = [item for item in modules if item.get("status") not in {"healthy"}]
    healthy_modules = [item for item in modules if item.get("status") == "healthy"]
    healthy_systems = [item for item in systems if item.get("status") == "healthy"]
    attention_systems = [item for item in systems if item.get("status") != "healthy"]
    strength_counts = evidence_strength_counts(findings)
    attention_count = sum(strength_counts.values())
    return {
        "total_systems": summary.get("total_systems", len(systems)),
        "healthy_systems": summary.get("healthy", len(healthy_systems)),
        "warning_systems": summary.get("warning", 0),
        "critical_systems": summary.get("critical", 0),
        "healthy_modules": len(healthy_modules),
        "warning_modules": len(warning_modules),
        "total_modules": len(modules),
        "normal_pages": len(normal_pages),
        "protected_pages": len(protected_pages),
        "visited_pages": len(visited),
        "screenshots": screenshot_count,
        "request_failures": len(browser.get("request_failures") or []),
        "abnormal_responses": len(browser.get("abnormal_responses") or []),
        "clusters": len(clustered_findings(findings)),
        "attention_count": attention_count,
        "strength_counts": strength_counts,
        "healthy_system_list": healthy_systems,
        "attention_system_list": attention_systems,
        "healthy_module_list": healthy_modules,
        "attention_module_list": warning_modules,
    }


def health_baseline_items(picture: dict) -> list[tuple[str, str]]:
    return [
        ("健康系统", f"{picture['healthy_systems']} / {picture['total_systems']}"),
        ("健康模块", f"{picture['healthy_modules']} / {picture['total_modules']}"),
        ("正常页面", f"{picture['normal_pages']} / {picture['visited_pages']}"),
        ("截图证据", str(picture["screenshots"])),
    ]


def attention_items(picture: dict) -> list[tuple[str, str]]:
    counts = picture["strength_counts"]
    return [
        ("已确认故障", str(counts.get("已确认故障", 0))),
        ("高可信风险", str(counts.get("高可信风险", 0))),
        ("需人工复核", str(counts.get("需人工复核", 0))),
        ("自动化能力边界", str(counts.get("自动化能力边界", 0))),
        ("自动化识别不足", str(counts.get("自动化识别不足", 0))),
        ("请求/HTTP 异常", f"{picture['request_failures']} / {picture['abnormal_responses']}"),
    ]


def module_has_findings(module: dict) -> bool:
    return bool(module.get("findings")) or module.get("status") not in {"healthy"}


def business_impact_for_finding(finding: dict) -> str:
    title = str(finding.get("title") or "")
    target = str(finding.get("target") or "")
    if "浏览器资源请求失败" in title and target:
        return f"{target} 请求在浏览器侧出现失败或中断，需结合服务器日志判断是导航取消、前端主动取消，还是接口真实失败。"
    if "受保护页面重定向至登录页" in title:
        if "automation_login_status=unknown" in str(finding.get("technical_evidence") or "") or str(finding.get("confidence")) == "automation-boundary":
            return "该跳转发生在自动化登录态未确认之后，更可能说明巡检代理未维持有效会话或未命中角色基准；人工登录正常时不应直接定性为业务入口不可用。"
        return "可能影响课程、教室、练习、实验、考试或资源等受保护业务入口的访问，需要确认这些入口在当前账号权限下是否应直接可达。"
    if "管理员登录状态未确认" in title or "自动化登录态信号未确认" in title:
        return "不证明网站登录故障，只说明巡检代理未能稳定识别登录态；人工登录正常时，应作为自动化巡检能力边界处理。"
    if "auth/refresh" in target:
        return "可能影响登录保持、页面刷新后的会话延续或权限刷新，也可能只是未登录边界下的预期响应。"
    if "浏览器资源请求失败" in title:
        return "浏览器侧出现资源请求失败或中断，需结合服务器日志判断是否为真实失败。"
    if "页面内容过短" in title:
        return "更可能是单页应用在普通 HTTP 文本检查下未执行 JavaScript 导致的低可信提示，应以浏览器实测为主。"
    impact = str(finding.get("business_impact") or "").strip()
    if impact in VAGUE_IMPACT_TEXTS:
        owner = owner_role_for_finding(finding)
        domain = impact_domain_for_finding(finding)
        return f"影响范围尚未确认；建议由{owner}围绕{domain}补齐复测证据、服务端日志和业务预期后再定性。"
    return impact


def render_score_breakdown(report: dict) -> str:
    rows = score_breakdown(report)
    score = report.get("score", 0)
    if not rows:
        score_value = int(score or 0)
        empty_text = (
            "本次未形成可逐项扣分的问题簇，健康评分保持 100 分。"
            if score_value == 100
            else "本次未形成可逐项扣分的问题簇；当前分数来自覆盖缺口、未运行模块或上游汇总扣分，请查看交付清单和技术附录确认来源。"
        )
        return "\n".join(
            [
                '<section class="report-section score-section" id="score-breakdown">',
                '<div class="section-kicker">评分说明</div>',
                f"<h2>为什么是 {esc(score_value)} 分</h2>",
                f'<p class="empty">{esc(empty_text)}</p>',
                "</section>",
            ]
        )

    review_count = sum(1 for row in rows if row["classification"] in {"需人工复核", "自动化识别不足"})
    parts = [
        '<section class="report-section score-section" id="score-breakdown">',
        '<div class="section-kicker">评分说明</div>',
        f"<h2>为什么是 {esc(score)} 分</h2>",
        '<div class="score-band-note">',
        f'<strong>{esc(score_band_label(int(score or 0)))}</strong>',
        f'<span>{esc(score_semantics(int(score or 0), report))}</span>',
        "</div>",
        '<div class="score-explainer">',
        f'<div><span>基础分</span><strong>100</strong></div>',
        f'<div><span>当前分</span><strong>{esc(score)}</strong></div>',
        f'<div><span>扣分项</span><strong>{len(rows)}</strong></div>',
        f'<div><span>复核/识别不足</span><strong>{review_count}</strong></div>',
        "</div>",
        '<p class="fine">评分按根因归并扣分，而不是按每条重复日志或每个跳转页面机械扣分。已确认故障和高可信风险权重最高；自动化识别不足、会话边界、单页应用文本检查等低可信项会降低扣分权重，并保留“需复核”标识。</p>',
        '<div class="table-wrap">',
        "<table><thead><tr><th>事项</th><th>类型</th><th>扣分</th><th>说明</th><th>证据</th></tr></thead><tbody>",
    ]
    seen_notes: set[str] = set()
    for row in rows:
        note = str(row["note"] or "")
        note_text = note
        if "资源请求中断" in note or "请求中断" in note:
            note_text = "请求中断类说明见根因地图，本行保留扣分与证据差异。"
        elif note and note in seen_notes:
            note_text = "同类说明见上方，本行只展示扣分与证据差异。"
        elif note:
            seen_notes.add(note)
        parts.append(
            "<tr>"
            f'<td><span class="priority">{esc(row["priority"])}</span> {esc(row["title"])}<br><span class="fine">同类出现 {esc(row["count"])} 次</span></td>'
            f'<td><span class="review-tag">{esc(row["classification"])}</span><br><span class="fine">{esc(row["severity"])}</span></td>'
            f'<td><strong>-{esc(row["penalty"])}</strong><br><span class="fine">剩余 {esc(row["remaining"])}</span></td>'
            f'<td>{esc(note_text)}</td>'
            f'<td><code>{esc(row["evidence"])}</code></td>'
            "</tr>"
        )
    parts.extend(["</tbody></table>", "</div>", "</section>"])
    return "\n".join(parts)


def render_root_cause_map(report: dict) -> str:
    cards = root_cause_cards(report)
    if not cards:
        return ""
    seen_notes: set[str] = set()
    seen_evidence: set[str] = set()
    rendered_cards = []
    for card in cards[:6]:
        note = str(card["note"] or "")
        note_text = note
        if note and note not in seen_notes:
            seen_notes.add(note)
        elif note:
            note_text = ""
        evidence_text = str(card["evidence"] or "")
        evidence_html = ""
        if evidence_text and evidence_text not in seen_evidence:
            seen_evidence.add(evidence_text)
            evidence_html = f'<p class="fine"><b>下一份证据：</b>{esc(evidence_text)}</p>'
        rendered_cards.append(
            "\n".join(
                [
                    '<article class="root-cause-card">',
                    f'<span class="review-tag">{esc(card["classification"])}</span>',
                    f'<h3>{esc(card["title"])}</h3>',
                    f'<p>{esc(note_text)}</p>' if note_text else "",
                    '<div class="root-cause-meta">',
                    f'<div><span>影响域</span><strong>{esc(card["domain"])}</strong></div>',
                    f'<div><span>同类数</span><strong>{esc(card["count"])}</strong></div>',
                    f'<div><span>责任角色</span><strong>{esc(card["owner"])}</strong></div>',
                    "</div>",
                    evidence_html,
                    "</article>",
                ]
            )
        )
    return "\n".join(
        [
            '<section class="report-section root-cause-section" id="root-cause-map">',
            '<div class="section-kicker">风险地图</div>',
            "<h2>哪些根因最值得先闭环</h2>",
            '<p class="section-brief">本节按根因而不是按日志条数展示风险，帮助判断责任人、影响域和下一份证据。</p>',
            '<div class="root-cause-grid">',
            *rendered_cards,
            "</div>",
            "</section>",
        ]
    )


def render_auditor_summary(report: dict) -> str:
    findings = report.get("priority_findings", [])
    counts = evidence_strength_counts(findings)
    score = report.get("score", 0)
    if counts.get("已确认故障", 0) or counts.get("高可信风险", 0):
        judgement = "本次巡检已出现高可信风险或已确认故障，应优先组织技术负责人复核并进入修复闭环。"
    elif counts.get("自动化能力边界", 0) or counts.get("自动化识别不足", 0) or counts.get("需人工复核", 0):
        judgement = "当前报告更像自动化巡检能力边界、会话边界信号和需复核项的集合，尚未证明网站核心业务不可用。若人工登录正常，应优先优化巡检代理识别能力，而不是把登录未确认定性为网站故障。"
    else:
        judgement = "本次巡检未形成明确异常证据，可作为当前健康基线留档。"
    return "\n".join(
        [
            '<section class="report-section auditor-summary" id="auditor-summary">',
            '<div class="section-kicker">审计员摘要</div>',
            "<h2>这次告警到底有多严重</h2>",
            f'<p class="auditor-verdict">{esc(judgement)}</p>',
            render_evidence_ladder(report),
            '<div class="evidence-grid">',
            f'<div><span>已确认故障</span><strong>{esc(counts.get("已确认故障", 0))}</strong></div>',
            f'<div><span>高可信风险</span><strong>{esc(counts.get("高可信风险", 0))}</strong></div>',
            f'<div><span>自动化能力边界</span><strong>{esc(counts.get("自动化能力边界", 0))}</strong></div>',
            f'<div><span>自动化识别不足</span><strong>{esc(counts.get("自动化识别不足", 0))}</strong></div>',
            f'<div><span>需人工复核</span><strong>{esc(counts.get("需人工复核", 0))}</strong></div>',
            "</div>",
            f'<p class="fine">当前健康评分为 {esc(score)} / 100。该分数反映自动化巡检视角下的风险压力，不等同于已经确认的生产故障数量。</p>',
            "</section>",
        ]
    )


def browser_context(report: dict) -> dict:
    return browser_inspection_module(report) or {}


def current_health_verdict(report: dict) -> dict[str, str]:
    browser = browser_context(report)
    visited = browser.get("visited_pages") or []
    homepage_ok = any(page_judgement(item) == "正常可访问" and str(item.get("url", "")).rstrip("/") == "https://hdu.aiedulab.cn" for item in visited)
    login = browser.get("login") or {}
    login_status = login.get("status", "unknown")
    protected_redirects = [item for item in visited if page_judgement(item) == "受保护跳转"]
    confirmed_failures = evidence_strength_counts(report.get("priority_findings", [])).get("已确认故障", 0)
    if confirmed_failures:
        conclusion = "当前判断：已出现需要优先处置的高可信故障，应立即进入修复闭环。"
    elif login_status != "success" or protected_redirects:
        conclusion = "当前判断：公开首页可访问；管理员登录未通过自动化确认，但这首先反映巡检代理未捕获稳定登录态信号；若人工登录正常，则不构成网站登录故障。受保护入口仍需用人工已确认登录态复测；未发现已确认的生产级故障。"
    elif homepage_ok:
        conclusion = "当前判断：公开首页与登录后页面在本次自动化巡检中可访问，未发现需要立即处置的核心可用性故障。"
    else:
        conclusion = "当前判断：本次证据不足以形成完整健康结论，需要补充关键页面与登录链路复测。"
    return {
        "conclusion": conclusion,
        "public_site": "公开首页浏览器渲染正常" if homepage_ok else "公开首页可用性证据不足",
        "login": "管理员登录已确认" if login_status == "success" else "自动化未确认登录态；人工正常时属巡检能力边界",
        "protected": "受保护入口存在登录页重定向，是否异常取决于角色权限基准" if protected_redirects else "未观察到受保护入口异常跳转",
        "production": "未发现已确认生产故障" if not confirmed_failures else "存在已确认或高可信生产风险",
    }


def score_semantics(score: int, report: dict) -> str:
    verdict = current_health_verdict(report)
    if score >= 85:
        return "健康语义：整体稳定，可作为健康基线留档。"
    if score >= 60:
        return f"健康语义：公开访问可用，自动化深度浏览结论需要复核；人工登录正常时，登录未确认不应解读为网站故障；{verdict['production']}。"
    return "健康语义：自动化巡检压力较高，需区分网站真实故障、权限基准问题和巡检代理识别能力边界。"


def score_band_label(score: int) -> str:
    if score >= 85:
        return "健康基线"
    if score >= 70:
        return "轻度告警"
    if score >= 60:
        return "可访问但需复核"
    if score >= 40:
        return "健康不确定"
    return "高风险"


def report_scope_label(report: dict) -> str:
    if is_multi_site_overall(report):
        return "多站点批量巡检治理汇总"
    module_types = {m.get("report_type") for m in report.get("module_reports", [])}
    has_infra = "host-service-health" in module_types
    has_browser = "browser-inspection" in module_types
    if has_infra and has_browser:
        return "Web 前端 + 浏览器流程 + 基础设施证据"
    if has_browser:
        return "Web 前端与浏览器流程快照"
    return "Web 前端自动化快照"


def clean_site_title(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return ""
    if re.match(r"^[a-z0-9.-]+\.[a-z]{2,}$", text, flags=re.I):
        return ""
    if re.match(r"^[a-z0-9-]{8,}$", text, flags=re.I):
        return ""
    return text


def report_identity(report: dict) -> dict[str, str]:
    explicit = report.get("report_identity") or {}
    site_name = clean_site_title(explicit.get("site_name") or explicit.get("name") or "")
    site_url = str(explicit.get("site_url") or explicit.get("url") or "").strip()
    if site_name and site_url:
        return {"site_name": site_name, "site_url": site_url}

    for module in report.get("module_reports", []) or []:
        if not site_url:
            site_url = str(module.get("final_url") or module.get("url") or module.get("site_url") or "").strip()
        for page in module.get("visited_pages") or []:
            title = clean_site_title(page.get("title") or "")
            if title:
                site_name = site_name or title
                site_url = site_url or str(page.get("url") or "").strip()
                break
        if site_name and site_url:
            break

    if not site_name:
        for system in report.get("systems", []) or []:
            site_name = clean_site_title(system.get("system_name") or system.get("name") or system.get("system_id") or "")
            if site_name:
                break
    if not site_url:
        for system in report.get("systems", []) or []:
            site_url = str(system.get("url") or system.get("site_url") or system.get("base_url") or "").strip()
            if site_url:
                break

    return {
        "site_name": site_name or "网站健康状况",
        "site_url": site_url,
    }


def report_title(report: dict) -> str:
    if is_multi_site_overall(report):
        return multi_site_report_title(report)
    identity = report_identity(report)
    site_name = identity.get("site_name") or "网站健康状况"
    return f"{site_name}｜网站健康巡检报告"


def report_primary_site_name(report: dict) -> str | None:
    identity = report_identity(report)
    if identity.get("site_name") and identity["site_name"] != "网站健康状况":
        return identity["site_name"]
    names: list[str] = []
    for system in report.get("systems", []) or []:
        name = str(system.get("system_name") or system.get("system_id") or "").strip()
        if name and name not in names:
            names.append(name)
    if len(names) == 1:
        return names[0]
    return None


def section_nav_items(report: dict) -> list[tuple[str, str, str]]:
    if is_multi_site_overall(report):
        return [
            ("批次结论", "#overall-batch-brief", "管理层先看"),
            ("覆盖质量", "#overall-coverage-quality", "看边界与缺口"),
            ("健康分布", "#overall-health-distribution", "看站点分布"),
            ("优先站点", "#overall-priority-sites", "先处理谁"),
            ("共性风险", "#overall-common-risks", "看问题族"),
            ("站点矩阵", "#overall-site-matrix", "全量站点"),
            ("复测治理", "#overall-governance-plan", "下一步安排"),
            ("交付索引", "#overall-delivery-index", "打开单站报告"),
        ]
    return [
        ("管理结论", "#executive-decision", "一页读完判断"),
        ("健康总览", "#health-overview", "看范围与分布"),
        ("不健康索引", "#attention-index", "只看需分析项"),
        ("风险域", "#risk-domain-map", "定位责任域"),
        ("评分根因", "#score-breakdown", "理解扣分来源"),
        ("浏览器证据", "#browser-coverage", "核对登录截图"),
        ("系统与模块", "#system-health", "看证明链条"),
        ("复测闭环", "#retest-runbook", "下一步怎么做"),
    ]


SECTION_FOLD_LABELS = {
    "score-breakdown": "评分根因",
    "browser-coverage": "浏览器证据",
    "priority-findings": "优先事项",
    "root-cause-map": "根因地图",
    "system-health": "系统矩阵",
    "module-evidence": "模块证据",
    "evidence-files": "证据文件",
    "retest-runbook": "复测闭环",
    "term-notes": "术语说明",
    "tech-appendix": "技术附录",
}


def render_report_navigation(report: dict) -> str:
    return "\n".join(
        [
            '<nav class="report-nav" aria-label="报告阅读导航">',
            '<button type="button" class="toggle-all" data-toggle-all>展开全部</button>',
            *(f'<a href="{href}"><strong>{esc(label)}</strong><span>{esc(note)}</span></a>' for label, href, note in section_nav_items(report)),
            "</nav>",
        ]
    )


def extract_h2(fragment: str, fallback: str) -> str:
    match = re.search(r"<h2[^>]*>(.*?)</h2>", fragment, flags=re.S)
    if not match:
        return fallback
    text = re.sub(r"<[^>]+>", "", match.group(1))
    return html.unescape(text).strip() or fallback


def extract_section_brief(fragment: str) -> str:
    match = re.search(r'<p class="section-brief">(.*?)</p>', fragment, flags=re.S)
    if not match:
        match = re.search(r'<p class="fine">(.*?)</p>', fragment, flags=re.S)
    if not match:
        return ""
    text = re.sub(r"<[^>]+>", "", match.group(1))
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def collapsible_section(fragment: str, label: str, *, section_id: str | None = None, open_by_default: bool = False) -> str:
    if not fragment.strip():
        return ""
    title = extract_h2(fragment, label)
    brief = extract_section_brief(fragment)
    body = re.sub(r"<h2[^>]*>.*?</h2>", "", fragment, count=1, flags=re.S)
    body = re.sub(r'<div class="section-kicker">.*?</div>', "", body, count=1, flags=re.S)
    body = re.sub(r'^<section([^>]*)>', '<div class="fold-body">', body.strip(), count=1, flags=re.S)
    body = re.sub(r"</section>\s*$", "</div>", body, count=1, flags=re.S)
    open_attr = " open" if open_by_default else ""
    brief_html = f'<span class="fold-brief">{esc(brief)}</span>' if brief else ""
    id_attr = section_id or label
    return "\n".join(
        [
            f'<details class="fold-section" id="{esc(id_attr)}"{open_attr}>',
            "<summary>",
            f'<span class="section-kicker">{esc(label)}</span>',
            f"<strong>{esc(title)}</strong>",
            brief_html,
            "</summary>",
            body,
            "</details>",
        ]
    )


def fold_report_section(fragment: str, section_id: str, *, open_by_default: bool = False) -> str:
    if not str(fragment or "").strip():
        fragment = "\n".join(
            [
                f'<section class="report-section {esc(section_id)}" id="{esc(section_id)}">',
                '<div class="section-kicker">补充说明</div>',
                f"<h2>{esc(SECTION_FOLD_LABELS.get(section_id, section_id))}</h2>",
                '<p class="empty">本次巡检没有生成该类明细证据；该空状态会保留在报告中，便于确认不是交付缺漏。</p>',
                "</section>",
            ]
        )
    return collapsible_section(
        fragment,
        SECTION_FOLD_LABELS.get(section_id, section_id),
        section_id=section_id,
        open_by_default=open_by_default,
    )


def executive_decision_notes(report: dict) -> dict[str, str]:
    verdict = current_health_verdict(report)
    findings = clustered_findings(report.get("priority_findings", []))
    counts = evidence_strength_counts(report.get("priority_findings", []))
    score = int(report.get("score") or 0)
    status = report.get("overall_status", "unknown")
    browser = browser_context(report)
    visited = browser.get("visited_pages") or []
    screenshots = browser_screenshot_files(browser)
    modules = report.get("module_reports", [])
    confirmed = counts.get("已确认故障", 0)
    high = counts.get("高可信风险", 0)
    review = counts.get("需人工复核", 0) + counts.get("自动化识别不足", 0) + counts.get("自动化能力边界", 0)

    if confirmed or high:
        decision = "进入专项处置"
        confidence = "证据强度较高"
        headline = "本次巡检已形成需要优先处置的高可信风险。"
    elif review:
        decision = "先复核再升级"
        confidence = "自动化证据不足以直接定性生产故障"
        headline = "本次更接近自动化巡检能力边界、会话边界与需复核项集合，尚未证明核心业务不可用。"
    else:
        decision = "留档观察"
        confidence = "未形成明显异常证据"
        headline = "本次巡检可作为当前健康快照留档。"

    return {
        "decision": decision,
        "confidence": confidence,
        "headline": headline,
        "verdict": verdict["conclusion"],
        "score": f"{score} / 100",
        "status": STATUS_LABELS.get(status, status),
        "scope": report_scope_label(report),
        "evidence": f"{len(modules)} 个模块、{len(visited)} 个浏览器页面、{len(screenshots)} 张截图、{len(findings)} 个问题簇",
        "boundary": "当前评分代表 Web 前端与浏览器流程快照，不等同于完整生产基础设施健康评分。",
        "next": top_action(report.get("priority_findings", [])),
    }


def render_executive_decision(report: dict) -> str:
    notes = executive_decision_notes(report)
    counts = evidence_strength_counts(report.get("priority_findings", []))
    verdict = current_health_verdict(report)
    return "\n".join(
        [
            '<section class="report-section executive-decision" id="executive-decision">',
            '<div class="section-kicker">管理结论</div>',
            "<h2>一页读完本次健康判断</h2>",
            '<div class="decision-layout">',
            '<article class="decision-main">',
            f'<span class="decision-label">{esc(notes["decision"])}</span>',
            f'<p>{esc(notes["headline"])}</p>',
            f'<p class="fine">{esc(notes["verdict"])}</p>',
            "</article>",
            '<div class="decision-facts">',
            f'<div><span>健康评分</span><strong>{esc(notes["score"])}</strong></div>',
            f'<div><span>整体状态</span><strong>{esc(notes["status"])}</strong></div>',
            f'<div><span>证据强度</span><strong>{esc(notes["confidence"])}</strong></div>',
            f'<div><span>报告口径</span><strong>{esc(notes["scope"])}</strong></div>',
            "</div>",
            "</div>",
            '<div class="decision-strip">',
            f'<div><span>公开首页</span><strong>{esc(verdict["public_site"])}</strong></div>',
            f'<div><span>管理员登录</span><strong>{esc(verdict["login"])}</strong></div>',
            f'<div><span>受保护入口</span><strong>{esc(verdict["protected"])}</strong></div>',
            f'<div><span>生产故障</span><strong>{esc(verdict["production"])}</strong></div>',
            "</div>",
            '<div class="decision-matrix">',
            f'<div><span>已确认故障</span><strong>{esc(counts.get("已确认故障", 0))}</strong><p>可直接进入故障处置的证据。</p></div>',
            f'<div><span>高可信风险</span><strong>{esc(counts.get("高可信风险", 0))}</strong><p>需要技术负责人优先确认。</p></div>',
            f'<div><span>自动化能力边界</span><strong>{esc(counts.get("自动化能力边界", 0))}</strong><p>优先优化巡检代理识别，不直接归咎网站。</p></div>',
            f'<div><span>自动化识别不足</span><strong>{esc(counts.get("自动化识别不足", 0))}</strong><p>先补截图、日志和页面渲染证据。</p></div>',
            f'<div><span>需人工复核</span><strong>{esc(counts.get("需人工复核", 0))}</strong><p>结合业务权限和后端日志判断。</p></div>',
            "</div>",
            '<div class="decision-next">',
            f'<strong>下一步：</strong><span>{esc(notes["next"])}</span>',
            "</div>",
            f'<p class="fine">{esc(notes["boundary"])} 当前证据池：{esc(notes["evidence"])}。</p>',
            "</section>",
        ]
    )


def evidence_status_for_finding(finding: dict) -> str:
    label, _ = classify_finding(finding)
    if label in {"已确认故障", "高可信风险"}:
        return "可升级"
    if label in {"自动化识别不足", "自动化能力边界"}:
        return "先补证据"
    return "需复核"


def owner_role_for_finding(finding: dict) -> str:
    title = str(finding.get("title") or "")
    target = str(finding.get("target") or "")
    if "登录" in title or "auth" in target or "401" in str(finding.get("technical_evidence") or ""):
        return "账号/认证负责人"
    if "受保护页面" in title:
        return "业务权限负责人"
    if "请求失败" in title:
        return "前后端接口负责人"
    if "页面内容过短" in title:
        return "前端负责人"
    return "系统负责人"


def next_evidence_for_finding(finding: dict) -> str:
    title = str(finding.get("title") or "")
    target = str(finding.get("target") or "")
    if "管理员登录状态未确认" in title or "自动化登录态信号未确认" in title:
        return "人工登录成功截图 + 巡检代理登录态识别规则优化"
    if "受保护页面重定向至登录页" in title:
        if "automation_login_status=unknown" in str(finding.get("technical_evidence") or "") or str(finding.get("confidence")) == "automation-boundary":
            return "人工已确认登录态复测截图 + 巡检代理会话保持证据"
        return "角色权限预期表 + 已确认登录态复测截图"
    if "auth/refresh" in target or "401" in str(finding.get("technical_evidence") or ""):
        return "auth/refresh 服务端日志 + 带重试复测结果"
    if "请求失败" in title:
        if target:
            return f"{target} 对应后端日志 + HAR/Network 复测记录"
        return "同 URL 后端日志 + HAR/Network 复测记录"
    if "页面内容过短" in title:
        return "浏览器渲染截图 + 渲染后页面文本"
    return "业务预期说明 + 复测证据"


def evidence_line_for_finding(finding: dict, evidence: str) -> str:
    target = str(finding.get("target") or "").strip()
    text = str(evidence or "").strip()
    if text == "GET net::ERR_ABORTED" and target:
        return f"{target} · {text}"
    return text


def recommendation_line_for_finding(finding: dict, recommendation: str) -> str:
    target = str(finding.get("target") or "").strip()
    text = str(recommendation or "").strip()
    if text in VAGUE_RECOMMENDATION_TEXTS:
        domain = impact_domain_for_finding(finding)
        owner = owner_role_for_finding(finding)
        target_text = f"围绕 {target} " if target else ""
        return f"{target_text}补齐{domain}复测证据、对应服务端日志和业务预期说明，由{owner}判断是否升级为故障。"
    if text == "结合服务器日志、前端构建产物和后端接口状态进一步核查。" and target:
        return f"围绕 {target} 结合服务器日志、前端构建产物和后端接口状态进一步核查。"
    return text


def classification_note_for_finding(finding: dict, note: str) -> str:
    title = str(finding.get("title") or "")
    target = str(finding.get("target") or "").strip()
    if "浏览器资源请求失败" in title and target:
        return f"{target} 捕获到资源请求中断；需结合后端日志和用户路径确认是否影响页面功能。"
    if "浏览器捕获到异常 HTTP 响应" in title and target:
        return f"{target} 返回异常 HTTP 状态；需结合会话状态和接口预期判断。"
    return note


def impact_domain_for_finding(finding: dict) -> str:
    title = str(finding.get("title") or "")
    target = str(finding.get("target") or "")
    if "管理员登录状态未确认" in title or "自动化登录态信号未确认" in title:
        return "自动化巡检能力"
    if "受保护页面重定向至登录页" in title:
        if "automation_login_status=unknown" in str(finding.get("technical_evidence") or "") or str(finding.get("confidence")) == "automation-boundary":
            return "自动化巡检能力"
        return "受保护业务入口"
    if "auth/refresh" in target:
        return "会话保持"
    if "请求失败" in title:
        return "接口加载"
    if "页面内容过短" in title:
        return "内容完整性"
    return "系统健康"


def root_cause_cards(report: dict) -> list[dict]:
    cards = []
    for finding in clustered_findings(report.get("priority_findings", [])):
        label, note = classify_finding(finding)
        cards.append(
            {
                "title": finding.get("title", "未命名问题"),
                "count": finding.get("_cluster_count", 1),
                "classification": label,
                "domain": impact_domain_for_finding(finding),
                "owner": owner_role_for_finding(finding),
                "evidence": next_evidence_for_finding(finding),
                "note": note,
            }
        )
    return cards


def render_management_brief(report: dict) -> str:
    score = int(report.get("score") or 0)
    verdict = current_health_verdict(report)
    findings = report.get("priority_findings", [])
    cards = root_cause_cards(report)
    top_domains = []
    for item in cards:
        if item["domain"] not in top_domains:
            top_domains.append(item["domain"])
    brief = f'{verdict["conclusion"]} 当前评分 {score}/100，语义为“{score_band_label(score)}”。重点复核范围：{"、".join(top_domains[:3]) or "暂无优先风险域"}。'
    return "\n".join(
        [
            '<section class="report-section management-brief" id="management-brief">',
            '<div class="section-kicker">管理层摘录</div>',
            "<h2>可以直接转述的本次结论</h2>",
            f'<p class="brief-copy">{esc(brief)}</p>',
            '<div class="brief-grid">',
            f'<div><span>一句话结论</span><strong>{esc(score_band_label(score))}</strong><p>{esc(verdict["production"])}</p></div>',
            f'<div><span>最大不确定性</span><strong>{esc("自动化登录态识别与权限边界" if findings else "暂无")}</strong><p>人工登录正常时，先优化巡检代理识别能力，再判断网站风险。</p></div>',
            f'<div><span>处置口径</span><strong>先复核再升级</strong><p>当前不宜把所有需复核项直接定性为生产故障。</p></div>',
            "</div>",
            "</section>",
        ]
    )


def render_decision_matrix(report: dict) -> str:
    verdict = current_health_verdict(report)
    rows = [
        ("可以采信", verdict["public_site"], "浏览器截图与页面标题可作为正向证据。"),
        ("暂不定性", verdict["login"], "缺少自动化可识别的稳定登录态信号；人工登录正常时不等同网站故障。"),
        ("必须复核", verdict["protected"], "需要角色权限预期表判断是否异常。"),
        ("不可外推", "完整生产健康", "未覆盖主机、数据库、微服务、DNS/TLS 深度校验和压测。"),
    ]
    return "\n".join(
        [
            '<div class="decision-matrix">',
            *(f'<div><span>{esc(label)}</span><strong>{esc(value)}</strong><p>{esc(note)}</p></div>' for label, value, note in rows),
            "</div>",
        ]
    )


def render_attention_index(report: dict) -> str:
    rows = attention_summary(report)[:8]
    if not rows:
        body = '<p class="empty">本次巡检没有形成需要重点分析的不健康项。</p>'
    else:
        body = "\n".join(
            [
                '<div class="attention-index-table">',
                '<div class="attention-index-head"><span>类别</span><span>重点项</span><span>范围</span><span>下一证据</span></div>',
                *(
                    '<div class="attention-index-row">'
                    f'<span class="review-tag">{esc(row["classification"])}</span>'
                    f'<strong>{esc(row["title"])} <small>× {esc(row["count"])}</small></strong>'
                    f'<span>{esc(row["domain"])} · {esc(row["owner"])}</span>'
                    f'<span>{esc(row["next_evidence"])}</span>'
                    "</div>"
                    for row in rows
                ),
                "</div>",
            ]
        )
    return "\n".join(
        [
            '<section class="report-section attention-index" id="attention-index">',
            '<div class="section-kicker">不健康索引</div>',
            "<h2>哪些内容进入重点分析</h2>",
            '<p class="section-brief">健康项已经在整体画像里作为数据基线展示；下面只列需要解释、复核或闭环的不健康与不确定项。</p>',
            body,
            "</section>",
        ]
    )


def render_risk_domain_map(report: dict) -> str:
    rows = risk_domain_counts(report)
    if not rows:
        body = '<p class="empty">暂无需要展示的风险域。</p>'
    else:
        max_count = max(count for _, count in rows) or 1
        body = "\n".join(
            [
                '<div class="risk-domain-list">',
                *(
                    '<div class="risk-domain-row">'
                    f'<span>{esc(domain)}</span>'
                    f'<div><i style="width:{esc(max(8, round(count / max_count * 100)))}%"></i></div>'
                    f'<strong>{esc(count)}</strong>'
                    "</div>"
                    for domain, count in rows[:8]
                ),
                "</div>",
            ]
        )
    return "\n".join(
        [
            '<section class="report-section risk-domain-section" id="risk-domain-map">',
            '<div class="section-kicker">风险域分布</div>',
            "<h2>不健康项主要集中在哪里</h2>",
            '<p class="section-brief">把同类发现按影响域重新归并，帮助管理者判断应先找认证、接口、内容、权限还是巡检代理负责人。</p>',
            body,
            "</section>",
        ]
    )


def render_handoff_summary(report: dict) -> str:
    copy_text = handoff_summary_text(report)
    return "\n".join(
        [
            '<section class="report-section handoff-summary" id="handoff-summary">',
            '<div class="section-kicker">交付摘要</div>',
            "<h2>可直接放进工单或周报的一段话</h2>",
            f'<p class="handoff-copy" data-copy-source="handoff-summary">{esc(copy_text)}</p>',
            '<button type="button" class="copy-button" data-copy-target="handoff-summary">复制摘要</button>',
            '<p class="fine">这段摘要不替代正文证据，适合复制给负责人快速建立统一口径。</p>',
            "</section>",
        ]
    )


def render_verdict_action_chain(report: dict) -> str:
    verdict = current_health_verdict(report)
    actions = [
        ("先确认", "人工复核管理员登录是否成功，并截图记录账号/角色标识。"),
        ("再对照", "按角色权限预期表判断课程、实验、考试等入口跳转是否正常。"),
        ("后闭环", "用服务端日志和带重试复测确认 auth/login、auth/refresh 与 401 根因。"),
    ]
    return "\n".join(
        [
            '<div class="verdict-action-chain">',
            f'<p>{esc(verdict["conclusion"])}</p>',
            "<ol>",
            *(f'<li><span>{esc(label)}</span>{esc(note)}</li>' for label, note in actions),
            "</ol>",
            "</div>",
        ]
    )


def render_evidence_ladder(report: dict) -> str:
    findings = report.get("priority_findings", [])
    counts = evidence_strength_counts(findings)
    items = [
        ("已确认故障", counts.get("已确认故障", 0), "可直接进入修复闭环"),
        ("高可信风险", counts.get("高可信风险", 0), "优先组织技术负责人复核"),
        ("自动化能力边界", counts.get("自动化能力边界", 0), "先优化巡检代理，避免误报升级"),
        ("自动化识别不足", counts.get("自动化识别不足", 0), "先补证据，避免误报升级"),
        ("需人工复核", counts.get("需人工复核", 0), "结合权限基准和日志判断"),
    ]
    return "\n".join(
        [
            '<div class="evidence-ladder" aria-label="证据可信度阶梯">',
            *(f'<div><span>{esc(label)}</span><strong>{esc(count)}</strong><small>{esc(note)}</small></div>' for label, count, note in items),
            "</div>",
        ]
    )


def render_inspector_verdict(report: dict) -> str:
    score = int(report.get("score") or 0)
    verdict = current_health_verdict(report)
    items = [
        ("公开站点", verdict["public_site"]),
        ("登录链路", verdict["login"]),
        ("受保护入口", verdict["protected"]),
        ("生产故障", verdict["production"]),
    ]
    return "\n".join(
        [
            '<section class="report-section inspector-verdict" id="inspector-verdict">',
            '<div class="section-kicker">检测员结论</div>',
            "<h2>本次健康检测的最终判定</h2>",
            f'<p class="auditor-verdict">{esc(verdict["conclusion"])}</p>',
            '<div class="verdict-grid">',
            *(f'<div><span>{esc(label)}</span><strong>{esc(value)}</strong></div>' for label, value in items),
            "</div>",
            render_verdict_action_chain(report),
            render_decision_matrix(report),
            f'<p class="fine">{esc(score_semantics(score, report))} 本结论基于单次 Web 前端与浏览器巡检快照，不替代基础设施和服务端健康监控。</p>',
            "</section>",
        ]
    )


def render_inspection_scope(report: dict) -> str:
    modules = [MODULE_LABELS.get(m.get("report_type"), m.get("report_type") or m.get("file") or "未知模块") for m in report.get("module_reports", [])]
    covered = "、".join(modules) if modules else "暂无模块数据"
    missing = ["主机资源", "数据库状态", "微服务内部健康", "DNS 配置", "SSL 证书深度校验", "性能压测"]
    return "\n".join(
        [
            '<section class="report-section scope-section" id="inspection-scope">',
            '<div class="section-kicker">巡检边界</div>',
            "<h2>这份报告能说明什么，不能说明什么</h2>",
            '<div class="scope-grid">',
            f'<div><h3>已覆盖</h3><p>{esc(covered)}。报告结论主要基于 Web 前端可达性、页面内容、登录后浏览器实测和接口响应信号。</p></div>',
            f'<div><h3>未覆盖</h3><p>{esc("、".join(missing))}。若需要完整生产健康结论，应补充基础设施、服务端日志和性能监控数据。</p></div>',
            "</div>",
            "</section>",
        ]
    )


def render_next_detection_checklist(report: dict) -> str:
    score = int(report.get("score") or 0)
    checks = [
        ("角色权限预期表", "明确 admin 对课程、教室、实验、考试等入口是否应直接可访问，避免把正常授权跳转误判为故障。"),
        ("服务端登录/鉴权日志", "核对登录提交、会话写入、auth/login 与 auth/refresh 的服务端返回，关闭 401 与请求中断的根因。"),
        ("TLS / DNS 基础检查", "补充证书链、证书有效期、DNS 解析、HTTP 到 HTTPS 跳转和安全响应头等站点基础健康项。"),
        ("三次重试与间隔检测", "在不同时间点重复关键路径，记录连续失败比例、响应时间波动和偶发/持续判断。"),
        ("关键业务路径断言", "为首页、登录、课程、实验、考试、资源下载等入口设定可复测成功条件。"),
        ("基础设施监控数据", "补充主机资源、数据库、微服务内部健康、应用日志和性能监控，形成完整生产健康结论。"),
    ]
    return "\n".join(
        [
            '<section class="report-section next-detection" id="next-detection">',
            '<div class="section-kicker">复测清单</div>',
            "<h2>下一次检测应补充什么</h2>",
            f'<p class="section-brief">当前 {esc(score)} 分是单次自动化巡检快照下的健康压力评分。若要把它升级为生产级健康结论，需要补齐下面这些可复测证据。</p>',
            '<div class="next-check-grid">',
            *(f'<article><span>{esc(label)}</span><p>{esc(note)}</p></article>' for label, note in checks),
            "</div>",
            '<p class="fine">稳定性说明：本次报告未覆盖多时间点对比、连续失败比例、响应时间分位数和服务端监控趋势，因此不能单独判断问题是偶发还是持续。</p>',
            "</section>",
        ]
    )


def render_retest_runbook(report: dict) -> str:
    steps = [
        ("准备", "确认管理员账号、验证码/二次认证要求、角色权限预期表和复测时间窗口。"),
        ("执行", "连续执行 3 次登录、首页、课程、实验、考试、资源入口访问，并留存截图。"),
        ("对账", "把浏览器结果与 auth/login、auth/refresh、授权日志、前端 Network 记录逐项对齐。"),
        ("判定", "只有连续复现且服务端日志支持的异常，才升级为真实故障或高可信风险。"),
    ]
    return "\n".join(
        [
            '<section class="report-section retest-runbook" id="retest-runbook">',
            '<div class="section-kicker">复测剧本</div>',
            "<h2>如何把本次快照变成闭环结论</h2>",
            '<div class="runbook-steps">',
            *(f'<div><span>{esc(label)}</span><p>{esc(note)}</p></div>' for label, note in steps),
            "</div>",
            '<div class="retest-timeline">',
            '<div><span>T+0</span><p>保存本次 HTML、JSON、截图和质量审计结果，作为快照基线。</p></div>',
            '<div><span>T+1</span><p>完成人工登录复核、角色权限预期表和 auth 日志对账。</p></div>',
            '<div><span>T+2</span><p>执行至少 3 次关键路径复测，记录失败比例和截图。</p></div>',
            '<div><span>T+3</span><p>根据复测证据将问题定性为真实故障、权限预期、自动化能力边界或关闭项。</p></div>',
            "</div>",
            '<p class="fine">建议把复测结果追加到同一报告目录，形成“自动化发现 -> 人工复核 -> 服务端对账 -> 最终定性”的闭环链路。</p>',
            "</section>",
        ]
    )


def render_term_notes() -> str:
    items = [
        ("登录未确认", "巡检代理未捕获稳定登录态信号；人工登录正常时，这是自动化/MCP 操控能力边界，不是网站故障。"),
        ("受保护跳转", "页面回到登录页，可能是正常鉴权，也可能是登录态或权限问题。"),
        ("401", "认证边界常见状态码，需结合会话状态判断是否异常。"),
        ("ERR_ABORTED", "浏览器请求被取消，可能由页面跳转、前端主动取消或真实接口异常触发。"),
    ]
    return "\n".join(
        [
            '<section class="report-section term-notes" id="term-notes">',
            '<div class="section-kicker">术语说明</div>',
            "<h2>避免误读的几个关键词</h2>",
            '<div class="term-grid">',
            *(f'<div><span>{esc(label)}</span><p>{esc(note)}</p></div>' for label, note in items),
            "</div>",
            "</section>",
        ]
    )


def module_score_text(module: dict) -> str:
    score = module.get("score")
    return "未单独评分" if score is None else f"{score}/100"


def format_ms(value) -> str:
    try:
        if value is None or value == "":
            return "未采集"
        return f"{int(round(float(value)))} ms"
    except (TypeError, ValueError):
        return "未采集"


def browser_performance_metrics(module: dict) -> dict:
    return module.get("metrics") or {}


def browser_performance_summary(module: dict) -> str:
    metrics = browser_performance_metrics(module)
    checked = metrics.get("checked_pages")
    avg_open = metrics.get("avg_open_time_ms")
    max_open = metrics.get("max_open_time_ms")
    slow_pages = metrics.get("slow_pages")
    avg_ttfb = metrics.get("avg_ttfb_ms")
    if avg_open is None and max_open is None:
        return "性能快照：未采集页面打开时间；本次报告仍保留可访问性、截图和请求异常证据。"
    return (
        f"性能快照：本次单次观测 {checked if checked is not None else '若干'} 个页面，"
        f"平均打开时间 {format_ms(avg_open)}，最慢页面 {format_ms(max_open)}，"
        f"慢页面 {slow_pages if slow_pages is not None else '未统计'} 个，平均 TTFB {format_ms(avg_ttfb)}。"
        "该数据受巡检机网络、浏览器冷启动、缓存和站点当时状态影响，不等同于持续监控或压测结果。"
    )


def slowest_pages(module: dict, limit: int = 5) -> list[dict]:
    rows = []
    for item in module.get("visited_pages") or []:
        performance = item.get("performance") or {}
        try:
            open_time = int(round(float(performance.get("open_time_ms"))))
        except (TypeError, ValueError):
            continue
        rows.append({"page": item, "performance": performance, "open_time_ms": open_time})
    rows.sort(key=lambda row: row["open_time_ms"], reverse=True)
    return rows[:limit]


def module_summary_text(module: dict) -> str:
    summary = localize_summary(module.get("summary"))
    if summary:
        return summary
    report_type = module.get("report_type")
    if report_type == "browser-inspection":
        login = module.get("login") or {}
        visited_count = len(module.get("visited_pages") or [])
        finding_count = len(module.get("findings") or [])
        note = login.get("note") or "已执行浏览器页面访问与证据采集。"
        return f"{note} 本模块访问 {visited_count} 个页面，记录 {finding_count} 条浏览器侧发现。"
    return "本模块已执行，未返回额外摘要。"


def module_metric_items(module: dict) -> list[tuple[str, str]]:
    metrics = module.get("metrics") or {}
    items = []
    for key, value in metrics.items():
        label = METRIC_LABELS.get(key, key)
        display = format_ms(value) if key.endswith("_ms") else str(value)
        items.append((label, display))
    if items:
        return items
    if module.get("report_type") == "browser-inspection":
        login = module.get("login") or {}
        status = "已确认" if login.get("status") == "success" else "需复核"
        screenshot_count = len(browser_screenshot_files(module))
        return [
            ("登录状态", status),
            ("访问页面", str(len(module.get("visited_pages") or []))),
            ("截图证据", str(screenshot_count)),
            ("请求失败", str(len(module.get("request_failures") or []))),
            ("异常响应", str(len(module.get("abnormal_responses") or []))),
            ("发现数", str(len(module.get("findings") or []))),
        ]
    return []


def module_evidence_note(module: dict) -> str:
    report_type = module.get("report_type")
    if report_type == "content-review":
        return "重点用于确认入口页内容是否完整、响应时间是否处于可接受范围。"
    if report_type == "browser-inspection":
        return "重点用于复核登录链路、受保护页面跳转和浏览器侧接口异常。"
    if report_type == "host-service-health":
        return "重点用于确认主机、端口或微服务基础健康状态。"
    return "用于补充支撑本次巡检结论。"


def module_review_focus(module: dict) -> str:
    report_type = module.get("report_type")
    if report_type == "content-review":
        return "复核入口页是否为单页应用；若浏览器截图显示内容完整，HTTP 文本过短应降级为自动化识别不足。"
    if report_type == "browser-inspection":
        return "优先区分自动化登录态识别失败与网站真实登录失败；若人工登录正常，应把登录未确认归为巡检能力边界，再复核受保护页面跳转是否符合账号权限。"
    if report_type == "host-service-health":
        return "结合监控平台确认 CPU、内存、端口、服务进程和基础依赖是否正常。"
    return "结合模块原始证据和业务预期确认是否需要进入修复闭环。"


def module_inspector_judgement(module: dict) -> str:
    report_type = module.get("report_type")
    status = module.get("status", "unknown")
    if report_type == "content-review":
        return "检测员判定：内容完整性模块适合发现入口页不可达、空白页和明显文本缺失；对 SPA 页面应让位于浏览器截图证据，疑似内容过短不应单独升级为主要故障。"
    if report_type == "browser-inspection":
        login = module.get("login") or {}
        visited = module.get("visited_pages") or []
        protected = sum(1 for item in visited if page_judgement(item) == "受保护跳转")
        if login.get("status") == "success":
            return f"检测员判定：浏览器实测已确认登录态，访问 {len(visited)} 个页面；仍需按业务基准复核 {protected} 个受保护入口的访问策略。"
        return f"检测员判定：公开页面可读性有截图支撑，但管理员登录态未被巡检代理稳定识别；若人工登录正常，该项属于自动化能力边界。{protected} 个受保护入口需用人工已确认登录态和角色权限基准复测。"
    if report_type == "host-service-health":
        if status == "healthy":
            return "检测员判定：主机或服务基础健康未见明显异常，可作为生产健康结论的支撑证据之一。"
        return "检测员判定：主机或服务健康证据不足或存在告警，应结合监控平台、端口状态和服务进程复核。"
    return "检测员判定：本模块提供辅助证据，是否进入修复闭环取决于业务预期、复测结果和服务端日志。"


def module_findings_summary(module: dict) -> tuple[int, str]:
    findings = module.get("findings") or []
    if not findings:
        return (0, "未形成明确问题项，本模块主要提供覆盖性证据。")
    titles: dict[str, int] = {}
    for finding in findings:
        title = str(finding.get("title") or "未命名发现")
        titles[title] = titles.get(title, 0) + 1
    top = sorted(titles.items(), key=lambda item: item[1], reverse=True)[:3]
    summary = "；".join(f"{title} {count} 条" for title, count in top)
    return (len(findings), summary)


def module_evidence_strength(module: dict) -> str:
    report_type = module.get("report_type")
    if report_type == "browser-inspection":
        screenshots = len(browser_screenshot_files(module))
        visited = len(module.get("visited_pages") or [])
        if screenshots >= 4 and visited >= 4:
            return "证据较充分：已包含浏览器访问记录、页面截图和接口响应信号。"
        return "证据中等：已执行浏览器检查，但截图或页面覆盖仍可补充。"
    if report_type == "content-review":
        return "证据中等：HTTP 内容检查可快速发现入口异常，但对单页应用需要结合浏览器截图复核。"
    return "证据补充项：用于支撑整体判断，必要时需结合外部监控或日志。"


def module_evidence_gap(module: dict) -> str:
    report_type = module.get("report_type")
    if report_type == "content-review":
        return "缺口：普通 HTTP 检查不执行前端 JavaScript，需要浏览器截图或渲染后文本作为最终依据。"
    if report_type == "browser-inspection":
        return "缺口：自动化代理未必能识别真实登录态；需要人工登录成功截图、账号角色标识、服务端日志和角色权限预期表共同闭环。"
    if report_type == "host-service-health":
        return "缺口：需要监控平台、进程状态和基础依赖指标支撑持续健康判断。"
    return "缺口：需要结合业务预期和外部证据确认模块结论。"


def render_module_details(modules: list[dict]) -> str:
    attention_modules = [module for module in modules if module_has_findings(module)]
    healthy_modules = [module for module in modules if not module_has_findings(module)]
    ordered_modules = attention_modules + healthy_modules
    parts = [
        '<section class="report-section module-evidence" id="module-evidence">',
        '<div class="section-kicker">模块证据</div>',
        "<h2>健康模块收敛展示，异常模块重点分析</h2>",
        f'<p class="section-brief">本节共覆盖 {esc(len(modules))} 个模块，其中 {esc(len(healthy_modules))} 个作为健康证据基线紧凑呈现，{esc(len(attention_modules))} 个进入重点分析。原始 JSON 和细节日志仍保留在技术证据附录。</p>',
        '<div class="module-cards">',
    ]
    for module in ordered_modules:
        label = MODULE_LABELS.get(module.get("report_type"), module.get("report_type") or module.get("file") or "未知模块")
        status = module.get("status", "unknown")
        metrics = module_metric_items(module)
        finding_count, findings_text = module_findings_summary(module)
        has_findings = module_has_findings(module)
        insight_html = ""
        if has_findings:
            insight_html = "\n".join(
                [
                    '<div class="module-insights">',
                    f'<div><span>检测员判定</span><p>{esc(module_inspector_judgement(module))}</p></div>',
                    f'<div><span>证据结论</span><p>{esc(module_evidence_note(module))}</p></div>',
                    f'<div><span>发现摘要</span><p>{esc(findings_text)}</p></div>',
                    f'<div><span>复核重点</span><p>{esc(module_review_focus(module))}</p></div>',
                    f'<div><span>证据缺口</span><p>{esc(module_evidence_gap(module))}</p></div>',
                    "</div>",
                ]
            )
        else:
            insight_html = (
                '<p class="module-baseline-note">'
                f'健康基线：{esc(module_evidence_note(module))} 本模块无优先发现，保留状态、分数和关键指标用于整体健康画像。'
                "</p>"
            )
        parts.extend(
            [
                f'<article class="module-card module-{esc(status)} {"module-baseline" if not has_findings else "module-attention"}">',
                '<div class="module-card-head">',
                "<div>",
                f"<h3>{esc(label)}</h3>",
                f'<p>{esc(module_summary_text(module))}</p>',
                "</div>",
                '<div class="module-status-stack">',
                status_badge(status),
                f'<span>{esc(module_score_text(module))}</span>',
                "</div>",
                "</div>",
                insight_html,
            ]
        )
        if metrics:
            parts.append('<div class="module-metrics">')
            for name, value in metrics[:8]:
                parts.append(f'<div><span>{esc(name)}</span><strong>{esc(value)}</strong></div>')
            parts.append("</div>")
        else:
            parts.append('<p class="empty">本模块未返回结构化指标，建议查看技术证据附录。</p>')
        parts.append(
            '<p class="module-note">'
            f'<strong>证据强度：</strong>{esc(module_evidence_strength(module))} '
            f'<strong>模块发现数：</strong>{esc(finding_count)}'
            "</p>"
        )
        parts.append("</article>")
    parts.extend(["</div>", "</section>"])
    return "\n".join(parts)


def system_risk_sources(system: dict, findings: list[dict]) -> str:
    sid = system.get("system_id")
    related = [f for f in findings if f.get("system_id") == sid]
    if not related:
        return "当前未聚合到优先问题，建议保留为健康基线。"
    clusters = clustered_findings(related)[:3]
    return "；".join(f"{item.get('title')}（{item.get('_cluster_count', 1)} 条）" for item in clusters)


def system_next_action(system: dict, findings: list[dict]) -> str:
    text = system_risk_sources(system, findings)
    if "登录" in text or "认证" in text or "重定向" in text:
        return "先复核管理员登录会话和账号权限，再判断受保护页面跳转是否为真实故障。"
    if "内容" in text or "body_length" in text:
        return "对照浏览器截图确认入口页是否完整渲染，避免把单页应用误报升级为故障。"
    if system.get("status") == "healthy":
        return "维持例行巡检，并将本次结果作为后续对比基线。"
    return "按优先事项逐条复核，并补充服务端日志或监控数据。"


def system_health_boundary(system: dict) -> str:
    modules = system.get("modules", {})
    missing = []
    if "host-service-health" not in modules:
        missing.append("主机/微服务")
    if "browser-inspection" not in modules:
        missing.append("浏览器流程")
    if "content-review" not in modules:
        missing.append("内容完整性")
    if not missing:
        return "覆盖较完整，可结合复测结果作为系统健康基线。"
    return f"本系统仍缺少 {'、'.join(missing)} 证据，当前更适合作为 Web 巡检结论，而非完整生产健康结论。"


def render_system_health_matrix(systems: list[dict], findings: list[dict]) -> str:
    attention_systems = [system for system in systems if system.get("status") != "healthy"]
    healthy_systems = [system for system in systems if system.get("status") == "healthy"]
    ordered_systems = attention_systems + healthy_systems
    parts = [
        '<section class="report-section system-health-section" id="system-health">',
        '<div class="section-kicker">系统矩阵</div>',
        "<h2>先看异常系统，再收敛健康系统</h2>",
        f'<p class="section-brief">本节先展示 {esc(len(attention_systems))} 个需要关注的系统，再把 {esc(len(healthy_systems))} 个健康系统作为基线数据收敛展示。健康项只保留数据，不展开长分析。</p>',
        '<div class="system-status-summary">',
        f'<div><span>健康系统</span><strong>{esc(len(healthy_systems))}</strong></div>',
        f'<div><span>需关注系统</span><strong>{esc(len(attention_systems))}</strong></div>',
        f'<div><span>系统总数</span><strong>{esc(len(systems))}</strong></div>',
        "</div>",
        '<div class="system-health-list">',
    ]
    if not systems:
        parts.append('<p class="empty">本次报告未聚合到系统级结果。</p>')
    for system in ordered_systems:
        modules_text = "、".join(MODULE_LABELS.get(key, key) for key in system.get("modules", {}).keys()) or "无"
        status = system.get("status", "unknown")
        is_healthy = status == "healthy"
        detail_html = (
            '<div class="system-health-meta system-baseline-meta">'
            f'<div><span>模块覆盖</span><p>{esc(modules_text)}</p></div>'
            f'<div><span>基线说明</span><p>当前未聚合到优先问题，作为整体健康画像的数据支撑。</p></div>'
            "</div>"
            if is_healthy
            else "\n".join(
                [
                    '<div class="system-health-meta">',
                    f'<div><span>模块覆盖</span><p>{esc(modules_text)}</p></div>',
                    f'<div><span>建议动作</span><p>{esc(system_next_action(system, findings))}</p></div>',
                    f'<div><span>健康边界</span><p>{esc(system_health_boundary(system))}</p></div>',
                    "</div>",
                ]
            )
        )
        parts.extend(
            [
                f'<article class="system-health-card system-{esc(status)} {"system-baseline" if is_healthy else "system-attention"}">',
                '<div class="system-health-main">',
                "<div>",
                f'<h3>{esc(system.get("system_name") or system.get("system_id"))}</h3>',
                f'<p>{esc(system_risk_sources(system, findings))}</p>',
                "</div>",
                '<div class="system-status-block">',
                status_badge(status),
                f'<strong>{esc(system.get("findings", 0))}</strong><span>发现数</span>',
                "</div>",
                "</div>",
                detail_html,
                "</article>",
            ]
        )
    parts.extend(["</div>", "</section>"])
    return "\n".join(parts)


def top_action(findings: list[dict]) -> str:
    if not findings:
        return "本次巡检未发现需要优先处理的问题，建议保留巡检记录并维持常规监测。"
    first = findings[0]
    title = first.get("title") or "优先问题"
    recommendation = first.get("recommendation") or "请安排负责人复核并制定修复计划。"
    return f"优先处理“{title}”：{recommendation}"


def compact_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def compact_raw_preview(value):
    if isinstance(value, list):
        return value[:3]
    if isinstance(value, dict):
        return {key: value[key] for key in list(value.keys())[:8]}
    return value


def technical_summary_rows(report: dict) -> list[dict]:
    rows: list[dict] = []
    for module in report.get("module_reports", []):
        module_name = MODULE_LABELS.get(module.get("report_type"), module.get("report_type") or module.get("file") or "未知模块")
        for key, label in TECHNICAL_COLLECTIONS.items():
            value = module.get(key)
            if not value:
                continue
            count = len(value) if isinstance(value, list) else 1
            if key == "visited_pages" and isinstance(value, list):
                impact = f"已访问 {count} 个页面，主要用于证明页面可达与截图留证。"
                action = "抽查访问截图和页面标题，确认关键功能入口是否覆盖。"
            elif key == "screenshots" and isinstance(value, list):
                impact = f"已保存 {count} 张截图，可作为页面状态证据。"
                action = "优先查看登录前、登录后和异常页面截图。"
            elif key == "console_messages" and isinstance(value, list):
                errors = [item for item in value if str(item.get("type")) in {"error", "warning"}]
                impact = f"捕获 {len(errors)} 条错误/警告类控制台消息。"
                action = "结合前端构建产物和接口日志判断是否影响用户流程。"
            elif key == "request_failures" and isinstance(value, list):
                impact = f"捕获 {count} 次浏览器资源请求失败。"
                action = "按 URL 对照后端日志，确认是否为预期中断、鉴权边界或真实接口失败。"
            elif key == "abnormal_responses" and isinstance(value, list):
                impact = f"捕获 {count} 个异常 HTTP 响应。"
                action = "确认状态码是否为业务预期，特别是认证刷新、权限校验类接口。"
            else:
                impact = f"记录 {count} 条技术证据。"
                action = "按需展开原始数据复核。"
            rows.append({"module": module_name, "type": label, "count": count, "impact": impact, "action": action, "raw": value})
    return rows


def render_appendix_usage_guide() -> str:
    items = [
        ("管理者", "只看影响判断和建议动作，不需要展开原始 JSON。"),
        ("技术负责人", "按请求失败、异常响应、控制台消息定位接口或前端模块。"),
        ("复测人员", "用访问页面和截图清单复核关键路径是否覆盖。"),
    ]
    return "\n".join(
        [
            '<div class="appendix-guide">',
            *(f'<div><span>{esc(role)}</span><p>{esc(note)}</p></div>' for role, note in items),
            "</div>",
        ]
    )


def render_technical_appendix(report: dict) -> str:
    rows = technical_summary_rows(report)
    score_review = report.get("score_review") or {}
    score_review_html = ""
    if score_review:
        status = score_review.get("score_audit_status") or score_review.get("status") or "unknown"
        note = score_review.get("note") or "未记录人工说明。"
        score_review_html = "\n".join(
            [
                '<details class="tech-summary">',
                "<summary>评分合理性复核</summary>",
                '<div class="tech-summary-body">',
                f'<p><strong>审计状态：</strong>{esc(status)}</p>',
                f'<p><strong>人工说明：</strong>{esc(note)}</p>',
                f'<p class="fine">评分审计是正式渲染前门禁；低分或疑似重复扣分需要先完成复核。</p>',
                "</div>",
                "</details>",
            ]
        )
    if not rows:
        return "\n".join(
            [
                '<section class="report-section tech-appendix" id="tech-appendix">',
                '<div class="section-kicker">技术证据附录</div>',
                "<h2>需要时再展开的原始证据</h2>",
                '<p class="empty">本次报告未包含额外原始技术证据。</p>',
                score_review_html,
                "</section>",
            ]
        )
    parts = [
        '<section class="report-section tech-appendix" id="tech-appendix">',
        '<div class="section-kicker">技术证据附录</div>',
        "<h2>需要时再展开的原始证据</h2>",
        '<p class="fine">本节优先展示管理者可读摘要，原始 JSON 默认收起，仅供技术人员复核定位使用。</p>',
        render_appendix_usage_guide(),
        score_review_html,
    ]
    visible_rows = rows[:MAX_TECH_APPENDIX_ROWS]
    hidden_rows = max(0, len(rows) - len(visible_rows))
    if hidden_rows:
        parts.append(f'<p class="fine">为压缩报告长度，默认仅展示前 {esc(len(visible_rows))} 组技术证据摘要；其余 {esc(hidden_rows)} 组保留在 <code>final-report.json</code> 和模块原始报告中。</p>')
    for idx, row in enumerate(visible_rows, 1):
        parts.extend(
            [
                '<details class="tech-summary">',
                f'<summary>{esc(row["type"])} · {esc(row["module"])} · {esc(row["count"])} 条</summary>',
                '<div class="tech-summary-body">',
                f'<p><strong>影响判断：</strong>{esc(row["impact"])}</p>',
                f'<p><strong>建议动作：</strong>{esc(row["action"])}</p>',
                '<details class="raw-json">',
                f"<summary>展开 JSON 预览 #{idx}</summary>",
                f"<pre><code>{esc(compact_json(compact_raw_preview(row['raw'])))}</code></pre>",
                '<p class="fine">为缩短 HTML，本处只嵌入前 3 条预览；完整原始数据请查看 <code>final-report.json</code> 或对应模块报告。</p>',
                "</details>",
                "</div>",
                "</details>",
            ]
        )
    parts.append("</section>")
    return "\n".join(parts)


def render_browser_coverage(report: dict, out_dir: Path | None = None) -> str:
    browser_modules = [m for m in report.get("module_reports", []) if m.get("report_type") == "browser-inspection"]
    if not browser_modules:
        return ""
    module = browser_modules[0]
    login = module.get("login") or {}
    visited = module.get("visited_pages") or []
    screenshot_count = len(browser_screenshot_files(module))
    status = login.get("status", "unknown")
    status_text = "已确认登录成功" if status == "success" else "登录状态需复核"
    note = login.get("note", "")
    parts = [
        '<section class="report-section browser-coverage" id="browser-coverage">',
        '<div class="section-kicker">浏览器巡检覆盖</div>',
        "<h2>登录链路是否真的失败</h2>",
        '<div class="score-explainer">',
        f'<div><span>登录状态</span><strong>{esc(status_text)}</strong></div>',
        f'<div><span>访问页面</span><strong>{len(visited)}</strong></div>',
        f'<div><span>截图证据</span><strong>{screenshot_count}</strong></div>',
        f'<div><span>发现数</span><strong>{len(module.get("findings") or [])}</strong></div>',
        "</div>",
        f'<p class="fine">{esc(note)}。若登录状态显示“需复核”，表示巡检代理已进入站点页面并采集截图，但未捕获稳定登录态信号；人工登录正常时，该项应视为自动化能力边界。</p>',
        render_browser_performance_snapshot(module),
        render_auth_signal_summary(module),
        render_login_evidence_boundary(module),
        render_access_policy_baseline(module),
        render_request_failure_closure(module),
        render_screenshot_index(module, out_dir),
    ]
    if visited:
        visible_visited = visited[:MAX_BROWSER_TABLE_ROWS]
        hidden_visited = max(0, len(visited) - len(visible_visited))
        if hidden_visited:
            parts.append(f'<p class="fine">页面覆盖表默认展示前 {esc(len(visible_visited))} 个关键入口，其余 {esc(hidden_visited)} 个入口保留在技术附录和 JSON 中，避免正文过长。</p>')
        parts.extend(
            [
                '<div class="table-wrap">',
                "<table><thead><tr><th>业务入口</th><th>页面标识</th><th>URL</th><th>判断</th><th>检测员备注</th><th>截图</th></tr></thead><tbody>",
            ]
        )
        for item in visible_visited:
            judgement = page_judgement(item)
            parts.append(
                "<tr>"
                f'<td>{esc(business_area_for_page(item))}</td>'
                f'<td>{esc(item.get("label"))}</td>'
                f'<td><a href="{esc(item.get("url"))}">{esc(item.get("url"))}</a></td>'
                f'<td><span class="review-tag">{esc(judgement)}</span></td>'
                f'<td>{esc(page_review_note(item))}<br><span class="fine">{esc(item.get("title"))}</span></td>'
                f'<td>{esc(item.get("screenshot"))}</td>'
                "</tr>"
            )
        parts.extend(["</tbody></table>", "</div>"])
    parts.append("</section>")
    return "\n".join(parts)


def render_browser_performance_snapshot(module: dict) -> str:
    metrics = browser_performance_metrics(module)
    rows = slowest_pages(module)
    if not metrics and not rows:
        return "\n".join(
            [
                '<div class="diagnostic-panel performance-panel">',
                "<h3>性能快照：未采集页面打开时间</h3>",
                "<p>本次浏览器实测未返回页面打开时间；可访问性、截图和请求异常证据仍保留。后续复测可重新运行深度浏览巡检补齐该项。</p>",
                "</div>",
            ]
        )
    summary_cards = [
        ("平均打开时间", format_ms(metrics.get("avg_open_time_ms"))),
        ("最慢页面", format_ms(metrics.get("max_open_time_ms"))),
        ("慢页面数", str(metrics.get("slow_pages", "未统计"))),
        ("平均 TTFB", format_ms(metrics.get("avg_ttfb_ms"))),
    ]
    parts = [
        '<div class="diagnostic-panel performance-panel">',
        "<h3>性能快照：页面打开时间与网速观测</h3>",
        f"<p>{esc(browser_performance_summary(module))}</p>",
        '<div class="diagnostic-grid">',
        *(f"<div><span>{esc(label)}</span><strong>{esc(value)}</strong><p>单次浏览器巡检观测值。</p></div>" for label, value in summary_cards),
        "</div>",
    ]
    if rows:
        parts.extend(
            [
                '<div class="table-wrap">',
                "<table><thead><tr><th>页面</th><th>URL</th><th>打开时间</th><th>TTFB</th><th>DOM Ready</th><th>Load</th></tr></thead><tbody>",
            ]
        )
        for row in rows:
            page = row["page"]
            performance = row["performance"]
            parts.append(
                "<tr>"
                f"<td>{esc(page.get('label') or page.get('title') or '页面')}</td>"
                f'<td><a href="{esc(page.get("url"))}">{esc(page.get("url"))}</a></td>'
                f"<td>{esc(format_ms(performance.get('open_time_ms')))}</td>"
                f"<td>{esc(format_ms(performance.get('ttfb_ms')))}</td>"
                f"<td>{esc(format_ms(performance.get('dom_content_loaded_ms')))}</td>"
                f"<td>{esc(format_ms(performance.get('load_event_ms')))}</td>"
                "</tr>"
            )
        parts.extend(["</tbody></table>", "</div>"])
    parts.append("</div>")
    return "\n".join(parts)


def render_login_evidence_boundary(module: dict) -> str:
    login = module.get("login") or {}
    visited = module.get("visited_pages") or []
    after_login = next((item for item in visited if item.get("label") == "after-login"), {})
    request_failures = module.get("request_failures") or []
    abnormal = module.get("abnormal_responses") or []
    login_failures = [item for item in request_failures if "auth/login" in str(item)]
    refresh_401 = [item for item in abnormal if "auth/refresh" in str(item) or "401" in str(item)]
    rows = [
        ("是否提交登录表单", "已尝试提交", "报告存在 after-login 截图与登录后页面记录，但仍需结合服务端日志确认提交是否成功。"),
        ("提交后看到的页面", after_login.get("url") or "未记录", after_login.get("text_excerpt", "")[:80] or login.get("note", "未记录页面摘要")),
        ("自动化未确认原因", "巡检代理未捕获稳定登录态信号", "未发现足够明确的账号标识、后台落地页或退出登录等成功信号；这不等同于人工登录失败。"),
        ("登录接口信号", "需复核", f"捕获 auth/login 请求中断 {len(login_failures)} 条；该现象可能来自导航取消、前端主动取消或接口真实失败。"),
        ("会话刷新信号", "需复核", f"捕获 auth/refresh/401 相关信号 {len(refresh_401)} 条；需结合后端日志判断是否为未登录边界的预期行为。"),
    ]
    return "\n".join(
        [
            '<div class="diagnostic-panel">',
            "<h3>登录未确认的证据边界</h3>",
            '<div class="diagnostic-grid">',
            *(f'<div><span>{esc(label)}</span><strong>{esc(value)}</strong><p>{esc(note)}</p></div>' for label, value, note in rows),
            "</div>",
            "</div>",
        ]
    )


def render_access_policy_baseline(module: dict) -> str:
    visited = module.get("visited_pages") or []
    protected = [item for item in visited if page_judgement(item) == "受保护跳转"]
    if not protected:
        return ""
    examples = []
    for item in protected[:6]:
        url = str(item.get("url") or "")
        path = url.split("redirect=", 1)[-1] if "redirect=" in url else url
        examples.append(path.replace("%2F", "/"))
    return "\n".join(
        [
            '<div class="diagnostic-panel policy-panel">',
            "<h3>受保护页面是否异常：缺少角色权限基准</h3>",
            f'<p>本次观察到 {esc(len(protected))} 个入口重定向至登录页，示例：{esc("、".join(examples))}。这并不能单独证明页面故障，因为需要先确认 admin 账号对这些入口的预期访问策略。</p>',
            '<div class="policy-checklist">',
            '<span>需要补充：角色权限预期表</span>',
            '<span>需要补充：登录成功后的账号/角色标识</span>',
            '<span>需要补充：服务端授权日志</span>',
            "</div>",
            "</div>",
        ]
    )


def render_request_failure_closure(module: dict) -> str:
    request_failures = module.get("request_failures") or []
    abnormal = module.get("abnormal_responses") or []
    focus = [item for item in request_failures + abnormal if "auth/" in str(item) or "401" in str(item) or "ERR_ABORTED" in str(item)]
    if not focus:
        return ""
    possible_causes = [
        "浏览器跳转或页面卸载导致请求被取消",
        "前端代码主动中断旧请求",
        "未登录或会话过期边界下的预期 401",
        "认证接口真实失败或后端异常",
    ]
    needed = [
        "同一时间段服务端 access/error 日志",
        "auth/login 与 auth/refresh 的 HTTP 状态和响应体",
        "带重试的复测结果",
    ]
    return "\n".join(
        [
            '<div class="diagnostic-panel request-closure">',
            "<h3>请求失败与 401 的闭环状态</h3>",
            f'<p>当前仍处于“现象已发现，根因未闭环”阶段。报告捕获到 {esc(len(focus))} 条认证或请求中断相关信号，但浏览器侧证据无法单独区分导航取消、前端主动取消、会话边界和真实后端故障。</p>',
            '<div class="closure-columns">',
            "<div><span>可能原因</span><ul>",
            *(f"<li>{esc(item)}</li>" for item in possible_causes),
            "</ul></div>",
            "<div><span>闭环所需证据</span><ul>",
            *(f"<li>{esc(item)}</li>" for item in needed),
            "</ul></div>",
            "</div>",
            "</div>",
        ]
    )


def render_auth_signal_summary(module: dict) -> str:
    login = module.get("login") or {}
    visited = module.get("visited_pages") or []
    after_login = next((item for item in visited if item.get("label") == "after-login"), {})
    request_failures = module.get("request_failures") or []
    abnormal = module.get("abnormal_responses") or []
    signals = [
        ("表单提交", "已尝试" if after_login else "未记录", "存在 after-login 页面记录可作为已执行登录动作的间接证据。"),
        ("落地页面", after_login.get("url") or "未记录", after_login.get("title") or login.get("note") or "未记录"),
        ("成功标识", "未捕获" if login.get("status") != "success" else "已捕获", "账号名、角色、退出登录按钮等稳定信号仍需复核。"),
        ("请求中断", str(len(request_failures)), "需区分浏览器导航取消、前端主动取消和真实接口失败。"),
        ("异常响应", str(len(abnormal)), "重点关注 auth/refresh、401 和登录接口响应。"),
    ]
    return "\n".join(
        [
            '<div class="auth-signal-strip">',
            *(f'<div><span>{esc(label)}</span><strong>{esc(value)}</strong><small>{esc(note)}</small></div>' for label, value, note in signals),
            "</div>",
        ]
    )


def business_area_for_page(item: dict) -> str:
    url = str(item.get("url") or "")
    label = str(item.get("label") or "")
    if "redirect=%2Fcourses" in url or "/courses" in url:
        return "课程入口"
    if "redirect=%2Fclassrooms" in url or "/classrooms" in url:
        return "教室入口"
    if "redirect=%2Fpractice" in url or "/practice" in url:
        return "练习入口"
    if "redirect=%2Flabs" in url or "/labs" in url:
        return "实验入口"
    if "redirect=%2Fexam" in url or "/exam" in url:
        return "考试入口"
    if "redirect=%2Fresources" in url or "/resources" in url:
        return "资源入口"
    if "/certificate" in url:
        return "证书查询"
    if label == "after-login":
        return "登录提交后"
    if "/login" in url:
        return "登录页"
    return "公开首页"


def page_review_note(item: dict) -> str:
    judgement = page_judgement(item)
    if judgement == "正常可访问":
        return "浏览器可渲染，作为可用性正向证据。"
    if judgement == "登录未确认":
        return "仍需确认是否出现账号/角色/退出登录等稳定登录态信号。"
    if judgement == "受保护跳转":
        return "需对照角色权限预期，判断跳转是否正常。"
    if judgement == "登录页":
        return "用于核对登录表单与入口是否可见。"
    return "需结合截图复核。"


def finding_resolution_path(finding: dict) -> list[str]:
    title = str(finding.get("title") or "")
    target = str(finding.get("target") or "")
    if "管理员登录状态未确认" in title:
        return ["确认人工登录是否正常", "若人工正常则标为自动化能力边界", "优化巡检代理对账号/角色/退出入口的识别规则"]
    if "自动化登录态信号未确认" in title:
        return ["确认人工登录是否正常", "若人工正常则标为自动化能力边界", "优化巡检代理对账号/角色/退出入口的识别规则"]
    if "受保护页面重定向至登录页" in title:
        return ["补齐角色权限预期表", "用已确认登录态复测目标入口", "判断是正常保护跳转还是权限异常"]
    if "auth/refresh" in target or "401" in str(finding.get("technical_evidence") or ""):
        return ["查看服务端 auth/refresh 日志", "确认 401 是否未登录边界", "带重试验证刷新后会话是否延续"]
    if "请求失败" in title:
        return ["按 URL 聚合同类失败", "区分导航取消、前端取消和接口失败", "结合后端日志确认是否影响业务功能"]
    if "页面内容过短" in title:
        return ["对照浏览器截图", "确认是否为 SPA 首屏渲染", "若截图正常则降级为低可信提示"]
    return ["复核业务影响", "补充日志或截图证据", "确认是否进入修复闭环"]


def page_judgement(item: dict) -> str:
    label = str(item.get("label") or "")
    url = str(item.get("url") or "")
    text = str(item.get("text_excerpt") or "")
    if "login?redirect=" in url:
        return "受保护跳转"
    if label == "after-login" and ("欢迎登录" in text or "/login" in url):
        return "登录未确认"
    if "/login" in url:
        return "登录页"
    return "正常可访问"


def render_screenshot_index(module: dict, out_dir: Path | None = None) -> str:
    screenshots = browser_screenshot_files(module)
    if not screenshots:
        return ""
    visited = module.get("visited_pages") or []
    by_label = {str(item.get("label") or ""): item for item in visited if item.get("screenshot")}
    by_screenshot = {str(item.get("screenshot") or ""): item for item in visited if item.get("screenshot")}

    preferred = [
        (
            "after-login-confirmed",
            "登录后首页证据",
            "用于确认巡检代理在提交凭证后看到的页面状态；人工登录正常时，可辅助判断自动化登录态识别边界。",
        ),
        ("route-/", "公开首页渲染", "用于确认公开首页、导航和主要内容是否正常可见。"),
        ("route-/login", "登录入口页面", "用于确认登录表单、入口页面和账号密码输入区域是否可见。"),
        ("route-/certificate", "证书查询入口", "用于复核具体业务入口的页面渲染和异常提示是否清晰。"),
        ("route-/courses", "受保护业务入口", "用于确认课程等受保护入口在当前会话下的访问表现。"),
        ("route-/exam", "考试入口", "用于确认考试类入口是否跳转、阻断或渲染异常。"),
    ]
    selected: list[tuple[str, str, str]] = []
    used: set[str] = set()
    for label_key, label, note in preferred:
        item = by_label.get(label_key)
        filename = str(item.get("screenshot") or "") if item else ""
        if filename and filename in screenshots and filename not in used:
            selected.append((filename, label, note))
            used.add(filename)
        if len(selected) >= MAX_SCREENSHOT_GALLERY:
            break
    fallback_notes = {
        "entry-before-login.png": ("登录前首页", "用于确认公开首页是否正常渲染、导航与主要内容是否可见。"),
        "login-trigger-opened.png": ("登录入口打开后", "用于确认登录表单是否可见、账号密码输入入口是否可操作。"),
        "after-login.png": ("提交登录后", "用于复核是否仍停留在登录页，或是否出现管理员身份/退出登录等成功信号。"),
    }
    for filename in screenshots:
        if len(selected) >= MAX_SCREENSHOT_GALLERY:
            break
        if filename in used:
            continue
        basename = Path(filename).name
        if basename in fallback_notes:
            label, note = fallback_notes[basename]
        else:
            item = by_screenshot.get(filename) or {}
            label = business_area_for_page(item) if item else "页面截图"
            note = page_review_note(item) if item else "用于抽查页面渲染、跳转状态和异常提示。"
        selected.append((filename, label, note))
        used.add(filename)
    items = []
    for idx, (filename, label, note) in enumerate(selected, 1):
        image_src = filename
        if out_dir is not None:
            preferred_name = f"evidence-{idx:02d}-{safe_asset_stem(label, 'shot')}"
            image_src = best_effort_image_ref(filename, out_dir, "evidence-shot", preferred_name, HTML_ASSET_DIR)
        items.append(
            "\n".join(
                [
                    '<figure class="evidence-shot">',
                    f'<img src="{esc(image_src)}" alt="{esc(label)}">',
                    "<figcaption>",
                    f"<strong>{esc(label)}</strong>",
                    f"<span>{esc(note)}</span>",
                    "</figcaption>",
                    "</figure>",
                ]
            )
        )
    if not items:
        return ""
    return "\n".join(
        [
            '<div class="screenshot-index">',
            "<h3>哪些证据值得优先看</h3>",
            '<p class="fine">优先展示最能支撑结论的 4 张截图；完整截图文件统一保留在 <code>screenshots/</code>，HTML 展示图统一保留在 <code>html-assets/</code>。</p>',
            '<div class="screenshot-gallery">',
            *items,
            "</div>",
            "</div>",
        ]
    )


def render_evidence_file_index(report: dict) -> str:
    files: dict[str, list[str]] = {}
    for finding in report.get("priority_findings", []):
        for filename in finding.get("evidence_files") or []:
            files.setdefault(str(filename), []).append(str(finding.get("title") or "未命名问题"))
    items = []
    seen_evidence_titles: dict[str, int] = {}
    for filename, titles in list(files.items())[:MAX_EVIDENCE_FILES]:
        title_text = "；".join(dict.fromkeys(titles[:3]))
        duplicate_index = seen_evidence_titles.get(title_text, 0) + 1
        seen_evidence_titles[title_text] = duplicate_index
        if duplicate_index > 1:
            title_text = f"同类证据 #{duplicate_index}：{title_text}"
        items.append(f'<li><span>{esc(filename)}</span><p>{esc(title_text)}</p></li>')
    if not items:
        items.append('<li><span>无独立证据文件</span><p>本次发现主要来自结构化 HTTP / 浏览器状态记录；如需截图闭环，请在复测时补充人工截图或服务端日志。</p></li>')
    section_note = (
        f'为缩短正文，本节仅展示前 {esc(min(len(files), MAX_EVIDENCE_FILES))} 个证据文件索引；完整证据关系请查看结构化 JSON。'
        if files
        else "本次没有独立 evidence_files 记录，报告仍保留证据包清单，方便确认正式交付物与后续复测补证路径。"
    )
    return "\n".join(
        [
            '<section class="report-section evidence-file-index" id="evidence-files">',
            '<div class="section-kicker">证据索引</div>',
            "<h2>截图和证据文件对应哪些问题</h2>",
            f'<p class="section-brief">{section_note}</p>',
            '<div class="evidence-pack">',
            *(f'<div><span>{esc(label)}</span><strong>{esc(value)}</strong><p>{esc(note)}</p></div>' for label, value, note in evidence_pack_items(report)),
            "</div>",
            "<ul>",
            *items,
            "</ul>",
            "</section>",
        ]
    )


def browser_inspection_module(report: dict) -> dict | None:
    for module in report.get("module_reports", []):
        if module.get("report_type") == "browser-inspection":
            return module
    return None


def count_by_key(items: list[dict], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        value = str(item.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def overall_site_results(report: dict) -> list[dict]:
    sites = report.get("site_results") or []
    if sites:
        return sites
    return [
        {
            "index": idx,
            "slug": item.get("system_id", ""),
            "name": item.get("system_name", "未知站点"),
            "url": item.get("url", ""),
            "owner": item.get("owner", ""),
            "status": item.get("status", "unknown"),
            "score": item.get("score", 0),
            "findings": item.get("findings", 0),
            "quality_status": item.get("quality_status", "unknown"),
            "error": item.get("error", ""),
            "report": item.get("report", ""),
        }
        for idx, item in enumerate(report.get("systems", []), start=1)
    ]


def overall_batch_metrics(report: dict) -> dict:
    sites = overall_site_results(report)
    summary = report.get("summary") or {}
    scores = [int_value(item.get("score"), 0) for item in sites]
    return {
        "site_count": int_value((report.get("batch_metrics") or {}).get("site_count"), len(sites)),
        "average_score": int_value((report.get("batch_metrics") or {}).get("average_score"), int_value(report.get("score"), 0)),
        "lowest_score": int_value((report.get("batch_metrics") or {}).get("lowest_score"), min(scores, default=0)),
        "failed": int_value((report.get("batch_metrics") or {}).get("failed"), sum(1 for item in sites if item.get("error"))),
        "quality_failed": int_value(
            (report.get("batch_metrics") or {}).get("quality_failed"),
            sum(1 for item in sites if item.get("error") or item.get("quality_status") in {"failed", "not-run"}),
        ),
        "status_distribution": (report.get("batch_metrics") or {}).get("status_distribution") or summary,
    }


def overall_priority_sites(report: dict) -> list[dict]:
    configured = report.get("priority_sites") or []
    if configured:
        return configured
    sites = overall_site_results(report)
    return [
        item
        for item in sites
        if item.get("status") != "healthy" or item.get("error") or item.get("quality_status") in {"failed", "not-run"}
    ]


def overall_top_action(report: dict) -> str:
    priority_sites = overall_priority_sites(report)
    if priority_sites:
        first = priority_sites[0]
        reason = first.get("reason") or first.get("error") or f"{STATUS_LABELS.get(first.get('status'), first.get('status'))}状态"
        return f"优先复核“{first.get('name', '未命名站点')}”：{reason}"
    families = report.get("common_issue_families") or []
    if families:
        first = families[0]
        return f"优先处理共性问题“{first.get('title')}”，覆盖 {first.get('site_count', 0)} 个站点。"
    return "本批次未发现需要优先处置的站点，建议保留批次结果并纳入周期巡检。"


def site_report_link(site: dict) -> str:
    href = str(site.get("report") or "")
    if not href:
        return '<span class="muted">未生成</span>'
    return f'<a href="{esc(href)}">打开单站报告</a>'


def render_overall_batch_brief(report: dict) -> str:
    metrics = overall_batch_metrics(report)
    summary = metrics["status_distribution"]
    score = int_value(report.get("score"), metrics["average_score"])
    status = report.get("overall_status", "unknown")
    return "\n".join(
        [
            '<section class="report-section overall-batch-brief" id="overall-batch-brief">',
            '<div class="section-kicker">批次总览</div>',
            "<h2>批次总览与管理结论</h2>",
            f'<p class="section-brief">{esc(report.get("executive_summary", ""))}</p>',
            '<section class="metrics overview-metrics">',
            f'<div class="metric"><div class="value">{esc(metrics["site_count"])}</div><div class="label">巡检站点</div></div>',
            f'<div class="metric healthy-tone"><div class="value">{esc(summary.get("healthy", 0))}</div><div class="label">正常</div></div>',
            f'<div class="metric warning-tone"><div class="value">{esc(summary.get("warning", 0))}</div><div class="label">告警</div></div>',
            f'<div class="metric critical-tone"><div class="value">{esc(summary.get("critical", 0))}</div><div class="label">严重</div></div>',
            f'<div class="metric"><div class="value">{esc(metrics["average_score"])}</div><div class="label">平均评分</div></div>',
            f'<div class="metric warning-tone"><div class="value">{esc(metrics["quality_failed"])}</div><div class="label">质量/运行缺口</div></div>',
            "</section>",
            '<div class="decision-next">',
            f"<strong>管理判断：</strong><span>{esc(STATUS_LABELS.get(status, status))}，批次评分 {esc(score)} / 100。{esc(overall_top_action(report))}</span>",
            "</div>",
            "</section>",
        ]
    )


def render_overall_coverage_quality(report: dict) -> str:
    metrics = overall_batch_metrics(report)
    sites = overall_site_results(report)
    missing_reports = sum(1 for item in sites if not item.get("report"))
    return "\n".join(
        [
            '<section class="report-section overall-coverage-quality" id="overall-coverage-quality">',
            '<div class="section-kicker">覆盖质量</div>',
            "<h2>巡检覆盖与质量边界</h2>",
            '<p class="section-brief">总体报告只表达批次层面的覆盖质量和治理缺口；单站浏览器证据、截图和模块细节保留在各站点报告中。</p>',
            '<div class="overview-grid">',
            '<article class="overview-panel">',
            "<h3>覆盖范围</h3>",
            "<ul>",
            f"<li><strong>纳入站点</strong><span>{esc(metrics['site_count'])} 个。</span></li>",
            f"<li><strong>生成报告</strong><span>{esc(metrics['site_count'] - missing_reports)} 个站点有单站报告入口。</span></li>",
            f"<li><strong>最低评分</strong><span>{esc(metrics['lowest_score'])} / 100，用于定位批次短板。</span></li>",
            "</ul>",
            "</article>",
            '<article class="overview-panel">',
            "<h3>质量缺口</h3>",
            "<ul>",
            f"<li><strong>运行失败</strong><span>{esc(metrics['failed'])} 个站点。</span></li>",
            f"<li><strong>质量审计/未运行</strong><span>{esc(metrics['quality_failed'])} 个站点。</span></li>",
            f"<li><strong>未生成入口</strong><span>{esc(missing_reports)} 个站点。</span></li>",
            "</ul>",
            "</article>",
            "</div>",
            "</section>",
        ]
    )


def render_overall_health_distribution(report: dict) -> str:
    summary = overall_batch_metrics(report)["status_distribution"]
    total = int_value(summary.get("total_systems"), len(overall_site_results(report)))
    rows = [
        ("正常", "healthy", summary.get("healthy", 0), "可作为健康基线保留，不在总体报告中展开单站证据。"),
        ("告警", "warning", summary.get("warning", 0), "需要责任人复核，确认是否进入修复或观察。"),
        ("严重", "critical", summary.get("critical", 0), "应进入专项处置或应急修复。"),
        ("未知", "unknown", summary.get("unknown", 0), "优先补齐 URL、凭证、运行环境或质量审计。"),
    ]
    cards = [
        f'<article class="health-picture-card"><h3>{esc(label)}</h3><strong>{esc(count)} / {esc(total)}</strong><p>{esc(note)}</p></article>'
        for label, _, count, note in rows
    ]
    return "\n".join(
        [
            '<section class="report-section overall-health-distribution" id="overall-health-distribution">',
            '<div class="section-kicker">站点分布</div>',
            "<h2>站点健康分布</h2>",
            '<p class="section-brief">本节按站点状态呈现批次格局，帮助管理者判断本轮是个别站点问题，还是存在跨站共性风险。</p>',
            '<div class="health-picture-grid">',
            *cards,
            "</div>",
            "</section>",
        ]
    )


def render_overall_priority_sites(report: dict) -> str:
    sites = overall_priority_sites(report)
    if not sites:
        body = '<p class="empty">本批次没有形成需要优先处置的站点。</p>'
    else:
        rows = []
        for site in sites[:12]:
            rows.append(
                "<tr>"
                f"<td>{esc(site.get('index', '-'))}</td>"
                f"<td><strong>{esc(site.get('name', '未命名站点'))}</strong><br><span class=\"fine\">{esc(site.get('url') or '未提供 URL')}</span></td>"
                f"<td>{esc(site.get('owner') or '未指定')}</td>"
                f"<td>{status_badge(str(site.get('status') or 'unknown'))}</td>"
                f"<td>{esc(site.get('score', 0))}</td>"
                f"<td>{esc(site.get('findings', 0))}</td>"
                f"<td>{esc(site.get('reason') or site.get('error') or '需复核')}</td>"
                f"<td>{site_report_link(site)}</td>"
                "</tr>"
            )
        body = '<div class="table-wrap"><table><thead><tr><th>序号</th><th>站点</th><th>负责人</th><th>状态</th><th>评分</th><th>问题数</th><th>优先原因</th><th>报告</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>"
    return "\n".join(
        [
            '<section class="report-section overall-priority-sites" id="overall-priority-sites">',
            '<div class="section-kicker">优先处置</div>',
            "<h2>优先处置站点清单</h2>",
            '<p class="section-brief">只列非健康、运行失败或质量审计未通过的站点，便于直接分派复核和修复任务。</p>',
            body,
            "</section>",
        ]
    )


def render_overall_common_risks(report: dict) -> str:
    families = report.get("common_issue_families") or []
    if not families:
        body = '<p class="empty">本批次没有聚合出跨站共性风险。</p>'
    else:
        cards = []
        for family in families[:8]:
            sites = "、".join(family.get("sites") or []) or "未记录"
            owners = "、".join(family.get("owners") or []) or "按单站负责人分派"
            cards.append(
                '<article class="root-cause-card">'
                f'<span class="review-tag">{esc(family.get("classification", "批次共性风险"))}</span>'
                f"<h3>{esc(family.get('title', '未命名问题族'))}</h3>"
                f"<p>覆盖 {esc(family.get('site_count', 0))} 个站点、{esc(family.get('finding_count', 0))} 条发现；负责人：{esc(owners)}。</p>"
                f'<p class="fine"><b>涉及站点：</b>{esc(sites)}</p>'
                f'<p class="fine"><b>建议动作：</b>{esc(family.get("next_action") or "安排责任人复核并形成闭环。")}</p>'
                "</article>"
            )
        body = '<div class="root-cause-grid">' + "".join(cards) + "</div>"
    return "\n".join(
        [
            '<section class="report-section overall-common-risks" id="overall-common-risks">',
            '<div class="section-kicker">共性风险</div>',
            "<h2>共性风险与问题族</h2>",
            '<p class="section-brief">总体报告按问题族聚合跨站风险，不复制每个站点的原始证据；需要核对细节时进入单站报告。</p>',
            body,
            "</section>",
        ]
    )


def render_overall_site_matrix(report: dict) -> str:
    rows = []
    for site in overall_site_results(report):
        rows.append(
            "<tr>"
            f"<td>{esc(site.get('index', '-'))}</td>"
            f"<td><strong>{esc(site.get('name', '未命名站点'))}</strong><br><span class=\"fine\">{esc(site.get('url') or '未提供 URL')}</span></td>"
            f"<td>{esc(site.get('owner') or '未指定')}</td>"
            f"<td>{status_badge(str(site.get('status') or 'unknown'))}</td>"
            f"<td>{esc(site.get('score', 0))}</td>"
            f"<td>{esc(site.get('findings', 0))}</td>"
            f"<td>{esc(site.get('quality_status') or 'unknown')}</td>"
            f"<td>{esc(site.get('error') or '无')}</td>"
            f"<td>{site_report_link(site)}</td>"
            "</tr>"
        )
    body = '<p class="empty">本批次没有站点结果。</p>' if not rows else '<div class="table-wrap"><table><thead><tr><th>序号</th><th>站点</th><th>负责人</th><th>状态</th><th>评分</th><th>问题数</th><th>质量审计</th><th>运行错误</th><th>报告</th></tr></thead><tbody>' + "".join(rows) + "</tbody></table></div>"
    return "\n".join(
        [
            '<section class="report-section overall-site-matrix" id="overall-site-matrix">',
            '<div class="section-kicker">站点矩阵</div>',
            "<h2>全量站点矩阵</h2>",
            '<p class="section-brief">完整列出本轮所有站点的状态、评分、问题数量、质量审计结果和单站报告入口。</p>',
            body,
            "</section>",
        ]
    )


def render_overall_governance_plan(report: dict) -> str:
    metrics = overall_batch_metrics(report)
    return "\n".join(
        [
            '<section class="report-section overall-governance-plan" id="overall-governance-plan">',
            '<div class="section-kicker">复测治理</div>',
            "<h2>治理建议与复测计划</h2>",
            '<p class="section-brief">总体报告的后续动作应围绕批次治理，而不是逐站复述技术细节。</p>',
            '<div class="retest-timeline">',
            f"<div><span>T+0</span><p>保存批次首页、总体报告、{esc(metrics['site_count'])} 个站点结果和 batch-summary.json，作为本轮基线。</p></div>",
            "<div><span>T+1</span><p>优先补齐 unknown、运行失败和质量审计失败站点，确保下一轮批次覆盖完整。</p></div>",
            "<div><span>T+2</span><p>按共性风险问题族分派责任域，分别进入内容、接口、权限、部署或巡检代理优化闭环。</p></div>",
            "<div><span>T+3</span><p>复跑批次巡检，对比状态分布、平均分、最低分和优先站点是否收敛。</p></div>",
            "</div>",
            "</section>",
        ]
    )


def render_overall_delivery_index(report: dict) -> str:
    links = []
    for site in overall_site_results(report):
        href = str(site.get("report") or "")
        if href:
            links.append(f'<li><span>{esc(site.get("name", "未命名站点"))}</span><a href="{esc(href)}">打开单站报告</a></li>')
    if not links:
        links.append("<li><span>单站报告</span><p>本批次暂无可打开的单站报告入口。</p></li>")
    return "\n".join(
        [
            '<section class="report-section overall-delivery-index" id="overall-delivery-index">',
            '<div class="section-kicker">交付索引</div>',
            "<h2>交付索引与单站报告入口</h2>",
            '<p class="section-brief">对外发送时仍发送整个 delivery-batch 文件夹；总体报告只做批次汇总，单站证据从这里或批次首页进入。</p>',
            '<ul class="evidence-pack">',
            *links,
            "</ul>",
            "</section>",
        ]
    )


def render_multi_site_overall_body(report: dict, image_rel: str | None, guide_rel: str | None, out_dir: Path | None = None, guide_status: dict | None = None) -> str:
    sections = [
        ("overall-batch-brief", render_overall_batch_brief(report), True),
        ("overall-coverage-quality", render_overall_coverage_quality(report), False),
        ("overall-health-distribution", render_overall_health_distribution(report), False),
        ("overall-priority-sites", render_overall_priority_sites(report), False),
        ("overall-common-risks", render_overall_common_risks(report), False),
        ("overall-site-matrix", render_overall_site_matrix(report), False),
        ("overall-governance-plan", render_overall_governance_plan(report), False),
        ("overall-delivery-index", render_overall_delivery_index(report), False),
    ]
    return "\n".join(
        [
            render_guide_cover(report, guide_rel, guide_status),
            render_report_navigation(report),
            *(fold_report_section(fragment, section_id, open_by_default=open_by_default) for section_id, fragment, open_by_default in sections),
        ]
    )


def render_multi_site_overall_markdown(report: dict) -> str:
    metrics = overall_batch_metrics(report)
    summary = metrics["status_distribution"]
    generated_at = format_report_time(report.get("generated_at"))
    lines = [
        f"# {multi_site_report_title(report)}",
        "",
        f"- 整体状态：{STATUS_LABELS.get(report.get('overall_status'), report.get('overall_status'))}",
        f"- 批次评分：{report.get('score')} / 100",
        f"- 巡检站点：{metrics['site_count']}",
        f"- 平均评分：{metrics['average_score']} / 100",
        f"- 最低评分：{metrics['lowest_score']} / 100",
        f"- 生成时间：{generated_at}",
        "",
        report.get("executive_summary", ""),
        "",
        "## 巡检覆盖与质量边界",
        "",
        f"- 正常：{summary.get('healthy', 0)}",
        f"- 告警：{summary.get('warning', 0)}",
        f"- 严重：{summary.get('critical', 0)}",
        f"- 未知：{summary.get('unknown', 0)}",
        f"- 运行失败：{metrics['failed']}",
        f"- 质量审计/未运行：{metrics['quality_failed']}",
        "",
        "## 优先处置站点清单",
        "",
    ]
    priority_sites = overall_priority_sites(report)
    if not priority_sites:
        lines.append("本批次没有形成需要优先处置的站点。")
    for site in priority_sites:
        reason = site.get("reason") or site.get("error") or STATUS_LABELS.get(site.get("status"), site.get("status", "unknown"))
        report_link = site.get("report") or "未生成"
        lines.append(f"- {site.get('name')}｜{STATUS_LABELS.get(site.get('status'), site.get('status'))}｜{site.get('score')} 分｜{reason}｜{report_link}")
    lines.extend(["", "## 共性风险与问题族", ""])
    families = report.get("common_issue_families") or []
    if not families:
        lines.append("本批次没有聚合出跨站共性风险。")
    for family in families:
        sites = "、".join(family.get("sites") or []) or "未记录"
        lines.append(f"- {family.get('classification')}｜{family.get('title')}｜覆盖 {family.get('site_count', 0)} 个站点｜{sites}｜{family.get('next_action')}")
    lines.extend(["", "## 全量站点矩阵", ""])
    for site in overall_site_results(report):
        report_link = site.get("report") or "未生成"
        lines.append(
            f"- {site.get('index')}. {site.get('name')}｜{STATUS_LABELS.get(site.get('status'), site.get('status'))}｜"
            f"{site.get('score')} 分｜问题 {site.get('findings')}｜质量 {site.get('quality_status')}｜{report_link}"
        )
    lines.extend(
        [
            "",
            "## 治理建议与复测计划",
            "",
            "- T+0：保存批次首页、总体报告、单站报告和 batch-summary.json，作为本轮基线。",
            "- T+1：优先补齐 unknown、运行失败和质量审计失败站点。",
            "- T+2：按共性问题族分派责任域并进入闭环。",
            "- T+3：复跑批次巡检，对比状态分布、平均分、最低分和优先站点是否收敛。",
            "",
        ]
    )
    return "\n".join(lines)


def render_health_overview(report: dict) -> str:
    summary = report.get("summary", {})
    findings = report.get("priority_findings", [])
    modules = report.get("module_reports", [])
    clusters = clustered_findings(findings)
    browser = browser_inspection_module(report) or {}
    login = browser.get("login") or {}
    visited = browser.get("visited_pages") or []
    screenshots = browser_screenshot_files(browser)
    request_failures = browser.get("request_failures") or []
    abnormal_responses = browser.get("abnormal_responses") or []
    performance_text = browser_performance_summary(browser) if browser else "性能快照：未采集浏览器页面打开时间。"
    score = int(report.get("score") or 0)
    status = report.get("overall_status", "unknown")
    status_label = STATUS_LABELS.get(status, status)
    severity_counts = count_by_key(findings, "severity")
    priority_counts = count_by_key(findings, "priority")
    strength_counts = evidence_strength_counts(findings)
    picture = health_picture(report)
    health_items = health_baseline_items(picture)
    issue_focus_items = attention_items(picture)

    if score >= 85:
        score_note = "当前评分处于稳定区间。健康证据作为基线展示，正文只保留必要的巡检边界说明。"
    elif score >= 60:
        score_note = "当前评分处于告警区间。健康数据证明系统具备可访问证据，分析重点放在接口、权限基准或自动化识别边界。"
    else:
        score_note = "当前评分低于 60 分。报告仍先给出健康数据基线，但正文分析集中在真实故障、接口异常、权限基准差异和自动化巡检能力边界。"

    login_status = login.get("status", "unknown")
    if login_status == "success":
        login_text = "管理员登录已由自动化流程确认，后续页面覆盖可信度较高。"
    else:
        login_text = "管理员登录状态未被自动化流程完全确认；如果人工登录已验证正常，本项应归类为自动化/MCP 操控能力边界，并优先优化巡检代理的登录态识别与会话保持。"

    module_labels = [
        MODULE_LABELS.get(module.get("report_type"), module.get("report_type") or module.get("file") or "未知模块")
        for module in modules
    ]
    module_text = "、".join(module_labels) if module_labels else "暂无模块数据"

    top_clusters = clusters[:4]
    if top_clusters:
        issue_items = []
        for item in top_clusters:
            classification, _ = classify_finding(item)
            issue_items.append(
                f'<li><strong>{esc(item.get("title"))}</strong><span>{esc(classification)}，同类 {esc(item.get("_cluster_count", 1))} 条，严重度 {esc(item.get("severity", "unknown"))}</span></li>'
            )
        issue_html = "\n".join(issue_items)
    else:
        issue_html = '<li><strong>未发现优先问题</strong><span>本次巡检未形成需要优先跟进的问题簇。</span></li>'

    next_actions = [
        "先用人工已确认登录态复测，并把自动化未确认登录态的问题归入巡检代理识别与会话保持优化。",
        "对资源请求失败和异常 HTTP 响应按 URL 聚类排查，区分真实故障、鉴权拦截和浏览器中断噪声。",
        "用截图证据抽查关键页面，确认首页、登录后页面、功能入口和受保护页面是否符合业务预期。",
    ]
    if score >= 85:
        next_actions = [
            "保留本次巡检截图和 JSON 证据，作为后续对比基线。",
            "将核心页面加入固定巡检清单，保持周期性监测。",
            "继续关注响应时间、登录链路和关键接口状态变化。",
        ]

    parts = [
        '<section class="report-section health-overview" id="health-overview">',
        '<div class="section-kicker">健康总览</div>',
        '<div class="overview-head">',
        '<div>',
        f"<h2>整体健康画像：{esc(status_label)}，健康评分 {esc(score)} / 100</h2>",
        f'<p>{esc(score_note)} 本节同时展示健康和不健康数据：健康部分只保留基线证据，不展开冗长分析；需要关注的部分进入后续根因、优先事项和复测章节。</p>',
        "</div>",
        '<div class="overview-score-card">',
        '<span>当前评分</span>',
        f"<strong>{esc(score)}</strong>",
        "<small>/100</small>",
        "</div>",
        "</div>",
        '<section class="metrics overview-metrics">',
        f'<div class="metric healthy-tone"><div class="value">{picture["healthy_systems"]}</div><div class="label">健康系统</div></div>',
        f'<div class="metric warning-tone"><div class="value">{picture["warning_systems"]}</div><div class="label">告警系统</div></div>',
        f'<div class="metric critical-tone"><div class="value">{picture["critical_systems"]}</div><div class="label">严重系统</div></div>',
        f'<div class="metric healthy-tone"><div class="value">{picture["normal_pages"]}</div><div class="label">正常页面</div></div>',
        f'<div class="metric"><div class="value">{picture["screenshots"]}</div><div class="label">截图证据</div></div>',
        f'<div class="metric warning-tone"><div class="value">{picture["clusters"]}</div><div class="label">需关注问题簇</div></div>',
        "</section>",
        '<div class="health-picture-grid">',
        '<article class="health-picture-card health-baseline-card">',
        "<h3>健康数据基线</h3>",
        '<p>这些数据用于说明本次巡检看到了哪些正常证据，默认不展开分析。</p>',
        '<div class="compact-stat-list">',
        *(f'<div><span>{esc(name)}</span><strong>{esc(value)}</strong></div>' for name, value in health_items),
        "</div>",
        "</article>",
        '<article class="health-picture-card attention-card">',
        "<h3>不健康与需关注数据</h3>",
        '<p>以下项目才进入重点解释、根因归并和复测动作。</p>',
        '<div class="compact-stat-list">',
        *(f'<div><span>{esc(name)}</span><strong>{esc(value)}</strong></div>' for name, value in issue_focus_items),
        "</div>",
        "</article>",
        "</div>",
        '<div class="overview-grid">',
        '<article class="overview-panel">',
        '<h3>覆盖数据</h3>',
        "<ul>",
        f"<li><strong>检查对象</strong><span>{esc(summary.get('total_systems', 0))} 个系统，覆盖模块：{esc(module_text)}。</span></li>",
        f"<li><strong>健康证据</strong><span>正常页面 {esc(picture['normal_pages'])} 个、健康模块 {esc(picture['healthy_modules'])} 个、截图 {esc(picture['screenshots'])} 张。</span></li>",
        f"<li><strong>异常证据</strong><span>请求失败 {esc(picture['request_failures'])} 次、异常 HTTP 响应 {esc(picture['abnormal_responses'])} 个、需关注问题簇 {esc(picture['clusters'])} 个。</span></li>",
        f"<li><strong>性能快照</strong><span>{esc(performance_text)}</span></li>",
        "</ul>",
        "</article>",
        '<article class="overview-panel">',
        '<h3>分析边界</h3>',
        "<ul>",
        f'<li><strong>登录链路</strong><span>{esc(login_text)}</span></li>',
        '<li><strong>重要说明</strong><span>“登录状态未确认”表示巡检代理未捕获稳定登录态信号；人工登录正常时，这是自动化/MCP 操控能力边界，不是网站故障。</span></li>',
        f'<li><strong>问题等级</strong><span>严重度分布：critical {esc(severity_counts.get("critical", 0))}、high {esc(severity_counts.get("high", 0))}、medium {esc(severity_counts.get("medium", 0))}、low {esc(severity_counts.get("low", 0))}。</span></li>',
        f'<li><strong>证据强度</strong><span>已确认故障 {esc(strength_counts.get("已确认故障", 0))}、高可信风险 {esc(strength_counts.get("高可信风险", 0))}、自动化能力边界 {esc(strength_counts.get("自动化能力边界", 0))}、自动化识别不足 {esc(strength_counts.get("自动化识别不足", 0))}、需人工复核 {esc(strength_counts.get("需人工复核", 0))}。</span></li>',
        f'<li><strong>优先级</strong><span>P1 {esc(priority_counts.get("P1", 0))}、P2 {esc(priority_counts.get("P2", 0))}、P3 {esc(priority_counts.get("P3", 0))}、P4 {esc(priority_counts.get("P4", 0))}。</span></li>',
        "</ul>",
        "</article>",
        '<article class="overview-panel">',
        '<h3>不健康重点</h3>',
        "<ul>",
        issue_html,
        "</ul>",
        "</article>",
        '<article class="overview-panel action-panel">',
        '<h3>建议优先级</h3>',
        "<ol>",
        *(f"<li>{esc(action)}</li>" for action in next_actions),
        "</ol>",
        "</article>",
        "</div>",
        "</section>",
    ]
    return "\n".join(parts)


def render_html_guide_visual(report: dict, guide_status: dict | None = None) -> str:
    findings = clustered_findings(report.get("priority_findings", []) or [])
    picture = health_picture(report)
    modules = report.get("module_reports", []) or []
    systems = report.get("systems", []) or []
    status = STATUS_LABELS.get(report.get("overall_status"), report.get("overall_status", "未知"))
    score = int(report.get("score") or 0)
    priority_counts = count_by_key(report.get("priority_findings", []) or [], "priority")
    strength_counts = picture.get("strength_counts", {})
    module_text = (
        f"{len(modules)} 个模块已纳入巡检；完整模块名称见正文的巡检边界与系统矩阵。"
        if modules
        else "暂无模块报告。"
    )
    top = findings[0] if findings else {}
    top_title = top.get("title") or "未发现优先问题"
    steps = [
        ("巡检范围", f"{picture['total_systems']} 个系统 / {len(modules)} 个模块"),
        ("健康判定", f"{status} · {score}/100"),
        ("健康证据", f"正常页面 {picture['normal_pages']} 个，截图 {picture['screenshots']} 张"),
        ("需关注项", f"问题簇 {picture['clusters']} 个，请优先看不健康索引"),
        ("问题分层", f"P1 {priority_counts.get('P1', 0)} · P2 {priority_counts.get('P2', 0)} · P3 {priority_counts.get('P3', 0)}"),
        ("下一步动作", top_title),
    ]
    strength_items = [
        ("已确认故障", strength_counts.get("已确认故障", 0)),
        ("高可信风险", strength_counts.get("高可信风险", 0)),
        ("需人工复核", strength_counts.get("需人工复核", 0)),
        ("自动化边界", strength_counts.get("自动化能力边界", 0)),
    ]
    return "\n".join(
        [
            '<div class="html-guide-visual" role="img" aria-label="HTML 生成的报告文字导览架构图">',
            '<div class="html-guide-banner">',
            '<div><span>报告图文导览</span><strong>阅读路径与重点证据</strong></div>',
            "<p>本导览由巡检数据自动整理，用于快速理解检测范围、健康判断、证据强度和复核顺序；正文数据为准。</p>",
            "</div>",
            '<div class="html-guide-kpis">',
            f"<div><span>整体状态</span><strong>{esc(status)}</strong></div>",
            f"<div><span>健康评分</span><strong>{esc(score)} / 100</strong></div>",
            f"<div><span>系统覆盖</span><strong>{esc(picture['total_systems'])}</strong></div>",
            f"<div><span>需关注系统</span><strong>{esc(len(picture['attention_system_list']))}</strong></div>",
            "</div>",
            '<div class="html-guide-flow">',
            *(
                f'<div class="html-guide-step"><span>{idx:02d}</span><strong>{esc(label)}</strong><p>{esc(text)}</p></div>'
                for idx, (label, text) in enumerate(steps, 1)
            ),
            "</div>",
            '<div class="html-guide-bottom">',
            '<div class="html-guide-module">',
            "<span>模块覆盖</span>",
            f"<p>{esc(module_text)}</p>",
            "</div>",
            '<div class="html-guide-strength">',
            *(
                f"<div><span>{esc(label)}</span><strong>{esc(value)}</strong></div>"
                for label, value in strength_items
            ),
            "</div>",
            "</div>",
            "</div>",
        ]
    )


def render_guide_cover(report: dict, guide_rel: str | None, guide_status: dict | None = None) -> str:
    status = report.get("overall_status", "unknown")
    tone = STATUS_TONES.get(status, STATUS_TONES["unknown"])
    findings = report.get("priority_findings", [])
    score = int(report.get("score") or 0)
    generated_at = format_report_time(report.get("generated_at"))
    identity = report_identity(report)
    site_name = identity.get("site_name")
    site_url = identity.get("site_url")
    title = site_name if site_name and site_name != "网站健康状况" else "网站健康状况"
    report_type = "网站健康状况巡检报告"
    eyebrow = "管理平台网站健康巡检"
    lead = f"{tone} 首页导览用于快速理解巡检范围、健康判断、影响面和处理顺序；正文数据为准。"
    next_action = top_action(findings)
    reading_steps = '<ol><li>先看封面数据栏，确认正文实时评分和状态。</li><li>再读管理层摘录与检测员结论，理解本次是否已证明真实故障。</li><li>最后进入评分、浏览器证据和技术附录，复核关键证据。</li></ol>'
    if is_multi_site_overall(report):
        title = multi_site_report_title(report)
        report_type = "批量网站健康治理汇总报告"
        eyebrow = "多站点批次治理汇总"
        lead = f"{tone} 本报告用于批量判断站点健康分布、覆盖质量、共性风险和复测优先级；单站证据请进入对应站点报告。"
        next_action = overall_top_action(report)
        reading_steps = '<ol><li>先看批次总览，确认本轮覆盖多少站点、整体状态和平均评分。</li><li>再看优先站点与共性风险，决定责任分派和复测顺序。</li><li>最后通过交付索引进入单站报告核对截图、浏览器证据和模块细节。</li></ol>'

    if guide_rel:
        visual = f'<img class="guide-cover-image" alt="AI 生成的报告文字导览架构图" src="{esc(guide_rel)}">'
    else:
        visual = render_html_guide_visual(report, guide_status)

    return "\n".join(
        [
            '<section class="guide-cover" aria-labelledby="guide-cover-title">',
            '<div class="guide-cover-head">',
            '<div>',
            f'<div class="eyebrow">{esc(eyebrow)}</div>',
            f'<h1 id="guide-cover-title">{esc(title)}</h1>',
            f'<p class="report-type">{esc(report_type)}</p>',
            f'<p class="lead">{esc(lead)}</p>',
            "</div>",
            f'<p class="next-action">{esc(next_action)}</p>',
            "</div>",
            '<div class="guide-cover-meta">',
            f'<div><span>整体状态</span>{status_badge(status)}</div>',
            f'<div><span>健康评分</span><strong>{esc(score)} / 100</strong></div>',
            f'<div><span>报告口径</span><strong>{esc(report_scope_label(report))}</strong></div>',
            f'<div><span>生成时间</span><strong>{esc(generated_at)}</strong></div>',
            *( [f'<div><span>巡检网址</span><strong>{esc(site_url)}</strong></div>'] if site_url and not is_multi_site_overall(report) else [] ),
            "</div>",
            visual,
            '<div class="reading-path">',
            '<span>阅读路径</span>',
            reading_steps,
            "</div>",
            f'<p class="guide-footnote">导览仅用于阅读引导，正文数据为准：当前评分 {esc(score)} / 100，生成时间 {esc(generated_at)}。若 AI 图片内数据与正文不同，请以本页数据栏和后续正文为准。</p>',
            "</section>",
        ]
    )


def render_body(report: dict, image_rel: str | None, guide_rel: str | None, out_dir: Path | None = None, guide_status: dict | None = None) -> str:
    if is_multi_site_overall(report):
        return render_multi_site_overall_body(report, image_rel, guide_rel, out_dir, guide_status)
    findings = report.get("priority_findings", [])
    systems = report.get("systems", [])
    modules = report.get("module_reports", [])
    parts = [
        render_guide_cover(report, guide_rel, guide_status),
        render_report_navigation(report),
        render_executive_decision(report),
        render_handoff_summary(report),
    ]
    parts.extend(
        [
            render_health_overview(report),
            render_attention_index(report),
            render_risk_domain_map(report),
            render_inspection_scope(report),
            render_next_detection_checklist(report),
            fold_report_section(render_score_breakdown(report), "score-breakdown"),
            fold_report_section(render_browser_coverage(report, out_dir), "browser-coverage"),
            '<section class="report-section priority-section">',
            '<div class="section-kicker">优先事项</div>',
            "<h2>严重问题与优先处理项</h2>",
            '<p class="section-brief">本节按根因合并后的优先事项展示，不再逐条堆叠重复日志。默认收起，适合在需要安排负责人时展开。</p>',
        ]
    )
    clustered_attention = attention_clusters(findings)
    if findings:
        hidden_findings = max(0, len(clustered_attention) - MAX_PRIORITY_FINDINGS)
        if hidden_findings:
            parts.append(f'<p class="section-brief">为压缩报告长度，本节仅展开前 {esc(MAX_PRIORITY_FINDINGS)} 个优先问题簇；其余 {esc(hidden_findings)} 个问题簇保留在评分拆解、技术附录和 JSON 中。</p>')
        seen_classification_notes: dict[str, int] = {}
        recommendation_counts = collections.Counter(
            recommendation_line_for_finding(item, str(item.get("recommendation") or "").strip())
            for item in clustered_attention[:MAX_PRIORITY_FINDINGS]
        )
        impact_counts = collections.Counter(
            business_impact_for_finding(item)
            for item in clustered_attention[:MAX_PRIORITY_FINDINGS]
        )
        seen_recommendations: dict[str, int] = {}
        seen_impacts: dict[str, int] = {}
        for finding in clustered_attention[:MAX_PRIORITY_FINDINGS]:
            priority = str(finding.get("priority", "")).lower()
            cluster_count = int(finding.get("_cluster_count", 1) or 1)
            evidence = finding.get("_cluster_evidence") or finding.get("technical_evidence")
            impact = business_impact_for_finding(finding)
            impact_to_render = impact
            if impact and impact_counts.get(impact, 0) > 1:
                duplicate_impact_index = seen_impacts.get(impact, 0) + 1
                seen_impacts[impact] = duplicate_impact_index
                if duplicate_impact_index > 1:
                    impact_to_render = f"同类影响见上方；本项是第 {duplicate_impact_index} 个同类证据，聚焦 {impact_domain_for_finding(finding)} 的差异化复核。"
                else:
                    impact_to_render = f"{impact} 同类影响后续不再重复展开。"
            elif impact:
                seen_impacts[impact] = 1
            recommendation = str(finding.get("recommendation") or "").strip()
            recommendation = recommendation_line_for_finding(finding, recommendation)
            evidence_text = evidence_line_for_finding(finding, evidence)
            classification, classification_note = classify_finding(finding)
            classification_note = classification_note_for_finding(finding, classification_note)
            note_to_render = classification_note
            duplicate_note_index = seen_classification_notes.get(classification_note, 0)
            if duplicate_note_index:
                note_to_render = f"同类证据口径见上方；本项聚焦 {impact_domain_for_finding(finding)} 的差异化影响和下一证据 #{duplicate_note_index + 1}。"
            else:
                note_to_render = classification_note
            seen_classification_notes[classification_note] = duplicate_note_index + 1
            recommendation_to_render = recommendation
            if recommendation and recommendation_counts.get(recommendation, 0) > 1:
                duplicate_recommendation_index = seen_recommendations.get(recommendation, 0) + 1
                seen_recommendations[recommendation] = duplicate_recommendation_index
                if duplicate_recommendation_index > 1:
                    recommendation_to_render = f"同类建议见上方；本项是第 {duplicate_recommendation_index} 个同类证据，聚焦 {impact_domain_for_finding(finding)} 的差异化复核口径。"
                else:
                    recommendation_to_render = f"{recommendation} 同类问题后续不再重复展开。"
            elif recommendation:
                seen_recommendations[recommendation] = 1
            recommendation_html = f'<p class="fine"><b>建议：</b>{esc(recommendation_to_render)}</p>' if recommendation_to_render else ""
            parts.extend(
                [
                    f'<article class="finding {esc(priority)}">',
                    '<div class="finding-head">',
                    f'<span class="priority">{esc(finding.get("priority"))}</span>',
                    f'<h3>{esc(finding.get("title"))}</h3>',
                    "</div>",
                    '<div class="finding-meta-strip">',
                    f'<span>{esc(classification)}</span>',
                    f'<span>{esc(owner_role_for_finding(finding))}</span>',
                    f'<span>{esc(impact_domain_for_finding(finding))}</span>',
                    "</div>",
                    f'<p class="fine">同类发现 {esc(cluster_count)} 次，已按问题簇合并展示。</p>' if cluster_count > 1 else "",
                    f'<p>{esc(impact_to_render)}</p>',
                    f'<p class="fine"><b>证据口径：</b>{esc(note_to_render)}</p>',
                    '<ol class="resolution-path">',
                    *(f'<li>{esc(step)}</li>' for step in finding_resolution_path(finding)),
                    "</ol>",
                    recommendation_html,
                    f'<p class="fine"><b>下一证据：</b>{esc(next_evidence_for_finding(finding))}</p>',
                    f'<p class="fine"><b>证据：</b><code>{esc(evidence_text)}</code></p>',
                    "</article>",
                ]
            )
    else:
        parts.append('<p class="empty">本次巡检未发现需要优先处理的问题。</p>')
    parts.append("</section>")

    priority_section_start = next((idx for idx in range(len(parts) - 1, -1, -1) if 'class="report-section priority-section"' in parts[idx]), None)
    if priority_section_start is not None:
        priority_fragment = "\n".join(parts[priority_section_start:])
        parts = parts[:priority_section_start]
        parts.append(fold_report_section(priority_fragment, "priority-findings"))

    parts.append(fold_report_section(render_root_cause_map(report), "root-cause-map"))
    parts.append(fold_report_section(render_system_health_matrix(systems, findings), "system-health"))
    parts.append(fold_report_section(render_module_details(modules), "module-evidence"))
    parts.append(fold_report_section(render_evidence_file_index(report), "evidence-files"))
    parts.append(fold_report_section(render_retest_runbook(report), "retest-runbook"))
    parts.append(fold_report_section(render_term_notes(), "term-notes"))
    parts.append(fold_report_section(render_technical_appendix(report), "tech-appendix"))
    return "\n".join(parts)


def render_markdown(report: dict) -> str:
    if is_multi_site_overall(report):
        return render_multi_site_overall_markdown(report)
    findings = report.get("priority_findings", [])
    picture = health_picture(report)
    browser = browser_inspection_module(report) or {}
    generated_at = format_report_time(report.get("generated_at"))
    lines = [
        "# 网站健康状况检测报告",
        "",
        "## 图文导览",
        "",
        "- HTML 报告首屏提供图文导览；未生成 AI 图片时使用可离线打开的 HTML 导览，用于快速理解巡检范围、健康判断、影响面和处理顺序；正文数据为准。",
        f"- 下一步：{top_action(findings)}",
        "",
        f"- 整体状态：{STATUS_LABELS.get(report.get('overall_status'), report.get('overall_status'))}",
        f"- 健康评分：{report.get('score')} / 100",
        f"- 生成时间：{generated_at}",
        "",
        report.get("executive_summary", ""),
        "",
        "## 整体健康画像",
        "",
        "健康数据用于说明本次巡检看到的正常证据；重点分析集中在不健康、需复核、自动化能力边界和风险项。",
        "",
    ]
    for label, value in health_baseline_items(picture):
        lines.append(f"- {label}：{value}")
    for label, value in attention_items(picture):
        lines.append(f"- {label}：{value}")
    lines.extend(
        [
            "",
            "## 性能快照",
            "",
            browser_performance_summary(browser),
        ]
    )
    metrics = browser_performance_metrics(browser)
    if metrics:
        lines.extend(
            [
                f"- 平均打开时间：{format_ms(metrics.get('avg_open_time_ms'))}",
                f"- 最慢页面：{format_ms(metrics.get('max_open_time_ms'))}",
                f"- 慢页面数：{metrics.get('slow_pages', '未统计')}",
                f"- 平均 TTFB：{format_ms(metrics.get('avg_ttfb_ms'))}",
            ]
        )
    lines.extend(
        [
            "",
            "## 不健康重点索引",
            "",
        ]
    )
    attention_rows = attention_summary(report)[:8]
    if not attention_rows:
        lines.append("本次巡检没有形成需要重点分析的不健康项。")
    for row in attention_rows:
        lines.append(f"- {row['classification']}｜{row['title']}｜{row['domain']}｜下一证据：{row['next_evidence']}")
    lines.extend(
        [
            "",
        "## 优先问题",
        ]
    )
    if not findings:
        lines.append("本次巡检未发现需要优先处理的问题。")
    for finding in attention_clusters(findings):
        lines.extend(
            [
                f"- {finding.get('priority')} {finding.get('title')}",
                f"  影响：{finding.get('business_impact')}",
                f"  建议：{finding.get('recommendation')}",
            ]
        )
    return "\n".join(lines) + "\n"


def run_optional(command: list[str]) -> bool:
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.stdout.strip():
        print(scrub_runtime_text(result.stdout.strip()))
    if result.returncode != 0:
        message = result.stderr.strip().splitlines()[-1:] or result.stdout.strip().splitlines()[-1:]
        if message:
            print(f"Skipped optional step: {scrub_runtime_text(message[0])}", file=sys.stderr)
    return result.returncode == 0


def scrub_runtime_text(value: str) -> str:
    text = str(value or "")
    replacements = [
        (re.compile(r"sk-[A-Za-z0-9_-]{12,}"), "[REDACTED_OPENAI_KEY]"),
        (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9_./+=-]{12,}"), r"\1[REDACTED_TOKEN]"),
        (re.compile(r"(?i)((?:api[_-]?key|token|secret|password|passwd|pwd)\s*[:=]\s*['\"]?)[^'\"\s;,]{6,}"), r"\1[REDACTED]"),
    ]
    for pattern, replacement in replacements:
        text = pattern.sub(replacement, text)
    return text


def record_optional_error(out_dir: Path, filename: str, command: list[str], result: subprocess.CompletedProcess[str]) -> None:
    lines = [
        "可选步骤执行失败",
        "",
        "命令：" + scrub_runtime_text(" ".join(command)),
        "退出码：" + str(result.returncode),
        "",
        "标准输出：",
        scrub_runtime_text(result.stdout.strip()) or "无",
        "",
        "标准错误：",
        scrub_runtime_text(result.stderr.strip()) or "无",
    ]
    (out_dir / filename).write_text("\n".join(lines) + "\n", encoding="utf-8-sig")


def run_optional_with_error_file(command: list[str], out_dir: Path, error_filename: str) -> bool:
    result = subprocess.run(command, check=False, capture_output=True, text=True)
    if result.stdout.strip():
        print(scrub_runtime_text(result.stdout.strip()))
    if result.returncode != 0:
        record_optional_error(out_dir, error_filename, command, result)
        message = result.stderr.strip().splitlines()[-1:] or result.stdout.strip().splitlines()[-1:]
        if message:
            print(f"Skipped optional step: {scrub_runtime_text(message[0])}", file=sys.stderr)
    return result.returncode == 0


def last_error_message(path: Path) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    for line in reversed([item.strip() for item in text.splitlines() if item.strip()]):
        if line.startswith("stderr:") or line.startswith("stdout:"):
            continue
        return line[:240]
    return text[:240]


def archive_nonfinal_html_reports(out_dir: Path) -> list[Path]:
    """Move legacy draft HTML reports out of the run root to avoid misdelivery."""
    archived: list[Path] = []
    archive_dir = out_dir / "_archived-nonfinal-html"
    for item in sorted(out_dir.glob("final-*-health-report.html")):
        if item.name == "final-report.html" or not item.is_file():
            continue
        archive_dir.mkdir(parents=True, exist_ok=True)
        target = archive_dir / item.name
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            index = 2
            while True:
                candidate = archive_dir / f"{stem}-{index}{suffix}"
                if not candidate.exists():
                    target = candidate
                    break
                index += 1
        item.replace(target)
        archived.append(target)
    return archived


def file_artifact(path: Path) -> dict:
    return {
        "path": str(path),
        "exists": path.exists(),
        "bytes": path.stat().st_size if path.exists() and path.is_file() else 0,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() and path.is_file() else "",
    }


def directory_artifact(path: Path) -> dict:
    files = sorted(item for item in path.glob("*") if item.is_file()) if path.exists() and path.is_dir() else []
    return {
        "path": str(path),
        "exists": path.exists() and path.is_dir(),
        "files": len(files),
        "bytes": sum(item.stat().st_size for item in files),
    }


def delivery_manifest_payload(out_dir: Path, report_path: Path, archived_htmls: list[Path]) -> dict:
    root_nonfinal_html = sorted(
        item for item in out_dir.glob("final-*-health-report.html") if item.name != "final-report.html"
    )
    delivery_dir = out_dir / DELIVERY_DIR
    artifacts = {
        "official_html": out_dir / "final-report.html",
        "pdf_report": out_dir / "final-report.pdf",
        "delivery_html": delivery_dir / "final-report.html",
        "delivery_pdf_report": delivery_dir / "final-report.pdf",
        "structured_json": report_path,
        "delivery_structured_json": delivery_dir / "final-report.json",
        "markdown_summary": out_dir / "final-report.md",
        "delivery_markdown_summary": delivery_dir / "final-report.md",
        "quality_audit": out_dir / "quality-audit.md",
        "delivery_quality_audit": delivery_dir / "quality-audit.md",
        "quality_audit_json": out_dir / "quality-audit.json",
        "delivery_quality_audit_json": delivery_dir / "quality-audit.json",
        "score_audit": out_dir / "score-audit.md",
        "delivery_score_audit": delivery_dir / "score-audit.md",
        "score_audit_json": out_dir / "score-audit.json",
        "delivery_score_audit_json": delivery_dir / "score-audit.json",
        "ai_guide_status": out_dir / GUIDE_STATUS_FILE,
        "delivery_ai_guide_status": delivery_dir / GUIDE_STATUS_FILE,
        "ai_guide_image": out_dir / HTML_ASSET_DIR / "guide-cover.png",
        "html_assets_dir": out_dir / HTML_ASSET_DIR,
        "screenshots_dir": out_dir / SCREENSHOT_ASSET_DIR,
        "delivery_dir": delivery_dir,
        "delivery_html_assets_dir": delivery_dir / HTML_ASSET_DIR,
        "delivery_screenshots_dir": delivery_dir / SCREENSHOT_ASSET_DIR,
    }
    artifact_payload = {
        key: directory_artifact(path) if key.endswith("_dir") else file_artifact(path)
        for key, path in artifacts.items()
    }
    checks = {
        "official_html_exists": artifact_payload["official_html"]["exists"],
        "official_pdf_exists": artifact_payload["pdf_report"]["exists"] and artifact_payload["pdf_report"]["bytes"] > 0,
        "delivery_html_exists": artifact_payload["delivery_html"]["exists"],
        "delivery_pdf_exists": artifact_payload["delivery_pdf_report"]["exists"] and artifact_payload["delivery_pdf_report"]["bytes"] > 0,
        "structured_json_exists": artifact_payload["structured_json"]["exists"],
        "markdown_summary_exists": artifact_payload["markdown_summary"]["exists"],
        "quality_audit_exists": artifact_payload["quality_audit"]["exists"],
        "quality_audit_json_exists": artifact_payload["quality_audit_json"]["exists"],
        "score_audit_exists": artifact_payload["score_audit"]["exists"],
        "score_audit_json_exists": artifact_payload["score_audit_json"]["exists"],
        "root_has_no_nonfinal_html": not root_nonfinal_html,
        "guide_image_available": artifact_payload["ai_guide_image"]["exists"],
        "guide_status_available": artifact_payload["ai_guide_status"]["exists"],
        "html_assets_available": artifact_payload["html_assets_dir"]["exists"],
        "screenshots_available": artifact_payload["screenshots_dir"]["exists"],
        "delivery_package_available": artifact_payload["delivery_dir"]["exists"],
    }
    quality_gate_status = "missing"
    quality_gate_failed_checks: list[str] = []
    if artifacts["quality_audit_json"].exists():
        try:
            quality_audit = read_json(artifacts["quality_audit_json"])
            quality_gate_status = str(quality_audit.get("status") or "missing")
            quality_gate_failed_checks = list(quality_audit.get("failed_checks") or [])
        except Exception:
            quality_gate_status = "invalid"
            quality_gate_failed_checks = ["quality_audit_json_invalid"]
    score_gate_status = "missing"
    score_gate_reasons: list[str] = []
    score_review: dict = {}
    if artifacts["score_audit_json"].exists():
        try:
            score_audit = read_json(artifacts["score_audit_json"])
            score_gate_status = str(score_audit.get("status") or "missing")
            score_gate_reasons = list(score_audit.get("blocking_reasons") or [])
        except Exception:
            score_gate_status = "invalid"
            score_gate_reasons = ["score_audit_json_invalid"]
    if report_path.exists():
        try:
            report_payload = read_json(report_path)
            score_review = dict(report_payload.get("score_review") or {})
        except Exception:
            score_review = {}
    package_complete = all(
        checks[key]
        for key in [
            "official_html_exists",
            "official_pdf_exists",
            "delivery_html_exists",
            "delivery_pdf_exists",
            "structured_json_exists",
            "markdown_summary_exists",
            "root_has_no_nonfinal_html",
            "guide_status_available",
            "html_assets_available",
            "screenshots_available",
            "delivery_package_available",
        ]
    )
    ready_to_deliver = bool(
        package_complete
        and checks["quality_audit_exists"]
        and checks["quality_audit_json_exists"]
        and checks["score_audit_exists"]
        and checks["score_audit_json_exists"]
        and (score_gate_status == "pass" or bool(score_review.get("approved")))
        and quality_gate_status != "fail"
        and quality_gate_status not in {"missing", "invalid"}
    )
    return {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_dir": str(out_dir),
        "official_entry": str(artifacts["official_html"]),
        "official_delivery_dir": str(delivery_dir),
        "official_delivery_entry": str(artifacts["delivery_html"]),
        "do_not_deliver_patterns": ["final-*-health-report.html"],
        "package_complete": package_complete,
        "quality_gate_status": quality_gate_status,
        "quality_gate_failed_checks": quality_gate_failed_checks,
        "score_gate_status": score_gate_status,
        "score_gate_blocking_reasons": score_gate_reasons,
        "score_review": score_review,
        "ready_to_deliver": ready_to_deliver,
        "counts": {
            "artifacts_present": sum(1 for item in artifact_payload.values() if item["exists"]),
            "root_nonfinal_html": len(root_nonfinal_html),
            "archived_nonfinal_html": len(archived_htmls),
            "html_assets": artifact_payload["html_assets_dir"].get("files", 0),
            "screenshots": artifact_payload["screenshots_dir"].get("files", 0),
        },
        "checks": checks,
        "artifacts": artifact_payload,
        "archived_nonfinal_html": [
            {
                "path": str(path),
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0,
            }
            for path in archived_htmls
        ],
        "delivery_rule": "Share the whole delivery/ folder. Open delivery/final-report.html. HTML images are relative refs under html-assets/; complete screenshot evidence is under screenshots/.",
    }


def write_delivery_manifest(out_dir: Path, report_path: Path, archived_htmls: list[Path]) -> dict[str, Path]:
    payload = delivery_manifest_payload(out_dir, report_path, archived_htmls)
    json_path = out_dir / "delivery-manifest.json"
    md_path = out_dir / "delivery-manifest.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = [
        "# 报告交付清单",
        "",
        "## 交付状态",
        "",
        f"- 状态：{'可以交付' if payload['ready_to_deliver'] else '暂缓交付'}",
        f"- 生成时间：`{payload['generated_at']}`",
        f"- 根目录非正式 HTML：{payload['counts']['root_nonfinal_html']} 个",
        f"- 已归档非正式 HTML：{payload['counts']['archived_nonfinal_html']} 个",
        f"- HTML 图片：{payload['counts']['html_assets']} 个",
        f"- 截图证据：{payload['counts']['screenshots']} 个",
        f"- 评分审计：{payload.get('score_gate_status', 'missing')}",
        "",
        "## 正式入口",
        "",
        f"- 交付包：`{payload['official_delivery_dir']}`",
        f"- HTML：`{payload['official_delivery_entry']}`",
        "- 规则：发送整个 `delivery/` 文件夹；不要只发送单个 HTML，也不要交付 `final-*-health-report.html`。",
        "- 图片目录：HTML 正文只引用 `html-assets/`；完整截图证据归档在 `screenshots/`。",
        "",
        "## 关键检查",
        "",
        *(f"- {key}：{'通过' if value else '未通过'}" for key, value in payload["checks"].items()),
        f"- score_gate_status：{payload.get('score_gate_status', 'missing')}",
        f"- score_review_approved：{'通过' if payload.get('score_review', {}).get('approved') else '未通过'}",
        "",
        "## 交付文件",
        "",
    ]
    for key, item in payload["artifacts"].items():
        status = "存在" if item["exists"] else "未生成"
        digest = f"，sha256 `{item['sha256'][:12]}`" if item.get("sha256") else ""
        rows.append(f"- {key}：`{item['path']}`（{status}，{item['bytes']} bytes{digest}）")
    rows.extend(["", "## 已归档的非正式 HTML", ""])
    if payload["archived_nonfinal_html"]:
        for item in payload["archived_nonfinal_html"]:
            status = "存在" if item["exists"] else "缺失"
            rows.append(f"- `{item['path']}`（{status}）")
    else:
        rows.append("- 无。")
    rows.append("")
    md_path.write_text("\n".join(rows), encoding="utf-8-sig")
    return {"json": json_path, "markdown": md_path}


def refresh_delivery_manifest(out_dir: Path, report_path: Path, archived_htmls: list[Path]) -> dict[str, Path]:
    return write_delivery_manifest(out_dir, report_path, archived_htmls)


def render_pdf_report(html_path: Path, pdf_path: Path) -> None:
    chrome_candidates = [
        os.getenv("CHROME_PATH", ""),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    error_path = pdf_path.parent / "pdf-generation-error.txt"
    if error_path.exists():
        error_path.unlink()
    browser = next((Path(item) for item in chrome_candidates if item and Path(item).exists()), None)
    if browser:
        command = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            f"--print-to-pdf={pdf_path}",
            html_path.resolve().as_uri(),
        ]
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        if result.returncode == 0 and pdf_path.exists() and pdf_path.stat().st_size > 0:
            return
        details = [
            f"PDF generation failed with {browser}.",
            f"exit_code={result.returncode}",
            "[stdout]",
            scrub_sensitive_text(result.stdout or ""),
            "[stderr]",
            scrub_sensitive_text(result.stderr or ""),
        ]
    else:
        details = [
            "PDF generation failed because Chrome or Edge was not found.",
            "Install Chrome/Edge, set CHROME_PATH, or rerun with --no-pdf for debug-only output.",
        ]
    error_path.write_text("\n".join(details).strip() + "\n", encoding="utf-8-sig")
    raise SystemExit("PDF generation failed; see pdf-generation-error.txt")


def effective_guide_mode(args: argparse.Namespace) -> str:
    if args.skip_ai_guide_image:
        return "html-guide"
    return args.guide_mode


def score_audit_status(out_dir: Path) -> dict:
    path = out_dir / "score-audit.json"
    if not path.exists():
        return {"status": "missing", "blocking_reasons": ["score_audit_missing"]}
    try:
        return read_json(path)
    except Exception:
        return {"status": "invalid", "blocking_reasons": ["score_audit_invalid"]}


def enforce_score_review_gate(report: dict, out_dir: Path, args: argparse.Namespace) -> dict:
    score = int(report.get("score") or 0)
    audit = score_audit_status(out_dir)
    status = str(audit.get("status") or "missing")
    reasons = list(audit.get("blocking_reasons") or [])
    approved = bool(getattr(args, "score_review_approved", False))
    note = str(getattr(args, "score_review_note", "") or "").strip()
    if approved and not note:
        raise SystemExit("--score-review-note is required when --score-review-approved is used")
    threshold = int(getattr(args, "score_audit_threshold", 60) or 60)
    needs_gate = score < threshold or status in {"blocked", "invalid"} or (status != "missing" and bool(reasons))
    if score < threshold and status == "missing":
        needs_gate = True
    approval_allowed = approved and status == "blocked" and set(reasons).issubset({"low_score_requires_review"})
    if approved and status in {"missing", "invalid"}:
        raise SystemExit("score review approval requires a valid score-audit.json; run audit_score_reasonableness.py first.")
    if approved and reasons and not set(reasons).issubset({"low_score_requires_review"}):
        raise SystemExit(
            "score review approval cannot bypass score mismatch or suspected duplicate penalties; resolve score-audit findings first."
        )
    if needs_gate and status != "pass" and not approval_allowed:
        raise SystemExit(
            "score-audit gate blocked rendering; run audit_score_reasonableness.py and resolve duplicate scoring, "
            "or pass --score-review-approved with --score-review-note after manual review."
        )
    review = {
        "score_audit_status": status,
        "blocking_reasons": reasons,
        "approved": approved,
        "note": note,
        "score_audit_json": str(out_dir / "score-audit.json"),
        "score_audit_markdown": str(out_dir / "score-audit.md"),
    }
    report["score_review"] = review
    return review


def resolve_guide_image(
    *,
    guide_mode: str,
    out_dir: Path,
    report_path: Path,
    guide_path: Path,
) -> tuple[dict, str | None]:
    if guide_mode == "html-guide":
        return (
            write_guide_status(
                out_dir,
                "html_guide_selected",
                "user_selected_html_guide",
                "用户已明确选择不提供图片接口 API Key，首页使用 HTML 图文导览。",
            ),
            None,
        )

    if guide_mode == "reuse-existing":
        valid, reason = valid_ai_guide_image(guide_path, out_dir)
        if not valid:
            status = write_guide_status(
                out_dir,
                "needs_user_choice",
                reason,
                "未找到可复用的有效 AI 导览图。请先询问用户：提供 API Key 生成图片，或改用 HTML 图文导览。",
            )
            raise SystemExit(status["message"])
        status = write_guide_status(
            out_dir,
            "reused_existing",
            "existing_ai_guide_image",
            "已按用户选择复用运行目录中已有的 AI 导览图。",
        )
        guide_rel = ensure_report_image_ref(str(guide_path), out_dir, "ai-report-guide", "guide-cover")
        return status, guide_rel

    if guide_mode == "auto" and not has_usable_openai_api_key():
        status = write_guide_status(
            out_dir,
            "needs_user_choice",
            "OPENAI_API_KEY is not set",
            "当前没有可用图片接口 API Key。请先询问用户：提供 API Key 生成 AI 导览图，或选择 HTML 图文导览。",
        )
        raise SystemExit(status["message"])

    if guide_mode == "ai-image" and not has_usable_openai_api_key():
        status = write_guide_status(
            out_dir,
            "missing_api_key",
            "OPENAI_API_KEY is not set",
            "用户选择了 AI 导览图，但当前没有可用图片接口 API Key。请要求用户提供 API Key 后重试。",
        )
        raise SystemExit(status["message"])

    if not ensure_openai_python_package(out_dir):
        status = write_guide_status(
            out_dir,
            "missing_dependency",
            "openai Python package is not installed and automatic installation failed",
            "用户已选择 AI 导览图并提供 API Key，但当前 Python 环境缺少 openai 包且自动安装失败。请先修复运行环境后重试，不要直接改用 HTML 导览。",
            "ai-report-guide-dependency-error.txt",
        )
        raise SystemExit(status["message"])

    error_path = out_dir / "ai-report-guide-error.txt"
    if error_path.exists():
        error_path.unlink()
    guide_cmd = [
        sys.executable,
        str(SCRIPT_DIR / "generate_ai_report_guide_image.py"),
        "--report",
        str(report_path),
        "--out",
        str(out_dir),
    ]
    if os.getenv("OPENAI_BASE_URL"):
        guide_cmd.extend(["--base-url", os.getenv("OPENAI_BASE_URL", "")])
    ok = run_optional_with_error_file(guide_cmd, out_dir, "ai-report-guide-error.txt")
    if ok and guide_path.exists():
        status = write_guide_status(
            out_dir,
            "generated",
            "image_generated",
            "AI 导览图生成成功，首页使用 ai-report-guide.png。",
        )
        guide_rel = ensure_report_image_ref(str(guide_path), out_dir, "ai-report-guide", "guide-cover")
        return status, guide_rel

    status = write_guide_status(
        out_dir,
        "failed",
        last_error_message(out_dir / "ai-report-guide-error.txt") or "image generation failed",
        "AI 导览图调用失败，首页使用 HTML 图文导览兜底。",
        "ai-report-guide-error.txt",
    )
    return status, None


def main() -> None:
    parser = argparse.ArgumentParser(description="Render final HTML and Markdown report.")
    parser.add_argument("--report", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--guide-mode",
        choices=["auto", "ai-image", "html-guide", "reuse-existing"],
        default="auto",
        help="Choose guide generation behavior. auto requires a usable API key or exits for user choice.",
    )
    parser.add_argument("--skip-ai-guide-image", action="store_true", help="Compatibility alias for --guide-mode html-guide.")
    parser.add_argument("--no-load-env", action="store_true")
    parser.add_argument("--no-pdf", action="store_true")
    parser.add_argument("--score-audit-threshold", type=int, default=60)
    parser.add_argument("--score-review-approved", action="store_true")
    parser.add_argument("--score-review-note", default="")
    args = parser.parse_args()
    if not args.no_load_env:
        load_project_env(ROOT)
    out_dir = ensure_dir(args.out)
    report_path = Path(args.report)
    cleanup_asset_dirs(out_dir)
    report = read_json(report_path)
    report = normalize_report_for_render(report)
    report = normalize_image_refs_for_portable_html(report, out_dir)
    enforce_score_review_gate(report, out_dir, args)
    screenshot_assets = collect_screenshot_assets(report, out_dir)
    write_json(report_path, report)

    run_optional([sys.executable, str(SCRIPT_DIR / "generate_summary_image.py"), "--report", str(report_path), "--out", str(out_dir)])
    image_path = out_dir / "executive-summary.png"
    image_rel = ensure_report_image_ref(str(image_path), out_dir, "executive-summary", "executive-summary") if image_path.exists() else None
    report.setdefault("artifacts", {})["executive_summary_image"] = str(image_path)

    guide_path = out_dir / "ai-report-guide.png"
    guide_status, guide_rel = resolve_guide_image(
        guide_mode=effective_guide_mode(args),
        out_dir=out_dir,
        report_path=report_path,
        guide_path=guide_path,
    )
    if guide_status.get("status") in {"generated", "reused_existing"} and guide_path.exists():
        report.setdefault("artifacts", {})["ai_report_guide_image"] = str(guide_path)

    doc_title = report_title(report)
    template = (ASSETS / "report-template.html").read_text(encoding="utf-8")
    html_doc = template.replace("{{TITLE}}", doc_title).replace("{{BODY}}", render_body(report, image_rel, guide_rel, out_dir, guide_status))
    html_path = out_dir / "final-report.html"
    md_path = out_dir / "final-report.md"
    html_path.write_text(html_doc, encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    if not args.no_pdf:
        render_pdf_report(html_path, out_dir / "final-report.pdf")
    archived_htmls = archive_nonfinal_html_reports(out_dir)
    if archived_htmls:
        report.setdefault("artifacts", {})["archived_nonfinal_html"] = [str(item) for item in archived_htmls]
    manifest_paths = write_delivery_manifest(out_dir, report_path, archived_htmls)
    report.setdefault("artifacts", {})["delivery_manifest"] = str(manifest_paths["json"])
    report.setdefault("artifacts", {})["html_assets_dir"] = str(out_dir / HTML_ASSET_DIR)
    report.setdefault("artifacts", {})["screenshots_dir"] = str(out_dir / SCREENSHOT_ASSET_DIR)
    report.setdefault("artifacts", {})["screenshot_assets"] = [str(item) for item in screenshot_assets]
    write_json(report_path, report)
    sync_delivery_package(out_dir)
    manifest_paths = refresh_delivery_manifest(out_dir, report_path, archived_htmls)
    sync_delivery_package(out_dir)
    if archived_htmls:
        print("Archived non-final HTML drafts: " + ", ".join(item.name for item in archived_htmls))
    print(out_dir / DELIVERY_DIR / "final-report.html")


if __name__ == "__main__":
    main()
