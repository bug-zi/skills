from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from health_common import ensure_dir, read_json, write_json
from scoring_model import (
    clustered_findings,
    health_status_from_score_and_findings,
    normalized_endpoint,
    root_cause_identity,
    root_cause_penalty,
    score_from_finding_clusters,
    status_reasons_from_score_and_findings,
)


DEFAULT_THRESHOLD = 60


def text(value) -> str:
    return str(value or "").strip()


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9._:-]+", "-", value.lower()).strip("-")


def loose_target_family(target: str) -> str:
    endpoint = normalized_endpoint(target)
    endpoint = re.sub(r"/:id(?=/|$)", "/:any", endpoint)
    endpoint = re.sub(r"([._-])\[hash\](?=\.|$)", r"\1:anyhash", endpoint)
    return endpoint


def loose_duplicate_key(finding: dict) -> tuple[str, str, str]:
    system_id, kind, _target_key, label = root_cause_identity(finding)
    category = slug(text(finding.get("cluster_key") or finding.get("category") or finding.get("finding_type") or kind))
    title = slug(text(finding.get("_cluster_label") or finding.get("title") or label))
    semantic = category or kind or title
    target_family = loose_target_family(text(finding.get("target")))
    if not target_family or target_family == "/":
        target_family = ""
    return system_id, semantic, target_family


def score_unknown_penalty(report: dict) -> int:
    if report.get("module_reports") or report.get("priority_findings"):
        return 0
    return 20


def recompute_score(report: dict) -> int:
    return score_from_finding_clusters(report.get("priority_findings", []), unknown_penalty=score_unknown_penalty(report))


def recompute_status(report: dict, score: int) -> tuple[str, list[str]]:
    has_reports = bool(report.get("module_reports") or report.get("priority_findings"))
    findings = report.get("priority_findings", []) or []
    status = health_status_from_score_and_findings(score, findings, has_reports=has_reports)
    reasons = status_reasons_from_score_and_findings(score, findings, has_reports=has_reports)
    return status, reasons


def penalty_rows(report: dict) -> list[dict]:
    rows: list[dict] = []
    for finding in clustered_findings(report.get("priority_findings", [])):
        count = int(finding.get("_cluster_count", 1) or 1)
        penalty = root_cause_penalty(finding, count)
        system_id, kind, target_key, label = root_cause_identity(finding)
        rows.append(
            {
                "finding": finding,
                "system_id": system_id,
                "kind": kind,
                "target_key": target_key,
                "label": label,
                "penalty": penalty,
                "count": count,
            }
        )
    return rows


def duplicate_suspicions(report: dict) -> list[dict]:
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for finding in report.get("priority_findings", []) or []:
        penalty = root_cause_penalty(finding, 1)
        if penalty <= 0:
            continue
        system_id, kind, target_key, label = root_cause_identity(finding)
        row = {
            "finding": finding,
            "system_id": system_id,
            "kind": kind,
            "target_key": target_key,
            "label": label,
            "penalty": penalty,
            "count": 1,
        }
        key = loose_duplicate_key(finding)
        groups.setdefault(key, []).append(row)

    suspicions: list[dict] = []
    for key, rows in groups.items():
        raw_targets = {text(row["finding"].get("target")) for row in rows if text(row["finding"].get("target"))}
        if len(rows) < 2 or len(raw_targets) < 2:
            continue
        current_penalty = sum(int(row["penalty"]) for row in rows)
        suggested_single_penalty = max(int(row["penalty"]) for row in rows)
        suspected_over_penalty = max(0, current_penalty - suggested_single_penalty)
        if suspected_over_penalty <= 0:
            continue
        findings = [row["finding"] for row in rows]
        targets = []
        evidence = []
        for finding in findings:
            target = text(finding.get("target"))
            if target:
                targets.append(target)
            item_evidence = text(finding.get("_cluster_evidence") or finding.get("technical_evidence") or finding.get("evidence"))
            if item_evidence:
                evidence.append(item_evidence)
        suspicions.append(
            {
                "group_key": "|".join(key),
                "cluster_count": len(rows),
                "current_penalty": current_penalty,
                "suggested_single_penalty": suggested_single_penalty,
                "suspected_over_penalty": suspected_over_penalty,
                "titles": sorted({text(item.get("_cluster_label") or item.get("title") or "未命名问题") for item in findings}),
                "targets": sorted(dict.fromkeys(targets))[:12],
                "evidence_samples": list(dict.fromkeys(evidence))[:5],
                "suggested_merge_fields": ["cluster_key", "category", "finding_type", "target"],
                "recommendation": "请复核这些发现是否属于同一根因；如属同一根因，应补充稳定 cluster_key/category/finding_type，并只保留一次扣分。",
            }
        )
    return sorted(suspicions, key=lambda item: (-int(item["suspected_over_penalty"]), item["group_key"]))


def build_markdown(result: dict) -> str:
    lines = [
        "# 评分合理性复核",
        "",
        f"- 状态：{result['status']}",
        f"- 报告评分：{result['score']} / 100",
        f"- 重算评分：{result['recomputed_score']} / 100",
        f"- 报告状态：{result['reported_status']}",
        f"- 期望状态：{result['expected_status']}",
        f"- 低分阈值：{result['threshold']} / 100",
        f"- 严格扣分簇：{result['metrics']['penalty_clusters']} 个",
        f"- 疑似重复扣分组：{len(result['duplicate_suspicions'])} 个",
        "",
    ]
    if result["blocking_reasons"]:
        lines.extend(["## 阻断原因", ""])
        for reason in result["blocking_reasons"]:
            lines.append(f"- {reason}")
        lines.append("")
    if result["duplicate_suspicions"]:
        lines.extend(["## 疑似重复扣分", ""])
        for index, item in enumerate(result["duplicate_suspicions"], 1):
            lines.extend(
                [
                    f"### {index}. {item['group_key']}",
                    "",
                    f"- 当前扣分合计：{item['current_penalty']}",
                    f"- 建议单次扣分：{item['suggested_single_penalty']}",
                    f"- 疑似多扣：{item['suspected_over_penalty']}",
                    f"- 建议归并字段：{', '.join(item['suggested_merge_fields'])}",
                    f"- 标题：{'；'.join(item['titles'])}",
                    f"- 目标：{'；'.join(item['targets'])}",
                    f"- 建议：{item['recommendation']}",
                    "",
                ]
            )
    else:
        lines.extend(["## 疑似重复扣分", "", "- 未发现疑似重复扣分组。", ""])
    return "\n".join(lines)


def audit_report(report_path: str | Path, out_dir: str | Path, threshold: int = DEFAULT_THRESHOLD) -> dict:
    report_path = Path(report_path)
    out_dir = ensure_dir(out_dir)
    report = read_json(report_path)
    score = int(report.get("score") or 0)
    recomputed = recompute_score(report)
    reported_status = str(report.get("overall_status") or "unknown")
    expected_status, status_reasons = recompute_status(report, recomputed)
    rows = penalty_rows(report)
    suspicions = duplicate_suspicions(report)

    blocking_reasons: list[str] = []
    if score < threshold:
        blocking_reasons.append("low_score_requires_review")
    if score != recomputed:
        blocking_reasons.append("score_mismatch")
    if reported_status != expected_status:
        blocking_reasons.append("status_score_mismatch")
    if suspicions:
        blocking_reasons.append("duplicate_penalty_suspected")

    status = "blocked" if blocking_reasons else "pass"
    result = {
        "schema_version": 1,
        "status": status,
        "report": str(report_path),
        "score": score,
        "recomputed_score": recomputed,
        "reported_status": reported_status,
        "expected_status": expected_status,
        "status_reasons": status_reasons,
        "threshold": threshold,
        "blocking_reasons": blocking_reasons,
        "duplicate_suspicions": suspicions,
        "metrics": {
            "findings": len(report.get("priority_findings", []) or []),
            "penalty_clusters": len(rows),
            "total_penalty": sum(int(row["penalty"]) for row in rows) + score_unknown_penalty(report),
            "unknown_penalty": score_unknown_penalty(report),
        },
    }
    write_json(out_dir / "score-audit.json", result)
    (out_dir / "score-audit.md").write_text(build_markdown(result), encoding="utf-8-sig")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit health score reasonableness before rendering final reports.")
    parser.add_argument("--report", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    args = parser.parse_args()
    result = audit_report(args.report, args.out, args.threshold)
    print(Path(args.out) / "score-audit.json")
    if result["status"] == "blocked":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
