from __future__ import annotations

import argparse
import re
from pathlib import Path

from health_common import now_iso, read_json, write_json
from scoring_model import (
    clustered_findings,
    finding_cluster_key,
    health_status_from_score_and_findings,
    root_cause_penalty,
    score_and_status_from_findings,
    score_from_finding_clusters,
)


REPORT_FILES = [
    "content-report.json",
    "browser-inspection-report.json",
    "function-report.json",
    "host-report.json",
]


def has_garbled_placeholder(value) -> bool:
    text = str(value or "")
    return "\ufffd" in text or "???" in text or "？？？" in text or bool(re.search(r"[?？]{4,}", text))


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
    finding["severity"] = "low"
    finding["priority"] = "P4"
    finding["confidence"] = "automation-boundary"


def normalize_garbled_findings(findings: list[dict], reports: list[dict]) -> list[dict]:
    for finding in findings:
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
    for report in reports:
        for finding in report.get("findings", []) or []:
            normalize_spa_text_check_finding(finding)
    return findings


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


def dedupe_findings(findings: list[dict]) -> list[dict]:
    merged = {}
    for finding in findings:
        key = (
            finding.get("system_id"),
            finding.get("target"),
            finding.get("title", "").replace(" 无法访问", "").replace(" 执行失败", ""),
        )
        if key not in merged:
            merged[key] = finding
        else:
            existing = merged[key]
            existing["technical_evidence"] = f"{existing.get('technical_evidence')}; {finding.get('technical_evidence')}"
            existing["evidence_files"] = list({*(existing.get("evidence_files") or []), *(finding.get("evidence_files") or [])})
    return list(merged.values())


def normalize_automation_boundaries(findings: list[dict], reports: list[dict]) -> list[dict]:
    """Backfill the newer evidence boundary fields for older browser reports."""
    browser_login_unknown = False
    for report in reports:
        if report.get("report_type") != "browser-inspection":
            continue
        login = report.get("login") or {}
        browser_login_unknown = browser_login_unknown or login.get("status") != "success"

    has_login_unconfirmed = any(
        "管理员登录状态未确认" in str(item.get("title") or "")
        or "自动化登录态信号未确认" in str(item.get("title") or "")
        for item in findings
    )
    if not browser_login_unknown and not has_login_unconfirmed:
        return findings

    for finding in findings:
        title = str(finding.get("title") or "")
        evidence = str(finding.get("technical_evidence") or "")
        if "管理员登录状态未确认" in title or "自动化登录态信号未确认" in title:
            finding["title"] = "自动化登录态信号未确认"
            finding["severity"] = "low"
            finding["priority"] = "P4"
            finding["confidence"] = "automation-boundary"
            finding["business_impact"] = (
                "不证明网站登录故障，只说明巡检代理未能稳定识别登录态；人工登录正常时，应作为自动化巡检能力边界处理。"
            )
            finding["recommendation"] = (
                "若人工登录已验证正常，将本项归为 AI/MCP 浏览器操控与登录态识别能力边界，并优化巡检代理的登录态识别、会话保持和账号角色判断。"
            )
            if "不等同于人工登录失败" not in evidence:
                finding["technical_evidence"] = (
                    f"{evidence}; automation_login_status=unknown; 该项不等同于人工登录失败，人工登录正常时属于自动化/MCP 能力边界。"
                ).strip("; ")
        elif "受保护页面重定向至登录页" in title and "automation_login_status=" not in evidence:
            finding["severity"] = "low"
            finding["priority"] = "P4"
            finding["confidence"] = "automation-boundary"
            finding["technical_evidence"] = f"automation_login_status=unknown; {evidence}"
            finding["business_impact"] = (
                "发生在自动化登录态未确认之后，更可能反映巡检代理未保持有效会话或缺少角色权限基准；不能单独证明目标页面不可用。"
            )
            finding["recommendation"] = (
                "先使用人工已确认登录态复测该入口；若人工访问正常，应将本项归类为自动化会话保持边界，而非网站页面故障。"
            )
    return findings


def overall_status(findings: list[dict], reports: list[dict]) -> str:
    score = score_from_finding_clusters(findings, unknown_penalty=0 if reports else 20)
    return health_status_from_score_and_findings(score, findings, has_reports=bool(reports))


def system_status(system_id: str, findings: list[dict], reports: list[dict]) -> str:
    system_findings = [finding for finding in findings if finding.get("system_id") == system_id]
    if not system_findings:
        return "healthy"
    score, status, _reasons = score_and_status_from_findings(system_findings, has_reports=bool(reports))
    return status


def executive_summary(status: str, score: int, findings: list[dict], system_count: int) -> str:
    if not findings:
        return f"本次巡检覆盖 {system_count} 个系统，整体状态正常，健康评分 {score}/100。"
    top_clusters = []
    seen = set()
    for finding in clustered_findings(findings):
        title, key = finding_cluster_key(finding)
        seen_key = (finding.get("system_id"), key, tuple(finding.get("_cluster_targets") or []))
        if seen_key in seen:
            continue
        seen.add(seen_key)
        top_clusters.append(title or finding.get("title", "未命名问题"))
        if len(top_clusters) >= 3:
            break
    titles = "；".join(top_clusters)
    if status == "critical":
        prefix = "本次巡检发现需要立即关注的严重风险"
    elif status == "warning":
        prefix = "本次巡检发现若干需要跟进的告警"
    else:
        prefix = "本次巡检整体可用"
    return f"{prefix}，健康评分 {score}/100。重点问题：{titles}。"


def merge(input_dir: str | Path) -> dict:
    base = Path(input_dir)
    reports = []
    findings = []
    systems_map = {}
    for filename in REPORT_FILES:
        path = base / filename
        if not path.exists():
            continue
        report = scrub_garbled_values(read_json(path))
        reports.append({"file": filename, **report})
        findings.extend(report.get("findings", []))
        for system in report.get("systems", []):
            sid = system.get("system_id")
            if not sid:
                continue
            systems_map.setdefault(sid, {"system_id": sid, "system_name": system.get("system_name"), "modules": {}, "findings": 0})
            systems_map[sid]["modules"][report.get("report_type", filename)] = system
            systems_map[sid]["findings"] += int(system.get("findings", 0))
    findings = normalize_garbled_findings(dedupe_findings(findings), reports)
    findings = normalize_automation_boundaries(findings, reports)
    findings.sort(key=lambda item: {"P1": 1, "P2": 2, "P3": 3, "P4": 4}.get(item.get("priority"), 9))
    score, status, _status_reasons = score_and_status_from_findings(findings, unknown_penalty=0 if reports else 20, has_reports=bool(reports))
    systems = list(systems_map.values())
    for system in systems:
        system["status"] = system_status(system["system_id"], findings, reports)
    summary_counts = {
        "total_systems": len(systems),
        "healthy": sum(1 for s in systems if s.get("status") == "healthy"),
        "warning": sum(1 for s in systems if s.get("status") == "warning"),
        "critical": sum(1 for s in systems if s.get("status") == "critical"),
        "unknown": 0,
    }
    return {
        "generated_at": now_iso(),
        "overall_status": status,
        "score": score,
        "executive_summary": executive_summary(status, score, findings, len(systems)),
        "summary": summary_counts,
        "systems": systems,
        "priority_findings": findings,
        "module_reports": reports,
        "artifacts": {},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge module reports into final report JSON.")
    parser.add_argument("--in", dest="input_dir", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    final = merge(args.input_dir)
    write_json(args.out, final)
    print(args.out)


if __name__ == "__main__":
    main()
