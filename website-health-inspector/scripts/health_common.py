from __future__ import annotations

import json
import os
import re
import socket
import ssl
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


STATUS_ORDER = {"healthy": 0, "warning": 1, "unknown": 2, "critical": 3}
SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}
SAFE_SECRET_KEYS = {"password_env", "passwordEnv", "token_env", "secret_env", "api_key_env"}
SENSITIVE_KEY_RE = re.compile(r"(?i)(password|passwd|pwd|token|secret|api[_-]?key|authorization|cookie|session)")
SECRET_TEXT_REPLACEMENTS = [
    (re.compile(r"sk-[A-Za-z0-9_-]{12,}"), "[REDACTED_OPENAI_KEY]"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9_./+=-]{12,}"), r"\1[REDACTED_TOKEN]"),
    (re.compile(r"(?i)((?:api[_-]?key|token|secret|password|passwd|pwd)\s*[:=]\s*['\"]?)[^'\"\s;,]{6,}"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(OPENAI_API_KEY\s*=\s*)\S+"), r"\1[REDACTED]"),
]
DANGEROUS_WORDS = {
    "logout",
    "delete",
    "remove",
    "approve",
    "payment",
    "restart",
    "shutdown",
    "disable",
    "drop",
    "truncate",
    "封禁",
    "删除",
    "审批",
    "重启",
    "下发",
    "结算",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def read_json(path: str | Path) -> Any:
    with open(path, "r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def scrub_sensitive_text(value: Any, explicit_values: list[str] | None = None) -> str:
    text = "" if value is None else str(value)
    for secret in explicit_values or []:
        if secret:
            text = text.replace(str(secret), "[REDACTED_SECRET]")
    for pattern, replacement in SECRET_TEXT_REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return text


def scrub_sensitive_data(data: Any, explicit_values: list[str] | None = None, key: str = "") -> Any:
    if isinstance(data, dict):
        cleaned: dict[str, Any] = {}
        for child_key, child_value in data.items():
            child_key_text = str(child_key)
            if child_key_text in SAFE_SECRET_KEYS:
                cleaned[child_key] = scrub_sensitive_data(child_value, explicit_values, child_key_text)
            elif SENSITIVE_KEY_RE.search(child_key_text):
                cleaned[child_key] = "[REDACTED_SECRET]" if child_value not in (None, "") else child_value
            else:
                cleaned[child_key] = scrub_sensitive_data(child_value, explicit_values, child_key_text)
        return cleaned
    if isinstance(data, list):
        return [scrub_sensitive_data(item, explicit_values, key) for item in data]
    if isinstance(data, str):
        return scrub_sensitive_text(data, explicit_values)
    return data


def write_json(path: str | Path, data: Any, explicit_sensitive_values: list[str] | None = None) -> Path:
    target = Path(path)
    ensure_dir(target.parent)
    safe_data = scrub_sensitive_data(deepcopy(data), explicit_sensitive_values)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(safe_data, handle, ensure_ascii=False, indent=2)
    return target


def slugify(value: str, fallback: str = "item") -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(value or "").strip()).strip("-")
    return text[:80] or fallback


def as_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on", "是", "启用"}


def as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def split_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [item.strip() for item in re.split(r"[;；\n,，]+", str(value)) if item.strip()]


def normalize_url(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return raw
    parsed = urlparse(raw)
    if not parsed.scheme:
        raw = "https://" + raw
    return raw


def is_valid_url(url: str) -> bool:
    parsed = urlparse(normalize_url(url))
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def has_dangerous_word(value: str) -> bool:
    lowered = str(value or "").lower()
    return any(word in lowered for word in DANGEROUS_WORDS)


def status_from_findings(findings: list[dict[str, Any]]) -> str:
    from scoring_model import health_status_from_score_and_findings, score_from_finding_clusters

    score = score_from_finding_clusters(findings)
    return health_status_from_score_and_findings(score, findings, has_reports=True)


def score_from_findings(findings: list[dict[str, Any]], unknown_penalty: int = 0) -> int:
    from scoring_model import score_from_finding_clusters

    return score_from_finding_clusters(findings, unknown_penalty=unknown_penalty)


def priority_for(severity: str, system_priority: str = "medium") -> str:
    sev = SEVERITY_ORDER.get(severity, 1)
    sys = {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(system_priority, 2)
    total = sev + sys
    if total >= 7:
        return "P1"
    if total >= 5:
        return "P2"
    if total >= 3:
        return "P3"
    return "P4"


def make_finding(
    *,
    module: str,
    index: int,
    system: dict[str, Any],
    severity: str,
    title: str,
    impact: str,
    evidence: str,
    target: str = "",
    recommendation: str = "",
    evidence_files: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": f"{module}-{index:03d}",
        "system_id": system.get("id", ""),
        "system_name": system.get("name", system.get("id", "")),
        "severity": severity,
        "priority": priority_for(severity, system.get("priority", "medium")),
        "title": title,
        "business_impact": impact,
        "technical_evidence": evidence,
        "target": target,
        "recommendation": recommendation,
        "evidence_files": evidence_files or [],
    }


def tcp_connect(host: str, port: int, timeout: float = 3.0) -> tuple[bool, str]:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True, "connected"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def tls_expiry_days(hostname: str, port: int = 443, timeout: float = 5.0) -> int | None:
    try:
        context = ssl.create_default_context()
        with socket.create_connection((hostname, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as ssock:
                cert = ssock.getpeercert()
        not_after = cert.get("notAfter")
        if not not_after:
            return None
        expiry = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        return (expiry - datetime.now(timezone.utc)).days
    except Exception:  # noqa: BLE001
        return None


def resolve_env_placeholder(value: Any) -> str:
    text = "" if value is None else str(value)
    match = re.fullmatch(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", text.strip())
    if match:
        return os.getenv(match.group(1), "")
    return text


def module_report(report_type: str, findings: list[dict[str, Any]], systems: list[dict[str, Any]], metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    score = score_from_findings(findings)
    status = status_from_findings(findings)
    return {
        "report_type": report_type,
        "generated_at": now_iso(),
        "status": status,
        "score": score,
        "summary": f"{len(systems)} 个系统完成 {report_type} 检查，发现 {len(findings)} 个问题。",
        "systems": systems,
        "findings": findings,
        "metrics": metrics or {},
    }
