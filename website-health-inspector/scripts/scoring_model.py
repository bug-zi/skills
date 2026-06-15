from __future__ import annotations

import re
from urllib.parse import urlparse


PENALTY_BY_SEVERITY = {"critical": 35, "high": 25, "medium": 12, "low": 5}
SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
PRIORITY_ORDER = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}

ROOT_CAUSE_PENALTIES = {
    "confirmed-outage": 35,
    "high-confidence-risk": 22,
    "admin-login-unconfirmed": 0,
    "automation-session-boundary": 0,
    "parameterized-route-boundary": 0,
    "manual-confirmed-normal": 0,
    "protected-route-login-redirect": 8,
    "auth-refresh": 6,
    "module-coverage-gap": 5,
    "module-runtime-failure": 8,
    "public-footer-404": 6,
    "front-route-404": 5,
    "certificate-query-empty-404": 3,
    "default-password-visible": 8,
    "project-center-null-users": 5,
    "request-failure-endpoint": 6,
    "spa-text-check": 2,
    "tls-expiry": 5,
    "slow-page": 2,
    "review-needed": 5,
}

ROOT_CAUSE_LABELS = {
    "admin-login-unconfirmed": "自动化登录态信号未确认",
    "automation-session-boundary": "自动化会话未确认后的受保护页面跳转",
    "parameterized-route-boundary": "参数化业务路由覆盖边界",
    "manual-confirmed-normal": "人工复核已确认正常",
    "protected-route-login-redirect": "受保护页面重定向至登录页",
    "auth-refresh": "认证刷新接口会话边界需复核",
    "module-coverage-gap": "巡检模块覆盖缺口",
    "module-runtime-failure": "巡检模块运行失败",
    "public-footer-404": "公开页面页脚入口返回站内 404 页面",
    "front-route-404": "前端构建产物暴露的部分路由当前渲染为 404",
    "certificate-query-empty-404": "证书查询接口空结果体验需复核",
    "default-password-visible": "系统设置页默认密码配置字段需复核",
    "project-center-null-users": "实验/项目中心用户列表空值处理异常",
    "request-failure-endpoint": "浏览器资源请求失败",
    "spa-text-check": "HTTP 文本检查疑似单页应用误报",
    "tls-expiry": "TLS 证书有效期风险",
    "slow-page": "页面打开时间偏慢",
    "confirmed-outage": "已确认核心可用性故障",
    "high-confidence-risk": "高可信风险",
    "review-needed": "需人工复核事项",
}

STRUCTURED_ALIASES = {
    "request-failure": "request-failure-endpoint",
    "request-failure-endpoint": "request-failure-endpoint",
    "automation-session-boundary": "automation-session-boundary",
    "admin-login-unconfirmed": "admin-login-unconfirmed",
    "manual-confirmed-normal": "manual-confirmed-normal",
    "protected-route-login-redirect": "protected-route-login-redirect",
    "auth-refresh": "auth-refresh",
    "module-coverage-gap": "module-coverage-gap",
    "coverage-gap": "module-coverage-gap",
    "module-runtime-failure": "module-runtime-failure",
    "runtime-failure": "module-runtime-failure",
    "public-footer-404": "public-footer-404",
    "front-route-404": "front-route-404",
    "certificate-query-empty-404": "certificate-query-empty-404",
    "default-password-visible": "default-password-visible",
    "project-center-null-users": "project-center-null-users",
    "parameterized-route-boundary": "parameterized-route-boundary",
    "spa-text-check": "spa-text-check",
    "tls-expiry": "tls-expiry",
    "slow-page": "slow-page",
    "performance-slow-page": "slow-page",
    "confirmed-outage": "confirmed-outage",
    "high-confidence-risk": "high-confidence-risk",
    "review-needed": "review-needed",
}

ZERO_PENALTY_KEYS = {
    "admin-login-unconfirmed",
    "automation-session-boundary",
    "parameterized-route-boundary",
    "manual-confirmed-normal",
}

TARGET_SENSITIVE_KEYS = {"request-failure-endpoint"}
NON_PRODUCTION_ENVIRONMENTS = {
    "dev",
    "development",
    "test",
    "testing",
    "qa",
    "uat",
    "stage",
    "staging",
    "pre",
    "preprod",
    "pre-production",
    "local",
    "sandbox",
}


def _text(value) -> str:
    return str(value or "").strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9._:-]+", "-", value.lower()).strip("-")


def _normalized_field(finding: dict, *names: str) -> str:
    for name in names:
        value = _slug(_text(finding.get(name)))
        if value:
            return value
    return ""


def _normalized_system_id(finding: dict) -> str:
    return _normalized_field(finding, "system_id", "system_name", "name")


def _is_non_production(finding: dict) -> bool:
    environment = _normalized_field(finding, "environment", "env", "stage", "deployment_env")
    return environment in NON_PRODUCTION_ENVIRONMENTS


def _number(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _metric_value(finding: dict, *field_names: str) -> float | None:
    for field_name in field_names:
        value = _number(finding.get(field_name))
        if value is not None:
            return value

    blob = " ".join(
        _text(finding.get(field_name))
        for field_name in (
            "technical_evidence",
            "evidence",
            "details",
            "business_impact",
            "recommendation",
        )
    )
    for field_name in field_names:
        escaped = re.escape(field_name).replace("\\_", "[-_ ]?")
        match = re.search(rf"\b{escaped}\s*[:=]\s*(-?\d+(?:\.\d+)?)", blob, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def _bounded_repeat_penalty(base: int, count: int, increment: int, cap: int) -> int:
    repeat_count = max(0, int(count or 1) - 1)
    return min(base + repeat_count * increment, cap)


def _review_needed_penalty(severity: str, confidence: str) -> int:
    if confidence in {"confirmed", "manual-confirmed", "high", "strong"}:
        return {"critical": 22, "high": 15, "medium": 8, "low": 5}.get(severity, 8)
    if confidence in {"low", "weak", "uncertain", "suspected"}:
        return {"critical": 12, "high": 8, "medium": 3, "low": 2}.get(severity, 3)
    return min(PENALTY_BY_SEVERITY.get(severity, 5), ROOT_CAUSE_PENALTIES["review-needed"])


def _tls_expiry_penalty(finding: dict) -> int:
    days = _metric_value(
        finding,
        "tls_expiry_days",
        "certificate_expiry_days",
        "cert_expiry_days",
        "days_until_expiry",
    )
    if days is None:
        return ROOT_CAUSE_PENALTIES["tls-expiry"]
    if days < 0:
        return ROOT_CAUSE_PENALTIES["high-confidence-risk"]
    if days <= 7:
        return PENALTY_BY_SEVERITY["medium"]
    if days <= 30:
        return ROOT_CAUSE_PENALTIES["tls-expiry"]
    return 3


def _environment_adjusted_penalty(finding: dict, penalty: int) -> int:
    if _is_non_production(finding):
        return min(penalty, 12)
    return penalty


def structured_kind(finding: dict) -> tuple[str, str] | None:
    for field in ("cluster_key", "category", "finding_type"):
        raw = _text(finding.get(field))
        if not raw:
            continue
        normalized = _slug(raw)
        return field, STRUCTURED_ALIASES.get(normalized, normalized)
    return None


def normalized_endpoint(target: str) -> str:
    value = _text(target)
    if not value:
        return ""
    value = re.sub(r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+", "", value, flags=re.IGNORECASE).strip()
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        path = _normalize_endpoint_path(parsed.path)
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}".lower()
    return _normalize_endpoint_path(value.split("?", 1)[0].split("#", 1)[0]).lower()


def _normalize_endpoint_path(path: str) -> str:
    raw = "/" + str(path or "").lstrip("/")
    segments = [segment for segment in raw.split("/") if segment]
    normalized = [_normalize_endpoint_segment(segment) for segment in segments]
    return "/" + "/".join(normalized) if normalized else "/"


def _normalize_endpoint_segment(segment: str) -> str:
    text = segment.strip()
    if not text:
        return text
    if re.fullmatch(r"\d+", text):
        return ":id"
    if re.fullmatch(r"[0-9a-f]{24}", text, flags=re.IGNORECASE):
        return ":id"
    if re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        text,
        flags=re.IGNORECASE,
    ):
        return ":id"
    text = re.sub(r"([._-])[0-9a-f]{8,}(?=\.)", r"\1[hash]", text, flags=re.IGNORECASE)
    text = re.sub(r"([._-])[0-9a-f]{8,}$", r"\1[hash]", text, flags=re.IGNORECASE)
    return text


def target_key_for(kind: str, target: str, field: str = "") -> str:
    if kind in TARGET_SENSITIVE_KEYS:
        return normalized_endpoint(target)
    if field == "cluster_key":
        return ""
    return "" if kind in ROOT_CAUSE_LABELS else normalized_endpoint(target)


def fallback_kind(finding: dict) -> tuple[str, str, str]:
    title = _text(finding.get("title"))
    target = _text(finding.get("target"))
    evidence = _text(finding.get("technical_evidence") or finding.get("evidence"))
    category = _text(finding.get("category") or finding.get("cluster_key") or finding.get("finding_type"))
    normalized_blob = f"{title} {target} {evidence} {category}".lower()

    if "parameterized" in normalized_blob and ("route" in normalized_blob or "business id" in normalized_blob):
        return ROOT_CAUSE_LABELS["parameterized-route-boundary"], "parameterized-route-boundary", ""
    if "auth/refresh" in target or ("401" in evidence and "auth" in target):
        return ROOT_CAUSE_LABELS["auth-refresh"], "auth-refresh", ""
    if "受保护页面重定向至登录页" in title:
        if "automation_login_status=unknown" in evidence or _text(finding.get("confidence")) == "automation-boundary":
            return ROOT_CAUSE_LABELS["automation-session-boundary"], "automation-session-boundary", ""
        return ROOT_CAUSE_LABELS["protected-route-login-redirect"], "protected-route-login-redirect", ""
    if "管理员登录状态未确认" in title or "自动化登录态信号未确认" in title:
        return ROOT_CAUSE_LABELS["admin-login-unconfirmed"], "admin-login-unconfirmed", ""
    if "公开页页脚入口" in title and "404" in title:
        return ROOT_CAUSE_LABELS["public-footer-404"], "public-footer-404", ""
    if "公开页面 " in title and "站内 404" in title:
        return ROOT_CAUSE_LABELS["public-footer-404"], "public-footer-404", ""
    if "前端构建产物暴露的部分路由当前渲染为 404" in title or "前端路由返回站内 404 页面" in title:
        return ROOT_CAUSE_LABELS["front-route-404"], "front-route-404", ""
    if "证书查询接口" in title and "404" in title:
        return ROOT_CAUSE_LABELS["certificate-query-empty-404"], "certificate-query-empty-404", ""
    if "默认密码" in title:
        return ROOT_CAUSE_LABELS["default-password-visible"], "default-password-visible", ""
    if "实验/项目中心" in title and "空值" in title:
        return ROOT_CAUSE_LABELS["project-center-null-users"], "project-center-null-users", ""
    if "浏览器资源请求失败" in title:
        return ROOT_CAUSE_LABELS["request-failure-endpoint"], "request-failure-endpoint", normalized_endpoint(target)
    if "浏览器捕获到异常 HTTP 响应" in title or "abnormal http" in normalized_blob or "http response" in normalized_blob:
        return "浏览器捕获到异常 HTTP 响应", "legacy-http-response-endpoint", normalized_endpoint(target)
    if "页面内容过短" in title or "body_length" in evidence:
        return ROOT_CAUSE_LABELS["spa-text-check"], "spa-text-check", ""
    return title, f"legacy:{title}", normalized_endpoint(target)


def root_cause_identity(finding: dict) -> tuple[str, str, str, str]:
    structured = structured_kind(finding)
    if structured:
        field, kind = structured
        label = ROOT_CAUSE_LABELS.get(kind) or _text(finding.get("title")) or kind
        target_key = target_key_for(kind, _text(finding.get("target")), field)
    else:
        label, kind, target_key = fallback_kind(finding)
    system_id = _normalized_system_id(finding)
    return system_id, kind, target_key, label


def finding_cluster_key(finding: dict) -> tuple[str, str]:
    _, kind, _, label = root_cause_identity(finding)
    return label, kind


def _is_better_representative(candidate: dict, current: dict) -> bool:
    cand_severity = SEVERITY_ORDER.get(_text(candidate.get("severity")) or "low", 1)
    curr_severity = SEVERITY_ORDER.get(_text(current.get("severity")) or "low", 1)
    if cand_severity != curr_severity:
        return cand_severity > curr_severity
    cand_priority = PRIORITY_ORDER.get((_text(candidate.get("priority")) or "P9").upper(), 9)
    curr_priority = PRIORITY_ORDER.get((_text(current.get("priority")) or "P9").upper(), 9)
    return cand_priority < curr_priority


def clustered_findings(findings: list[dict]) -> list[dict]:
    clusters: dict[tuple[str, str, str], dict] = {}
    order: list[tuple[str, str, str]] = []
    for finding in findings:
        system_id, kind, target_key, label = root_cause_identity(finding)
        identity = (system_id, kind, target_key)
        if identity not in clusters:
            clusters[identity] = {
                "finding": finding,
                "count": 0,
                "evidence": [],
                "targets": set(),
                "kind": kind,
                "label": label,
            }
            order.append(identity)
        item = clusters[identity]
        item["count"] += 1
        if _is_better_representative(finding, item["finding"]):
            item["finding"] = finding
        evidence = _text(finding.get("technical_evidence") or finding.get("evidence"))
        if evidence:
            item["evidence"].append(evidence)
        target = _text(finding.get("target"))
        if target:
            item["targets"].add(target)

    result = []
    for identity in order:
        item = clusters[identity]
        finding = dict(item["finding"])
        finding["_cluster_count"] = item["count"]
        finding["_cluster_evidence"] = "; ".join(item["evidence"][:5])
        finding["_cluster_targets"] = sorted(item["targets"])
        finding["_cluster_key"] = item["kind"]
        finding["_cluster_label"] = item["label"]
        result.append(finding)
    return result


def root_cause_penalty(finding: dict, count: int = 1) -> int:
    _, key = finding_cluster_key(finding)
    severity = _slug(_text(finding.get("severity"))) or "low"
    confidence = _normalized_field(finding, "confidence", "evidence_confidence")

    if confidence in {"manual-confirmed-normal", "manual-confirmed-ok", "manual-normal"}:
        return 0
    if key in ZERO_PENALTY_KEYS:
        return 0

    if key == "module-coverage-gap":
        return _environment_adjusted_penalty(finding, _bounded_repeat_penalty(5, count, 2, 10))
    if key == "slow-page":
        return _environment_adjusted_penalty(finding, _bounded_repeat_penalty(2, count, 1, 5))
    if key == "review-needed":
        return _environment_adjusted_penalty(finding, _review_needed_penalty(severity, confidence))
    if key == "tls-expiry":
        return _environment_adjusted_penalty(finding, _tls_expiry_penalty(finding))

    if confidence in {"low", "weak", "uncertain", "suspected"} and (key == "high-confidence-risk" or severity in {"high", "critical"}):
        return _environment_adjusted_penalty(finding, _review_needed_penalty(severity, confidence))

    if key == "confirmed-outage" or severity == "critical":
        return _environment_adjusted_penalty(finding, ROOT_CAUSE_PENALTIES["confirmed-outage"])
    if key == "high-confidence-risk" or severity == "high":
        return _environment_adjusted_penalty(finding, ROOT_CAUSE_PENALTIES["high-confidence-risk"])
    if key in ROOT_CAUSE_PENALTIES:
        return _environment_adjusted_penalty(finding, ROOT_CAUSE_PENALTIES[key])
    return _environment_adjusted_penalty(
        finding,
        min(PENALTY_BY_SEVERITY.get(severity, 5), ROOT_CAUSE_PENALTIES["review-needed"]),
    )


def score_from_finding_clusters(findings: list[dict], unknown_penalty: int = 0) -> int:
    score = 100 - unknown_penalty
    for finding in clustered_findings(findings):
        score -= root_cause_penalty(finding, int(finding.get("_cluster_count", 1) or 1))
    return max(0, min(100, score))


def status_reasons_from_score_and_findings(score: int, findings: list[dict], *, has_reports: bool = True) -> list[str]:
    if not has_reports:
        return ["no_module_reports"]
    reasons: list[str] = []
    positive_penalties = 0
    for finding in clustered_findings(findings):
        penalty = root_cause_penalty(finding, int(finding.get("_cluster_count", 1) or 1))
        if penalty <= 0:
            continue
        positive_penalties += 1
        _, key = finding_cluster_key(finding)
        severity = _slug(_text(finding.get("severity"))) or "low"
        if key == "confirmed-outage" or severity == "critical":
            reasons.append("critical_effective_penalty")
    if score < 60:
        reasons.append("score_below_60")
    if positive_penalties:
        reasons.append("positive_penalty_clusters")
    if not reasons:
        reasons.append("no_effective_penalty")
    return list(dict.fromkeys(reasons))


def health_status_from_score_and_findings(score: int, findings: list[dict], *, has_reports: bool = True) -> str:
    reasons = status_reasons_from_score_and_findings(score, findings, has_reports=has_reports)
    if "no_module_reports" in reasons:
        return "unknown"
    if "critical_effective_penalty" in reasons or "score_below_60" in reasons:
        return "critical"
    if "positive_penalty_clusters" in reasons:
        return "warning"
    return "healthy"


def score_and_status_from_findings(findings: list[dict], unknown_penalty: int = 0, *, has_reports: bool = True) -> tuple[int, str, list[str]]:
    score = score_from_finding_clusters(findings, unknown_penalty=unknown_penalty)
    status = health_status_from_score_and_findings(score, findings, has_reports=has_reports)
    reasons = status_reasons_from_score_and_findings(score, findings, has_reports=has_reports)
    return score, status, reasons


def classify_finding(finding: dict) -> tuple[str, str]:
    title = _text(finding.get("title"))
    evidence = _text(finding.get("technical_evidence") or finding.get("evidence"))
    target = _text(finding.get("target"))
    _, key = finding_cluster_key(finding)
    if key in {"admin-login-unconfirmed", "automation-session-boundary"}:
        return "自动化能力边界", "该项表示巡检代理未捕获稳定登录态或会话保持信号；人工登录正常时，不应归类为网站故障。"
    if key == "parameterized-route-boundary":
        return "自动化能力边界", "该项反映自动化巡检未掌握业务 ID 或角色上下文，不作为网站健康主扣分项。"
    if key == "spa-text-check":
        return "自动化识别不足", "普通 HTTP 文本检查未执行 JavaScript，单页应用可能已在浏览器实测中正常渲染，应以浏览器截图和页面文本为准。"
    if key == "auth-refresh":
        return "需人工复核", "认证刷新接口在未登录或会话边界下返回 401 可能是预期行为，但需要确认是否影响登录态续期。"
    if key == "request-failure-endpoint":
        return "需人工复核", "浏览器捕获到资源请求中断，建议结合后端日志和用户路径确认是否影响页面功能。"
    if key == "protected-route-login-redirect":
        return "需人工复核", "该页面可能确实需要登录或特定角色权限，也可能受登录态未确认影响；需要确认目标页面是否应在本账号下直接可访问。"
    if "err_aborted" in f"{title} {evidence} {target}".lower() or "failed to fetch" in evidence.lower():
        return "需人工复核", "浏览器捕获到资源请求中断，建议结合后端日志和用户路径确认是否影响页面功能。"
    if _text(finding.get("severity")) in {"critical", "high"}:
        return "高可信风险", "高严重度发现应优先进入修复或应急处置流程。"
    return "需人工复核", "当前证据不足以直接判定为真实故障，建议纳入例行复核。"


def score_breakdown(report: dict) -> list[dict]:
    rows: list[dict] = []
    running = 100
    for finding in clustered_findings(report.get("priority_findings", [])):
        severity = _text(finding.get("severity")) or "low"
        penalty = root_cause_penalty(finding, int(finding.get("_cluster_count", 1) or 1))
        running -= penalty
        label, note = classify_finding(finding)
        evidence = finding.get("_cluster_evidence") or finding.get("technical_evidence") or finding.get("evidence") or ""
        rows.append(
            {
                "priority": finding.get("priority", "-"),
                "severity": severity,
                "title": finding.get("_cluster_label") or finding.get("title", "未命名问题"),
                "target": finding.get("target", ""),
                "evidence": evidence,
                "penalty": penalty,
                "remaining": max(0, running),
                "classification": label,
                "note": note,
                "count": finding.get("_cluster_count", 1),
            }
        )
    return rows


def evidence_strength_counts(findings: list[dict]) -> dict[str, int]:
    labels = {"已确认故障": 0, "高可信风险": 0, "自动化能力边界": 0, "自动化识别不足": 0, "需人工复核": 0}
    for finding in clustered_findings(findings):
        label, _ = classify_finding(finding)
        if label == "真实告警":
            label = "已确认故障"
        labels[label] = labels.get(label, 0) + 1
    return labels
