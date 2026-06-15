from __future__ import annotations

import argparse
import base64
import os
import re
from datetime import datetime
from pathlib import Path

from health_common import ensure_dir, read_json
from env_utils import load_project_env


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent


STATUS_LABELS = {
    "healthy": "正常",
    "warning": "告警",
    "critical": "严重",
    "unknown": "未知",
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

PLACEHOLDER_API_KEYS = {
    "",
    "sk-" + "your-key-here",
    "<openai-api-key>",
    "your-api-key",
    "your_openai_api_key",
    "replace-me",
}


def has_usable_openai_api_key(value: str | None = None) -> bool:
    key = (os.getenv("OPENAI_API_KEY") if value is None else value) or ""
    normalized = key.strip()
    if normalized.lower() in PLACEHOLDER_API_KEYS:
        return False
    if normalized.startswith("<") and normalized.endswith(">"):
        return False
    return bool(re.fullmatch(r"sk-[A-Za-z0-9_-]{20,}", normalized))


def _priority_counts(findings: list[dict]) -> dict[str, int]:
    counts = {"P1": 0, "P2": 0, "P3": 0, "P4": 0}
    for finding in findings:
        priority = str(finding.get("priority") or "").upper()
        if priority in counts:
            counts[priority] += 1
    return counts


def _redact_prompt_text(value: object, *, fallback: str, max_chars: int = 42) -> str:
    text = str(value or "").strip() or fallback
    text = re.sub(r"sk-[A-Za-z0-9_-]{10,}", "[已隐藏密钥]", text)
    text = re.sub(
        r"(?i)\b(api[_-]?key|authorization|cookie|token|password|secret)\b\s*[:=]\s*[^;\s，,]+",
        r"\1=[已隐藏]",
        text,
    )
    text = re.sub(r"https?://[^\s，,；;]+", "[URL已隐藏]", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


def _report_site_name(report: dict) -> str:
    identity = report.get("report_identity") or {}
    candidates = [
        identity.get("site_name"),
        identity.get("title"),
        report.get("site_name"),
        report.get("name"),
    ]
    for system in report.get("systems") or []:
        candidates.extend([system.get("name"), system.get("system_name"), system.get("id")])
    for candidate in candidates:
        value = _redact_prompt_text(candidate, fallback="", max_chars=32)
        if value:
            return value
    return "本次巡检站点"


def _module_names(modules: list[dict]) -> str:
    names: list[str] = []
    for module in modules:
        name = MODULE_LABELS.get(module.get("report_type"), str(module.get("report_type") or "").strip())
        if name and name not in names:
            names.append(name)
    return "、".join(names) or "暂无模块报告"


def _browser_performance_snapshot(modules: list[dict]) -> str:
    for module in modules:
        metrics = module.get("metrics") or {}
        if module.get("report_type") not in {"browser-inspection", "browser-inspection-report.json"} and not metrics:
            continue
        parts: list[str] = []
        avg_open = metrics.get("avg_open_time_ms")
        slow_pages = metrics.get("slow_pages")
        ttfb = metrics.get("avg_ttfb_ms") or metrics.get("max_ttfb_ms")
        if avg_open is not None:
            parts.append(f"平均打开时间 {avg_open}ms")
        if slow_pages is not None:
            parts.append(f"慢页面 {slow_pages}")
        if ttfb is not None:
            parts.append(f"TTFB {ttfb}ms")
        if parts:
            return " · ".join(parts)
    return "平均打开时间、慢页面数与 TTFB 以正文实时数据为准"


def _inspection_time(report: dict) -> str:
    raw = str(report.get("generated_at") or report.get("inspection_time") or report.get("created_at") or "").strip()
    if not raw:
        return "以报告生成时间为准"
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
        return parsed.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        match = re.search(r"(\d{4}-\d{2}-\d{2})[T\s]+(\d{2}:\d{2})", raw)
        if match:
            return f"{match.group(1)} {match.group(2)}"
    return _redact_prompt_text(raw, fallback="以报告生成时间为准", max_chars=24)


def _status_distribution_text(distribution: dict) -> str:
    return (
        f"正常 {distribution.get('healthy', 0)} · "
        f"告警 {distribution.get('warning', 0)} · "
        f"严重 {distribution.get('critical', 0)} · "
        f"未知 {distribution.get('unknown', 0)}"
    )


def _priority_site_names(report: dict, *, max_items: int = 4) -> str:
    sites = report.get("priority_sites") or []
    if not sites:
        sites = [
            site
            for site in report.get("site_results") or []
            if site.get("status") in {"critical", "warning", "unknown"} or site.get("error")
        ]
    names = [
        _redact_prompt_text(site.get("name") or site.get("site_name") or site.get("slug"), fallback="未命名站点", max_chars=14)
        for site in sites[:max_items]
    ]
    return "、".join(name for name in names if name) or "暂无优先处置站点"


def _overall_subject(report: dict, site_count: int | None = None, *, max_names: int = 3) -> str:
    sites = report.get("site_results") or report.get("systems") or []
    names: list[str] = []
    for site in sites:
        name = _redact_prompt_text(
            site.get("name") or site.get("site_name") or site.get("system_name") or site.get("slug") or site.get("id"),
            fallback="",
            max_chars=14,
        )
        if name and name not in names:
            names.append(name)
        if len(names) >= max_names:
            break
    total = site_count if site_count is not None else len(sites)
    if names and total > len(names):
        return f"{'、'.join(names)}等{total}个站点"
    if names:
        return "、".join(names)
    if total:
        return f"{total}个站点"
    return "本批次站点"


def _common_issue_family_text(report: dict, *, max_items: int = 3) -> str:
    families = []
    for family in (report.get("common_issue_families") or [])[:max_items]:
        title = _redact_prompt_text(family.get("title"), fallback="未命名问题族", max_chars=18)
        site_count = family.get("site_count") or family.get("count") or 0
        families.append(f"{title}（{site_count}站）")
    return "、".join(families) or "暂无共性问题族"


def _overall_top_action(report: dict) -> str:
    priority_sites = _priority_site_names(report, max_items=2)
    families = _common_issue_family_text(report, max_items=2)
    if priority_sites != "暂无优先处置站点":
        return f"先处理 {priority_sites}，同步复核 {families}"
    if families != "暂无共性问题族":
        return f"围绕 {families} 建立批次整改任务"
    return "保持批次巡检节奏，按站点矩阵安排复测"


def build_overall_prompt(report: dict) -> str:
    summary = report.get("summary") or {}
    metrics = report.get("batch_metrics") or {}
    distribution = metrics.get("status_distribution") or summary
    findings = report.get("priority_findings") or []
    counts = _priority_counts(findings)
    status = STATUS_LABELS.get(report.get("overall_status"), report.get("overall_status", "未知"))
    site_count = metrics.get("site_count", summary.get("total_systems", len(report.get("site_results") or [])))
    average_score = metrics.get("average_score", report.get("score", 0))
    lowest_score = metrics.get("lowest_score", 0)
    failed = metrics.get("failed", summary.get("unknown", 0))
    quality_failed = metrics.get("quality_failed", 0)
    subject = _overall_subject(report, site_count)
    inspection_time = _inspection_time(report)
    priority_sites = _priority_site_names(report)
    families = _common_issue_family_text(report)
    top_action = _redact_prompt_text(_overall_top_action(report), fallback="按批次治理计划推进复测", max_chars=54)

    return f"""
Use case: batch governance guide infographic for a Chinese multi-site website health inspection overall report.
Asset type: opening AI 导览图 for a 多站点网站健康巡检总体报告. Generate a real raster image, not HTML, not SVG, not Mermaid.

Audience and job:
面向管理平台管理员和批次治理负责人，帮助他们在打开总体报告第一页时理解本批次的治理态势：哪些站点优先处理、哪些问题跨站复现、覆盖质量是否完整、如何跳转到单站报告入口并安排复测。导览图不是单网站诊断图，也不是单站浏览器证据长分析；它应像一张正式“批次治理驾驶舱 + 站点矩阵地图”。

Report type distinction:
这是 {subject} 的总报告 / 批次总体报告，采用 N+1 交付模式：一份整体总报告 + 多份单网站报告。总报告只做聚合治理、站点健康分布、优先处置站点、共性风险与问题族、全量站点矩阵、复测治理和交付索引；单站证据详情应通过单站报告入口查看。

Visual direction:
16:9 landscape, polished Chinese management-report infographic. Use a clean warm-white or light paper background, ink-blue primary accents, restrained amber/red/green/gray status colors, thin connectors, compact data cards, small line icons, and a clear hierarchy. The composition should read as:
1. 批次总览
2. 覆盖质量
3. 站点健康分布
4. 优先处置站点
5. 共性风险与问题族
6. 全量站点矩阵
7. 复测治理
8. 交付索引 / 单站报告入口
Add one central “批次治理态势” focal panel and one bottom “delivery-batch 交付包” strip.

Text to include exactly, with large readable Chinese typography:
标题：{subject}健康巡检总体报告导览
巡检对象：{subject}
监测时间：{inspection_time}
模式：N+1 批次治理
路径：批次总览 → 覆盖质量 → 健康分布 → 优先站点 → 共性风险 → 站点矩阵 → 复测治理 → 交付索引
整体状态：{status}
批次站点数：{site_count}
平均评分：{average_score}/100
最低评分：{lowest_score}/100
失败/未知站点：{failed}
质量门禁异常：{quality_failed}
站点健康分布：{_status_distribution_text(distribution)}
优先处置：{priority_sites}
共性问题：{families}
问题分层：P1 {counts["P1"]} · P2 {counts["P2"]} · P3 {counts["P3"]} · P4 {counts["P4"]}
下一步：{top_action}
交付入口：delivery-batch/index.html 与 overall/final-report.html
单站报告入口：sites/<slug>/delivery/final-report.html

Design constraints:
Keep all Chinese text concise, large, and legible. Prefer batch summary cards, status distribution bars, site matrix tiles, issue-family chips, governance arrows, and delivery index badges over dense paragraphs. Make clear that this image summarizes a batch, not a single website.

Hard exclusions:
Do not show raw URLs, API keys, passwords, tokens, cookies, authorization headers, stack traces, raw logs, code snippets, CSS selectors, fake browser chrome, terminal windows, Mermaid syntax, watermarks, logos, random English filler, neon cyber dashboard styling, tiny unreadable Chinese text, or single-site browser evidence long analysis.
""".strip()


def build_single_site_prompt(report: dict) -> str:
    summary = report.get("summary", {})
    findings = report.get("priority_findings", [])
    modules = report.get("module_reports", [])
    systems = report.get("systems", [])
    counts = _priority_counts(findings)
    status = STATUS_LABELS.get(report.get("overall_status"), report.get("overall_status", "未知"))
    score = report.get("score", 0)
    affected = sum(1 for system in systems if system.get("status") in {"warning", "critical"})
    module_names = _module_names(modules)
    site_name = _report_site_name(report)
    inspection_time = _inspection_time(report)
    performance_snapshot = _browser_performance_snapshot(modules)
    top_finding = findings[0] if findings else {}
    top_title = _redact_prompt_text(top_finding.get("title"), fallback="未发现优先问题", max_chars=34)
    top_impact = _redact_prompt_text(top_finding.get("business_impact"), fallback="影响范围尚未确认", max_chars=42)
    top_recommendation = _redact_prompt_text(
        top_finding.get("recommendation"),
        fallback="保持常规巡检、证据复核和闭环复测",
        max_chars=42,
    )

    return f"""
Use case: executive guide infographic for a Chinese website health inspection report.
Asset type: opening AI 导览图 for a formal HTML/PDF management report. Generate a real raster image, not HTML, not SVG, not Mermaid.

Audience and job:
面向管理平台管理员，帮助他们在打开报告第一页时快速理解本次网站健康巡检的阅读路径、健康画像、证据链和复测闭环。导览图不是扫描日志，也不是炫技海报；它应像一张正式报告首页的“管理驾驶舱 + 阅读地图”。

Skill core capabilities to visualize:
巡检入口：Excel 资源清单标准巡检、临时 URL 快速巡检、URL + 管理员凭证深度浏览。
检查能力：内容完整性审查、管理员浏览器实测、主机与微服务健康检查、受控页面发现。
报告方法：根因归并、健康评分、风险分层、不健康索引、证据链、责任域、处理建议、复测时间线。
正式交付：HTML/PDF/Markdown/JSON 报告与 delivery 证据包。

Visual direction:
16:9 landscape, polished Chinese management-report infographic. Use a clean warm-white or light paper background, ink-blue primary accents, restrained amber/red/green status colors, thin connectors, compact data cards, small line icons, and a clear hierarchy. The composition should read left-to-right as:
1. 巡检范围
2. 健康判定
3. 影响面
4. 不健康索引
5. 模块证据
6. 下一步动作 / 复测
Add one central “站点健康画像” focal panel and one bottom “证据包与正式交付” strip.

Text to include exactly, with large readable Chinese typography:
标题：网站健康巡检总报告导览
站点：{site_name}
监测时间：{inspection_time}
路径：巡检范围 → 健康判定 → 影响面 → 不健康索引 → 模块证据 → 复测闭环
整体状态：{status}
健康评分：{score}/100
系统总数：{summary.get("total_systems", 0)}
需关注系统：{affected}
优先问题：{len(findings)}
问题分层：P1 {counts["P1"]} · P2 {counts["P2"]} · P3 {counts["P3"]} · P4 {counts["P4"]}
模块覆盖：{module_names}
性能快照：{performance_snapshot}
优先动作：{top_title}
影响口径：{top_impact}
处理建议：{top_recommendation}

Design constraints:
Keep all Chinese text concise, large, and legible. Prefer cards, process arrows, evidence badges, risk chips, and simple icons over dense paragraphs. Make the image suitable for the first viewport of a formal inspection report and for PDF printing.

Hard exclusions:
Do not include URLs, API keys, passwords, tokens, cookies, authorization headers, stack traces, raw logs, code snippets, CSS selectors, fake browser chrome, terminal windows, Mermaid syntax, watermarks, logos, random English filler, neon cyber dashboard styling, or tiny unreadable Chinese text.
""".strip()


def build_prompt(report: dict) -> str:
    if report.get("report_kind") == "multi-site-overall":
        return build_overall_prompt(report)
    return build_single_site_prompt(report)


def generate_image(report: dict, out_path: Path, *, model: str, size: str, quality: str, base_url: str | None = None) -> Path:
    if not has_usable_openai_api_key():
        raise RuntimeError("OPENAI_API_KEY is not set; cannot call GPT image generation.")

    try:
        from openai import OpenAI
    except Exception as exc:
        raise RuntimeError("The openai Python package is required to call GPT image generation.") from exc

    out_path.parent.mkdir(parents=True, exist_ok=True)
    client_kwargs = {}
    effective_base_url = base_url or os.getenv("OPENAI_BASE_URL")
    if effective_base_url:
        client_kwargs["base_url"] = effective_base_url
    client = OpenAI(**client_kwargs)
    result = client.images.generate(
        model=model,
        prompt=build_prompt(report),
        size=size,
        quality=quality,
        output_format="png",
    )
    out_path.write_bytes(base64.b64decode(result.data[0].b64_json))
    return out_path


def main() -> None:
    load_project_env(ROOT)
    parser = argparse.ArgumentParser(description="Generate a GPT image guide for the final website health report.")
    parser.add_argument("--report", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--model", default=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2"))
    parser.add_argument("--size", default=os.getenv("OPENAI_IMAGE_SIZE", "2048x1152"))
    parser.add_argument("--quality", default=os.getenv("OPENAI_IMAGE_QUALITY", "high"))
    parser.add_argument("--base-url")
    args = parser.parse_args()

    out_dir = ensure_dir(args.out)
    report = read_json(Path(args.report))
    image_path = out_dir / "ai-report-guide.png"
    generate_image(report, image_path, model=args.model, size=args.size, quality=args.quality, base_url=args.base_url)
    print(image_path)


if __name__ == "__main__":
    main()
