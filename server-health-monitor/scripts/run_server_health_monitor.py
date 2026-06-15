#!/usr/bin/env python3
"""Run a read-only server health inspection and render delivery reports."""

from __future__ import annotations

import argparse
import base64
import csv
import datetime as dt
import html
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any


# auto 缺少明确导览图决策时中止
SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "cookie",
    "private_key",
    "auth_key",
    "priv_key",
    "community",
    "apikey",
    "api_key",
)
SAFE_NON_SECRET_KEYS = {
    "auth_security",
    "password_strength",
    "password_login_enabled",
    "root_login_enabled",
    "winrm_basic_enabled",
}

STATUS_LABELS = {"healthy": "健康", "warning": "预警", "critical": "严重", "unknown": "未知"}
SEVERITY_LABELS = {"info": "提示", "warning": "预警", "critical": "严重"}
COVERAGE_LABELS = {
    "offline-simulated": "离线清单验证",
    "live": "实时 TCP 探测",
    "live-tcp-probe": "实时 TCP 探测",
    "doops-collected": "doops 主机采集",
    "doops-self-collected": "doops 节点自身采集",
    "doops-network-probe": "doops 内网探测",
    "ssh-collected": "SSH 只读采集",
    "winrm-collected": "WinRM 只读采集",
    "ssh-winrm-collected": "SSH/WinRM 只读采集",
    "partial-host-metrics": "主机指标部分覆盖",
    "inventory-supplied": "清单提供",
    "not-supplied": "未提供",
}
COVERAGE_LABELS.update(
    {
        "snmp-collected": "SNMPv3 只读采集",
        "partial-snmp-metrics": "SNMPv3 部分覆盖",
        "auth-security-collected": "认证安全已覆盖",
        "partial-auth-security": "认证安全部分覆盖",
    }
)
CREDENTIAL_LABELS = {
    "available-from-environment": "环境变量可用，报告不展示真实凭证",
    "reference-only": "仅记录凭证引用，未读取真实凭证",
    "not-provided": "未提供凭证",
}
PORT_STATUS_LABELS = {"open": "开放", "closed": "关闭", "timeout": "超时", "not-tested": "未探测"}
PORT_SOURCE_LABELS = {
    "explicit": "清单显式声明",
    "excel-inferred": "根据 Excel 清单操作系统推断",
    "os-inferred": "根据操作系统推断",
    "role-inferred": "根据业务角色推断",
    "legacy": "旧版清单端口",
    "observed": "探测结果提供",
    "unknown": "来源未说明",
}
PORT_USAGE_LABELS = {
    "business": "业务端口",
    "service": "服务端口",
    "management": "管理端口",
    "unknown": "用途未说明",
}
PRIORITY_DUE_TIMES = {"P1": "当日处理", "P2": "两个工作日内处理", "P3": "复核确认", "P4": "补齐清单"}
MANAGEMENT_PORTS = {22, 3389, 5985, 5986}
BUSINESS_PORTS = {21, 80, 443, 445, 8080, 8443, 1521, 3306, 5432, 6379}
CORE_CRITICALITY_VALUES = {"core", "critical", "核心", "核心系统", "重要", "高"}


def marker_chars(*codepoints: int) -> str:
    return "".join(chr(codepoint) for codepoint in codepoints)


BAD_TEXT_MARKERS = (
    "?" * 2,
    chr(0xFFFD),
    marker_chars(0x951F, 0x65A4, 0x62F7),
    marker_chars(0x00C3),
    marker_chars(0x00C2),
    marker_chars(0x00E2, 0x20AC),
)

GUIDE_RUNTIME_NOTICES = (
    "本次按参数跳过",
    "跳过 GPT",
    "未检测到图像生成密钥",
    "GPT 导览图生成失败",
    "生成失败，已使用 HTML",
)

DEFAULT_THRESHOLDS = {
    "cpu_warning_percent": 75,
    "cpu_critical_percent": 90,
    "memory_warning_percent": 80,
    "memory_critical_percent": 92,
    "disk_warning_percent": 80,
    "disk_critical_percent": 90,
    "load_warning_per_core": 1.5,
    "load_critical_per_core": 2.5,
    "process_cpu_warning_percent": 80,
    "process_cpu_critical_percent": 150,
    "process_memory_warning_percent": 25,
    "process_memory_critical_percent": 50,
}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def display_timestamp(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "未提供"
    normalized = text
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(normalized)
        return parsed.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return text.replace("T", " ").replace("+08:00", "").replace("+00:00", "")


def load_inventory(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"inventory not found: {path}")
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {"environment": {"name": "Server environment"}, "servers": data}
        if isinstance(data, dict):
            if "servers" not in data:
                raise ValueError("JSON inventory must contain a 'servers' array")
            return data
        raise ValueError("JSON inventory must be an object or array")
    if path.suffix.lower() in {".csv", ".tsv"}:
        delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle, delimiter=delimiter))
        servers = []
        for row in rows:
            ports = parse_ports(row.get("ports") or row.get("Ports") or "")
            servers.append(
                sanitize_mapping(
                    {
                        "name": row.get("name") or row.get("server_name") or row.get("Server") or "unnamed-server",
                        "address": row.get("address") or row.get("host") or row.get("ip") or "",
                        "os_type": row.get("os_type") or row.get("os") or "unknown",
                        "role": row.get("role") or "",
                        "owner": row.get("owner") or "",
                        "ports": ports,
                        "auth_ref": row.get("auth_ref") or "",
                        "collect": {"network": True},
                    }
                )
            )
        return {"environment": {"name": path.stem}, "servers": servers}
    raise ValueError("inventory must be .json, .csv, or .tsv")


def parse_ports(value: Any) -> list[int]:
    if value is None:
        return []
    if isinstance(value, list):
        raw = value
    else:
        raw = str(value).replace(";", ",").split(",")
    ports: list[int] = []
    for item in raw:
        if item == "":
            continue
        try:
            port = int(str(item).strip())
        except ValueError:
            continue
        if 1 <= port <= 65535:
            ports.append(port)
    return sorted(set(ports))


def port_number(value: Any) -> int | None:
    try:
        port = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return port if 1 <= port <= 65535 else None


def infer_port_usage(port: int, role: str = "") -> str:
    role_text = role.lower()
    if port in MANAGEMENT_PORTS:
        return "management"
    if port in BUSINESS_PORTS:
        return "business"
    if any(marker in role_text for marker in ("web", "portal", "database", "db", "ftp", "redis", "file")):
        return "business"
    return "unknown"


def normalize_port_obligation(item: Any, role: str = "", default_source: str = "legacy") -> dict[str, Any] | None:
    if isinstance(item, dict):
        port = port_number(item.get("port") or item.get("number") or item.get("value"))
        if port is None:
            return None
        usage = str(item.get("usage") or item.get("type") or "").strip().lower()
        if usage not in PORT_USAGE_LABELS:
            usage = infer_port_usage(port, role)
        source = str(item.get("source") or item.get("origin") or default_source or "unknown").strip() or "unknown"
        required = bool(item.get("required", True))
        return {
            "port": port,
            "usage": usage,
            "source": source,
            "required": required,
            "label": str(item.get("label") or item.get("name") or ""),
            "description": str(item.get("description") or ""),
        }
    port = port_number(item)
    if port is None:
        return None
    return {
        "port": port,
        "usage": infer_port_usage(port, role),
        "source": default_source,
        "required": True,
        "label": "",
        "description": "",
    }


def normalize_port_obligations(server: dict[str, Any]) -> list[dict[str, Any]]:
    role = str(server.get("role") or "")
    raw_obligations = server.get("port_obligations")
    obligations = []
    if isinstance(raw_obligations, list):
        for item in raw_obligations:
            obligation = normalize_port_obligation(item, role, "explicit")
            if obligation:
                obligations.append(obligation)
    elif isinstance(raw_obligations, dict):
        obligation = normalize_port_obligation(raw_obligations, role, "explicit")
        if obligation:
            obligations.append(obligation)
    if not obligations:
        source = str(server.get("port_source") or "legacy")
        for item in server.get("ports", []):
            obligation = normalize_port_obligation(item, role, source)
            if obligation:
                obligations.append(obligation)
    deduped: dict[int, dict[str, Any]] = {}
    for obligation in obligations:
        existing = deduped.get(obligation["port"])
        if not existing or existing.get("source") != "explicit" and obligation.get("source") == "explicit":
            deduped[obligation["port"]] = obligation
    return [deduped[port] for port in sorted(deduped)]


def port_source_label(value: Any) -> str:
    return PORT_SOURCE_LABELS.get(str(value), str(value) if value else "来源未说明")


def port_usage_label(value: Any) -> str:
    return PORT_USAGE_LABELS.get(str(value), str(value) if value else "用途未说明")


def is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    if normalized in SAFE_NON_SECRET_KEYS:
        return False
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def sanitize_mapping(value: Any) -> Any:
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, nested in value.items():
            if is_sensitive_key(str(key)):
                continue
            clean[str(key)] = sanitize_mapping(nested)
        return clean
    if isinstance(value, list):
        return [sanitize_mapping(item) for item in value]
    return value


def redact_text(text: str, limit: int = 4000) -> str:
    clean = re.sub(r"(?i)(token|password|secret|cookie|api[_-]?key|auth[_-]?key|priv[_-]?key|community)(\s*[:=]\s*)\S+", r"\1\2<redacted>", str(text or ""))
    clean = re.sub(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted>", clean)
    return clean[-limit:]


def normalize_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    thresholds = DEFAULT_THRESHOLDS | sanitize_mapping(inventory.get("thresholds", {}))
    environment = sanitize_mapping(inventory.get("environment", {}))
    if not environment.get("name"):
        environment["name"] = "Server environment"
    servers = []
    for index, server in enumerate(inventory.get("servers", []), start=1):
        clean = sanitize_mapping(server)
        name = clean.get("name") or f"server-{index:02d}"
        address = clean.get("address") or clean.get("host") or clean.get("ip") or ""
        servers.append(
            {
                "name": str(name),
                "address": str(address),
                "os_type": str(clean.get("os_type") or clean.get("os") or "unknown").lower(),
                "role": str(clean.get("role") or ""),
                "owner": str(clean.get("owner") or ""),
                "department": str(clean.get("department") or ""),
                "business_system": str(clean.get("business_system") or clean.get("businessSystem") or ""),
                "business_domain": str(clean.get("business_domain") or clean.get("businessDomain") or ""),
                "user_group": str(clean.get("user_group") or clean.get("userGroup") or ""),
                "criticality": str(clean.get("criticality") or ""),
                "has_redundancy": clean.get("has_redundancy", clean.get("hasRedundancy")),
                "impact_note": str(clean.get("impact_note") or clean.get("impactNote") or ""),
                "inventory_index": clean.get("inventory_index") or index,
                "lifecycle_status": str(clean.get("lifecycle_status") or "active"),
                "lifecycle_source": str(clean.get("lifecycle_source") or "assumed"),
                "lifecycle_value": str(clean.get("lifecycle_value") or ""),
                "lifecycle_reason": str(clean.get("lifecycle_reason") or ""),
                "ports": parse_ports(clean.get("ports", [])),
                "port_obligations": normalize_port_obligations(clean),
                "credential_status": credential_status(server),
                "collect": clean.get("collect", {"network": True}),
                "metrics": clean.get("metrics", {}),
                "services": clean.get("services", []),
                "processes": clean.get("processes", []),
                "network_observation": clean.get("network_observation", {}),
                "application_checks": clean.get("application_checks", []),
                "application_observation": clean.get("application_observation", []),
                "collection_trace": clean.get("collection_trace", {}),
                "collection_errors": clean.get("collection_errors", []),
                "auth_security": summarize_auth_security(clean.get("auth_security", {})),
                "notes": str(clean.get("notes") or ""),
            }
        )
    return {
        "environment": environment,
        "servers": servers,
        "thresholds": thresholds,
        "doops_channel": sanitize_mapping(inventory.get("doops_channel", {})),
        "ai_review": sanitize_mapping(inventory.get("ai_review", {})),
        "inventory_groups": sanitize_mapping(inventory.get("inventory_groups", {})),
    }


def credential_status(server: dict[str, Any]) -> str:
    auth_ref = str(server.get("auth_ref") or "")
    if auth_ref.startswith("env:"):
        env_name = auth_ref.split(":", 1)[1]
        return "available-from-environment" if os.environ.get(env_name) else "reference-only"
    if auth_ref:
        return "reference-only"
    return "not-provided"


def probe_port(host: str, port: int, timeout: float) -> dict[str, Any]:
    started = dt.datetime.now(dt.timezone.utc)
    try:
        with socket.create_connection((host, port), timeout=timeout):
            elapsed_ms = int((dt.datetime.now(dt.timezone.utc) - started).total_seconds() * 1000)
            return {"port": port, "status": "open", "latency_ms": elapsed_ms}
    except socket.timeout:
        return {"port": port, "status": "timeout", "latency_ms": None}
    except OSError as exc:
        return {"port": port, "status": "closed", "latency_ms": None, "error": exc.__class__.__name__}


def inspect_server(server: dict[str, Any], thresholds: dict[str, Any], offline: bool, timeout: float) -> dict[str, Any]:
    network = inspect_network(server, offline, timeout)
    metric_findings = evaluate_metrics(server.get("metrics", {}), thresholds, server)
    service_findings = evaluate_services(server.get("services", []), server)
    process_findings = evaluate_processes(server.get("processes", []), server.get("metrics", {}), thresholds, server)
    auth_findings = evaluate_auth_security(server, network)
    collection_findings = evaluate_collection_errors(server)
    findings = []
    findings.extend(collection_findings)
    findings.extend(network["findings"])
    findings.extend(metric_findings)
    findings.extend(service_findings)
    findings.extend(process_findings)
    findings.extend(auth_findings)
    findings.extend(evaluate_application_observations(server, findings))
    status = rollup_status(findings, "unknown" if offline else "healthy")
    priority = server_priority(findings)
    server_auth_security = summarize_auth_security(server.get("auth_security", {}))
    inspected = {
        "name": server["name"],
        "address": server["address"],
        "os_type": server["os_type"],
        "role": server["role"],
        "owner": server["owner"],
        "department": server.get("department", ""),
        "business_system": server.get("business_system", ""),
        "business_domain": server.get("business_domain", ""),
        "user_group": server.get("user_group", ""),
        "criticality": server.get("criticality", ""),
        "has_redundancy": server.get("has_redundancy"),
        "impact_note": server.get("impact_note", ""),
        "credential_status": server["credential_status"],
        "status": status,
        "priority": priority,
        "due_time": PRIORITY_DUE_TIMES.get(priority, ""),
        "network": network,
        "metrics": summarize_metrics(server.get("metrics", {})),
        "services": summarize_services(server.get("services", [])),
        "processes": summarize_processes(server.get("processes", [])),
        "application_checks": server.get("application_checks", []),
        "application_observation": server.get("application_observation", []),
        "collection_trace": server.get("collection_trace", {}),
        "collection_errors": summarize_collection_errors(server.get("collection_errors", [])),
        "findings": findings,
        "evidence_boundary": evidence_boundary(server, offline),
        "notes": server.get("notes", ""),
    }
    if server_auth_security.get("status") != "not_enabled":
        inspected["auth_security"] = server_auth_security
    return inspected


def inspect_network(server: dict[str, Any], offline: bool, timeout: float) -> dict[str, Any]:
    obligations = normalize_port_obligations(server)
    ports = [item["port"] for item in obligations]
    if offline:
        return {
            "mode": "offline-simulated",
            "ports": [port_result_with_obligation({"port": item["port"], "status": "not-tested", "latency_ms": None}, item) for item in obligations],
            "findings": [
                finding(
                    "info",
                    "已跳过网络探测",
                    "离线模式只记录清单覆盖情况，不连接目标服务器。",
                    "network",
                )
            ],
        }
    collect = server.get("collect", {}) if isinstance(server.get("collect", {}), dict) else {}
    observation = server.get("network_observation", {}) if isinstance(server.get("network_observation", {}), dict) else {}
    if observation or collect.get("doops_probe"):
        observed_ports = observation.get("ports", []) if isinstance(observation.get("ports", []), list) else []
        results = []
        obligation_by_port = {item["port"]: item for item in obligations}
        for result in observed_ports:
            if not isinstance(result, dict):
                continue
            port_value = result.get("port")
            try:
                port_number = int(port_value)
            except (TypeError, ValueError):
                continue
            obligation = obligation_by_port.get(port_number) or normalize_port_obligation({"port": port_number, "source": "observed"}, server.get("role", ""), "observed")
            results.append(port_result_with_obligation(result, obligation))
        findings = []
        if not server.get("address"):
            findings.append(inventory_finding(server, "缺少服务器地址", "清单未提供可用于 doops 内网探测的有效地址。"))
        for result in results:
            if result["status"] in {"closed", "timeout", "not-tested", "unknown"}:
                findings.append(port_unreachable_finding(server, result, observation.get("probe_target") or collect.get("probe_target") or "unknown", "doops"))
        if not results and observation.get("reachable") is False:
            findings.append(network_unreachable_finding(server, obligations, "doops 内网探测未发现 ICMP 或 TCP 可达证据。"))
        if not results and ports:
            results = [port_result_with_obligation({"port": item["port"], "status": "not-tested", "latency_ms": None}, item) for item in obligations]
        return {
            "mode": observation.get("mode") or "doops-network-probe",
            "ports": results,
            "findings": findings,
            "ping": observation.get("ping", {}),
            "reachable": observation.get("reachable"),
            "probe_target": observation.get("probe_target") or collect.get("probe_target"),
        }
    if collect.get("doops"):
        return {
            "mode": "doops-collected",
            "ports": [port_result_with_obligation({"port": item["port"], "status": "not-tested", "latency_ms": None}, item) for item in obligations],
            "findings": [
                finding(
                    "info",
                    "已通过 doops 采集主机证据",
                    "本次使用 doops 进入目标环境并只读采集主机指标；未从客户端执行 TCP 端口探测。",
                    "network",
                )
            ],
        }
    if not server.get("address"):
        return {
            "mode": "live",
            "ports": [],
            "findings": [inventory_finding(server, "缺少服务器地址", "清单未提供可用于网络检查的地址。")],
        }
    obligation_by_port = {item["port"]: item for item in obligations}
    results = [port_result_with_obligation(probe_port(server["address"], port, timeout), obligation_by_port.get(port)) for port in ports]
    findings = []
    for result in results:
        if result["status"] in {"closed", "timeout"}:
            findings.append(port_unreachable_finding(server, result, "", "live"))
    if not ports:
        findings.append(inventory_finding(server, "未声明预期端口", "当前只能进行清单级检查。", severity="info", priority="P4"))
    return {"mode": "live", "ports": results, "findings": findings}


def port_result_with_obligation(result: dict[str, Any], obligation: dict[str, Any] | None) -> dict[str, Any]:
    obligation = obligation or {}
    port = port_number(result.get("port") or obligation.get("port")) or 0
    usage = str(obligation.get("usage") or infer_port_usage(port)).lower()
    source = str(obligation.get("source") or "unknown")
    return {
        "port": port,
        "status": str(result.get("status") or "unknown"),
        "latency_ms": result.get("latency_ms"),
        "error": result.get("error"),
        "usage": usage,
        "usage_label": port_usage_label(usage),
        "source": source,
        "source_label": port_source_label(source),
        "required": bool(obligation.get("required", True)),
        "label": str(obligation.get("label") or ""),
    }


def has_business_impact(server: dict[str, Any]) -> bool:
    for key in ("business_system", "business_domain", "user_group", "impact_note"):
        if str(server.get(key) or "").strip():
            return True
    return server.get("has_redundancy") is not None


def is_core_server(server: dict[str, Any]) -> bool:
    return str(server.get("criticality") or "").strip().lower() in CORE_CRITICALITY_VALUES


def impact_profile(server: dict[str, Any]) -> dict[str, Any]:
    profile = {
        "business_system": str(server.get("business_system") or ""),
        "business_domain": str(server.get("business_domain") or ""),
        "user_group": str(server.get("user_group") or ""),
        "has_redundancy": server.get("has_redundancy"),
        "impact_note": str(server.get("impact_note") or ""),
    }
    if not has_business_impact(server):
        profile["summary"] = "业务影响未在清单中提供，需由业务侧确认。"
        return profile
    parts = []
    if profile["business_system"]:
        parts.append(f"业务系统：{profile['business_system']}")
    if profile["business_domain"]:
        parts.append(f"业务域：{profile['business_domain']}")
    if profile["user_group"]:
        parts.append(f"用户群体：{profile['user_group']}")
    if profile["has_redundancy"] is not None:
        parts.append("替代节点：有" if profile["has_redundancy"] else "替代节点：未提供或无")
    if profile["impact_note"]:
        parts.append(profile["impact_note"])
    profile["summary"] = "；".join(parts) + "。"
    return profile


def owner_text(server: dict[str, Any]) -> str:
    return str(server.get("owner") or "").strip() or "未提供"


def priority_for_port(server: dict[str, Any], result: dict[str, Any]) -> tuple[str, str, str, bool, str]:
    port = int(result["port"])
    usage = str(result.get("usage") or infer_port_usage(port))
    source = str(result.get("source") or "unknown")
    if usage == "management" and source != "explicit":
        return "warning", "P3", "复核确认", True, "管理端口不可达，需复核是否符合安全策略"
    if usage in {"business", "service"}:
        priority = "P1" if is_core_server(server) else "P2"
        return "critical", priority, PRIORITY_DUE_TIMES[priority], False, f"业务端口 {port} 不可达"
    if source == "explicit":
        priority = "P1" if is_core_server(server) else "P2"
        return "critical", priority, PRIORITY_DUE_TIMES[priority], False, f"预期端口 {port} 不可达"
    return "warning", "P3", "复核确认", True, f"预期端口 {port} 不可达，需确认端口用途"


def recommendation_for_port(result: dict[str, Any]) -> tuple[str, list[str]]:
    usage = str(result.get("usage") or "")
    if usage == "management":
        actions = [
            "确认该管理端口是否按安全策略关闭或仅允许堡垒机访问。",
            "如策略允许关闭，请更新资产清单并标记管理端口非业务必需。",
            "如该端口需要开放，请按变更流程检查防火墙、ACL 和主机监听状态。",
        ]
        return "确认是否为安全策略关闭；如需开放，按变更流程复核防火墙、ACL、主机监听和堡垒机访问路径。", actions
    actions = [
        "确认应用进程、监听端口、反向代理和本机防火墙状态。",
        "检查数据库、中间件、负载均衡或网关依赖是否存在异常。",
        "核对最近变更记录，并确认是否已切换到备节点或替代服务。",
    ]
    return "确认应用进程、监听端口、反向代理、数据库/中间件依赖、最近变更和备节点切换状态。", actions


def port_unreachable_finding(server: dict[str, Any], result: dict[str, Any], probe_target: str, mode: str) -> dict[str, Any]:
    severity, priority, due_time, review_required, title = priority_for_port(server, result)
    target_text = f"通过 doops 目标 {probe_target}" if mode == "doops" else "本机"
    source_label = port_source_label(result.get("source"))
    usage_label = port_usage_label(result.get("usage"))
    evidence = (
        f"{target_text} 对 {server.get('address')}:{result['port']} 的 TCP 探测结果为 "
        f"{PORT_STATUS_LABELS.get(result['status'], result['status'])}；端口来源：{source_label}；端口用途：{usage_label}。"
    )
    impact = impact_profile(server)
    recommendation, actions = recommendation_for_port(result)
    return finding(
        severity,
        title,
        evidence,
        "network",
        priority=priority,
        due_time=due_time,
        impact=impact,
        impact_summary=impact["summary"],
        recommendation=recommendation,
        next_actions=actions,
        review_required=review_required,
        evidence_strength="strong" if result.get("source") == "explicit" else "needs-review",
        port=result["port"],
        port_source=str(result.get("source") or "unknown"),
        port_usage=str(result.get("usage") or "unknown"),
    )


def network_unreachable_finding(server: dict[str, Any], obligations: list[dict[str, Any]], evidence: str) -> dict[str, Any]:
    has_business_port = any(item.get("usage") in {"business", "service"} and item.get("source") == "explicit" for item in obligations)
    severity = "critical" if has_business_port or has_business_impact(server) else "warning"
    priority = "P1" if severity == "critical" and is_core_server(server) else "P2" if severity == "critical" else "P3"
    impact = impact_profile(server)
    actions = [
        "核对资产 IP 和清单地址是否正确。",
        "检查主机电源、虚拟机运行状态、安全组、防火墙和路由 ACL。",
        "从堡垒机或 doops 节点复核网络路径，并确认近期变更。",
    ]
    return finding(
        severity,
        "服务器网络不可达" if severity == "critical" else "服务器网络不可达，需复核资产清单",
        evidence,
        "network",
        priority=priority,
        due_time=PRIORITY_DUE_TIMES[priority],
        impact=impact,
        impact_summary=impact["summary"],
        recommendation="核对资产 IP、检查主机电源或虚拟机状态、检查安全组/防火墙/ACL，并从堡垒机或 doops 节点复核。",
        next_actions=actions,
        review_required=severity != "critical",
        evidence_strength="strong" if severity == "critical" else "needs-review",
    )


def inventory_finding(
    server: dict[str, Any],
    title: str,
    evidence: str,
    severity: str = "warning",
    priority: str = "P4",
) -> dict[str, Any]:
    impact = impact_profile(server)
    actions = ["补齐资产清单字段，包括地址、业务影响、预期端口和端口来源。"]
    return finding(
        severity,
        title,
        evidence,
        "inventory",
        priority=priority,
        due_time=PRIORITY_DUE_TIMES.get(priority, "补齐清单"),
        impact=impact,
        impact_summary=impact["summary"],
        recommendation="补齐资产清单并复核端口来源，避免将清单缺失误判为运行故障。",
        next_actions=actions,
        review_required=True,
        evidence_strength="needs-review",
    )


def evaluate_metrics(metrics: dict[str, Any], thresholds: dict[str, Any], server: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    findings = []
    cpu = number_or_none(metrics.get("cpu_percent"))
    if cpu is not None:
        findings.append(percent_finding(cpu, thresholds["cpu_warning_percent"], thresholds["cpu_critical_percent"], "CPU 使用率", "metrics", server))
    memory = number_or_none(metrics.get("memory_percent"))
    if memory is not None:
        findings.append(
            percent_finding(memory, thresholds["memory_warning_percent"], thresholds["memory_critical_percent"], "内存使用率", "metrics", server)
        )
    load = number_or_none(metrics.get("load_per_core"))
    if load is not None:
        if load >= float(thresholds["load_critical_per_core"]):
            findings.append(operational_finding("critical", "单核负载达到严重阈值", f"单核负载为 {load:.2f}。", "metrics", server))
        elif load >= float(thresholds["load_warning_per_core"]):
            findings.append(operational_finding("warning", "单核负载偏高", f"单核负载为 {load:.2f}。", "metrics", server))
    for disk in metrics.get("disks", []) if isinstance(metrics.get("disks", []), list) else []:
        used = number_or_none(disk.get("used_percent"))
        mount = str(disk.get("mount") or disk.get("name") or "disk")
        if used is not None:
            findings.append(
                percent_finding(
                    used,
                    thresholds["disk_warning_percent"],
                    thresholds["disk_critical_percent"],
                    f"磁盘使用率 {mount}",
                    "storage",
                    server,
                )
            )
    return [item for item in findings if item]


def percent_finding(value: float, warning: Any, critical: Any, label: str, category: str, server: dict[str, Any] | None = None) -> dict[str, Any] | None:
    warning_f = float(warning)
    critical_f = float(critical)
    if value >= critical_f:
        return operational_finding("critical", f"{label} 达到严重阈值", f"{label} 为 {value:.1f}%。", category, server)
    if value >= warning_f:
        return operational_finding("warning", f"{label} 偏高", f"{label} 为 {value:.1f}%。", category, server)
    return None


def evaluate_services(services: list[Any], server: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    findings = []
    for service in services if isinstance(services, list) else []:
        if not isinstance(service, dict):
            continue
        state = str(service.get("status") or service.get("state") or "").lower()
        expected = str(service.get("expected") or "running").lower()
        name = str(service.get("name") or "service")
        if state and expected and state != expected:
            findings.append(operational_finding("critical", f"服务 {name} 未达到预期状态", f"预期状态为 {expected}，观测状态为 {state}。", "service", server))
    return findings


def process_label(process: dict[str, Any]) -> str:
    name = str(process.get("name") or "process")
    pid = process.get("pid")
    if isinstance(pid, int):
        return f"{name}(pid={pid})"
    return name


def process_finding(
    severity: str,
    title: str,
    evidence: str,
    server: dict[str, Any] | None,
    process: dict[str, Any],
) -> dict[str, Any]:
    server = server or {}
    priority = "P2" if severity == "critical" else "P3"
    impact = impact_profile(server)
    return finding(
        severity,
        title,
        evidence,
        "process",
        priority=priority,
        due_time=PRIORITY_DUE_TIMES.get(priority, "复核确认"),
        impact=impact,
        impact_summary=impact["summary"],
        recommendation="结合主机整体 CPU/内存、业务高峰、进程启动时间和最近变更复核；如确认为异常，按服务归属排查日志、线程、连接数和资源限制。",
        next_actions=[
            f"登录只读监控通道复核 {process_label(process)} 当前资源占用。",
            "确认该进程是否属于预期业务负载或定时任务。",
            "检查最近发布、任务调度、日志增长和连接数变化。",
            "处置后重跑巡检并保留趋势对比。",
        ],
        review_required=severity != "critical",
        evidence_strength="strong",
        process=process_label(process),
    )


def evaluate_processes(
    processes: list[Any],
    metrics: dict[str, Any],
    thresholds: dict[str, Any],
    server: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    findings = []
    if not isinstance(processes, list):
        return findings
    host_cpu = number_or_none(metrics.get("cpu_percent")) if isinstance(metrics, dict) else None
    host_memory = number_or_none(metrics.get("memory_percent")) if isinstance(metrics, dict) else None
    host_cpu_critical = host_cpu is not None and host_cpu >= float(thresholds["cpu_critical_percent"])
    host_memory_critical = host_memory is not None and host_memory >= float(thresholds["memory_critical_percent"])
    cpu_seen = memory_seen = zombie_seen = 0
    for process in processes:
        if not isinstance(process, dict):
            continue
        state = str(process.get("state") or "").lower()
        if state.startswith("z") or "zombie" in state or "defunct" in state:
            if zombie_seen < 3:
                findings.append(
                    process_finding(
                        "warning",
                        "发现异常进程状态",
                        f"{process_label(process)} 状态为 {process.get('state') or 'unknown'}，可能存在僵尸进程或异常退出残留。",
                        server,
                        process,
                    )
                )
            zombie_seen += 1
        cpu = number_or_none(process.get("cpu_percent"))
        if cpu is not None and cpu >= float(thresholds["process_cpu_warning_percent"]) and cpu_seen < 3:
            severity = "critical" if host_cpu_critical and cpu >= float(thresholds["process_cpu_critical_percent"]) else "warning"
            findings.append(
                process_finding(
                    severity,
                    "主要进程 CPU 占用过高" if severity == "warning" else "主要进程 CPU 占用达到严重阈值",
                    f"{process_label(process)} CPU 占用 {cpu:.1f}%；主机整体 CPU 为 {host_cpu:.1f}%。" if host_cpu is not None else f"{process_label(process)} CPU 占用 {cpu:.1f}%。",
                    server,
                    process,
                )
            )
            cpu_seen += 1
        memory = number_or_none(process.get("memory_percent"))
        if memory is not None and memory >= float(thresholds["process_memory_warning_percent"]) and memory_seen < 3:
            severity = "critical" if host_memory_critical and memory >= float(thresholds["process_memory_critical_percent"]) else "warning"
            findings.append(
                process_finding(
                    severity,
                    "主要进程内存占用过高" if severity == "warning" else "主要进程内存占用达到严重阈值",
                    f"{process_label(process)} 内存占用 {memory:.1f}%；主机整体内存为 {host_memory:.1f}%。" if host_memory is not None else f"{process_label(process)} 内存占用 {memory:.1f}%。",
                    server,
                    process,
                )
            )
            memory_seen += 1
    return findings


def network_has_open_management_port(network: dict[str, Any]) -> bool:
    for port in network.get("ports", []) if isinstance(network.get("ports"), list) else []:
        if not isinstance(port, dict):
            continue
        try:
            number = int(port.get("port"))
        except (TypeError, ValueError):
            continue
        usage = str(port.get("usage") or "").lower()
        if number in {22, 3389, 5985, 5986} and str(port.get("status") or "").lower() == "open":
            return True
        if usage == "management" and str(port.get("status") or "").lower() == "open":
            return True
    return False


def auth_security_finding(
    severity: str,
    title: str,
    evidence: str,
    server: dict[str, Any],
    category: str = "auth-security",
    priority: str | None = None,
    review_required: bool | None = None,
) -> dict[str, Any]:
    impact = impact_profile(server)
    chosen_priority = priority or ("P1" if severity == "critical" else "P3")
    return finding(
        severity,
        title,
        evidence,
        category,
        priority=chosen_priority,
        due_time=PRIORITY_DUE_TIMES.get(chosen_priority, "复核确认"),
        impact=impact,
        impact_summary=impact["summary"],
        recommendation="复核认证日志、防护配置和账号口令强度；优先收敛管理端口暴露面，启用锁定策略、堡垒机或 MFA，并更换弱口令和复用口令。",
        next_actions=[
            "排查失败登录后成功登录的账号、来源 IP 和时间窗口。",
            "确认 SSH/RDP/WinRM 是否必须暴露，非必要管理入口应通过堡垒机或 VPN 收敛。",
            "启用账号锁定、fail2ban/NLA/MFA 等防护，并复核审计策略是否覆盖登录成功与失败。",
            "更换弱口令和复用口令，保留处置记录后重新巡检。",
        ],
        review_required=severity != "critical" if review_required is None else review_required,
        evidence_strength="strong" if severity == "critical" else "needs-review",
    )


def evaluate_auth_security(server: dict[str, Any], network: dict[str, Any]) -> list[dict[str, Any]]:
    auth_security = summarize_auth_security(server.get("auth_security", {}))
    status = str(auth_security.get("status") or "not_enabled")
    if status == "not_enabled":
        return []
    findings: list[dict[str, Any]] = []
    if status in {"unavailable", "partial"}:
        findings.append(
            auth_security_finding(
                "warning",
                "认证安全证据未覆盖，需补充日志读取权限",
                "已启用认证安全巡检，但认证日志或防护配置未能完整读取；不能据此判断不存在密码爆破风险。",
                server,
                priority="P3",
                review_required=True,
            )
        )
        if status == "unavailable":
            return findings
    log_evidence = auth_security.get("log_evidence", {}) if isinstance(auth_security.get("log_evidence"), dict) else {}
    protection = auth_security.get("protection_config", {}) if isinstance(auth_security.get("protection_config"), dict) else {}
    strength = auth_security.get("password_strength", {}) if isinstance(auth_security.get("password_strength"), dict) else {}
    failed = int(number_or_none(log_evidence.get("failed_login_count")) or 0)
    unique_sources = int(number_or_none(log_evidence.get("unique_source_count")) or 0)
    patterns = log_evidence.get("patterns", []) if isinstance(log_evidence.get("patterns"), list) else []
    weak_count = int(number_or_none(strength.get("weak_count")) or 0)
    reuse_count = int(number_or_none(strength.get("reuse_group_count")) or 0)
    management_open = network_has_open_management_port(network)
    has_failed_then_success = any(isinstance(pattern, dict) and pattern.get("type") == "failed-then-success" for pattern in patterns)
    if has_failed_then_success:
        findings.append(
            auth_security_finding(
                "critical",
                "发现疑似密码爆破后成功登录",
                f"最近 {auth_security.get('window_days', 7)} 天认证日志中存在失败登录后成功登录模式；失败次数 {failed}，来源数量 {unique_sources}。",
                server,
                priority="P1",
                review_required=False,
            )
        )
    if weak_count and management_open and protection.get("account_lockout_enabled") is False:
        findings.append(
            auth_security_finding(
                "critical",
                "弱口令叠加管理端口暴露且未启用锁定策略",
                f"密码强度评分发现弱口令 {weak_count} 个，管理端口可达，账号锁定策略未启用。",
                server,
                category="password-strength",
                priority="P1",
                review_required=False,
            )
        )
    if protection.get("root_login_enabled") is True and protection.get("password_login_enabled") is True and failed > 0:
        findings.append(
            auth_security_finding(
                "critical",
                "高权限账号允许远程密码登录且存在失败登录",
                f"root/Administrator 类高权限账号允许密码登录，最近 {auth_security.get('window_days', 7)} 天失败登录 {failed} 次。",
                server,
                category="auth-protection",
                priority="P1",
                review_required=False,
            )
        )
    if protection.get("winrm_basic_enabled") is True and protection.get("allow_unencrypted") is True and management_open:
        findings.append(
            auth_security_finding(
                "critical",
                "WinRM Basic 与未加密传输同时开启",
                "WinRM Basic 和 AllowUnencrypted 同时开启，且管理端口可达。",
                server,
                category="auth-protection",
                priority="P1",
                review_required=False,
            )
        )
    if not findings and failed >= 50:
        findings.append(
            auth_security_finding(
                "warning",
                "认证失败次数偏高，需排查密码爆破迹象",
                f"最近 {auth_security.get('window_days', 7)} 天失败登录 {failed} 次，来源数量 {unique_sources}。",
                server,
                priority="P2",
            )
        )
    if not findings and weak_count:
        findings.append(
            auth_security_finding(
                "warning",
                "发现弱口令风险，需按账号维度整改",
                f"本地密码强度评分发现弱口令 {weak_count} 个，复用组 {reuse_count} 个；报告不展示明文密码。",
                server,
                category="password-strength",
                priority="P3",
            )
        )
    if not findings and protection.get("password_login_enabled") is True and protection.get("account_lockout_enabled") in {False, None}:
        findings.append(
            auth_security_finding(
                "warning",
                "允许密码登录但锁定策略未确认",
                "认证防护配置显示允许密码登录，但账号锁定策略未启用或未能确认。",
                server,
                category="auth-protection",
                priority="P3",
            )
        )
    return findings


def evaluate_collection_errors(server: dict[str, Any]) -> list[dict[str, Any]]:
    collect = server.get("collect", {}) if isinstance(server.get("collect"), dict) else {}
    errors = summarize_collection_errors(server.get("collection_errors", []))
    if not collect.get("host_metrics") or not errors:
        return []
    error_types = "、".join(error["type"] for error in errors[:3])
    status = str(collect.get("host_metrics_status") or "failed")
    severity = "warning" if status != "collected" else "info"
    return [
        finding(
            severity,
            "主机指标无法监测",
            f"已尝试通过 doops 目标 {collect.get('metrics_probe_target') or 'unknown'} 进行只读主机指标采集，结果为 {status}，错误类型：{error_types}。",
            "metrics",
            priority="P3",
            due_time=PRIORITY_DUE_TIMES["P3"],
            impact=impact_profile(server),
            impact_summary=impact_profile(server)["summary"],
            recommendation="确认只读监控账号、SSH/WinRM 连通性和采集工具是否可用，补齐失败原因后重跑主机指标采集。",
            next_actions=["检查只读监控账号部署状态。", "复核 SSH/WinRM 访问策略。", "重跑主机指标采集并对比结果。"],
            review_required=True,
            evidence_strength="needs-review",
        )
    ]


def evaluate_application_observations(server: dict[str, Any], existing_findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    observations = server.get("application_observation") if isinstance(server.get("application_observation"), list) else []
    findings: list[dict[str, Any]] = []
    has_runtime_critical = any(
        item.get("severity") == "critical" and item.get("category") in {"network", "service"}
        for item in existing_findings
    )
    for observation in observations:
        if not isinstance(observation, dict):
            continue
        status = str(observation.get("status") or "").lower()
        if status == "matched":
            continue
        namespace = str(observation.get("namespace") or "未提供命名空间")
        deployment = str(observation.get("deployment") or "未提供部署名")
        expected_image = str(observation.get("expected_image") or "未提供期望镜像")
        message = str(observation.get("message") or "doops check 未返回明确结果")
        impact = impact_profile(server)
        if status == "mismatch":
            severity = "critical" if has_runtime_critical else "warning"
            priority = "P1" if severity == "critical" and is_core_server(server) else "P2" if severity == "critical" or is_core_server(server) else "P3"
            findings.append(
                finding(
                    severity,
                    "应用部署版本与清单不一致",
                    f"doops check 显示 {namespace}/{deployment} 镜像与清单不一致；期望镜像：{expected_image}；结果：{message}",
                    "application",
                    priority=priority,
                    due_time=PRIORITY_DUE_TIMES.get(priority, "复核确认"),
                    impact=impact,
                    impact_summary=impact["summary"],
                    recommendation="核对 Kubernetes Deployment 当前镜像、最近发布记录和回滚状态；如确认为计划内变更，应更新清单基线。",
                    next_actions=["核对发布单和镜像标签。", "确认是否存在灰度或回滚。", "如非预期版本，按变更流程修正部署。"],
                    review_required=severity != "critical",
                    evidence_strength="strong" if observation.get("returncode") is not None else "needs-review",
                )
            )
        elif status == "failed":
            findings.append(
                finding(
                    "warning",
                    "应用一致性无法确认，需复核",
                    f"doops check 未能确认 {namespace}/{deployment} 镜像一致性；期望镜像：{expected_image}；结果：{message}",
                    "application",
                    priority="P3",
                    due_time=PRIORITY_DUE_TIMES["P3"],
                    impact=impact,
                    impact_summary=impact["summary"],
                    recommendation="确认 doops check 参数、Kubernetes 命名空间、Deployment 名称和采集节点权限后重跑。",
                    next_actions=["复核 application_checks 清单字段。", "确认 doops 采集节点可访问集群。", "重跑应用一致性检查。"],
                    review_required=True,
                    evidence_strength="needs-review",
                )
            )
    return findings


def number_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def default_impact() -> dict[str, Any]:
    return {"summary": "业务影响未在清单中提供，需由业务侧确认。"}


def finding(
    severity: str,
    title: str,
    evidence: str,
    category: str,
    **extra: Any,
) -> dict[str, Any]:
    priority = str(extra.pop("priority", "P2" if severity == "critical" else "P3" if severity == "warning" else "P4"))
    due_time = str(extra.pop("due_time", PRIORITY_DUE_TIMES.get(priority, "")))
    impact = extra.pop("impact", default_impact())
    impact_summary = str(extra.pop("impact_summary", impact.get("summary") if isinstance(impact, dict) else "业务影响未在清单中提供，需由业务侧确认。"))
    recommendation = str(extra.pop("recommendation", "按证据边界复核资产清单和运行状态后继续处置。"))
    next_actions = extra.pop("next_actions", ["复核资产清单和当前运行证据。"])
    if not isinstance(next_actions, list):
        next_actions = [str(next_actions)]
    payload = {
        "severity": severity,
        "title": title,
        "evidence": evidence,
        "category": category,
        "priority": priority,
        "due_time": due_time,
        "impact": impact,
        "impact_summary": impact_summary,
        "recommendation": recommendation,
        "next_actions": [str(action) for action in next_actions],
        "review_required": bool(extra.pop("review_required", severity == "warning")),
        "evidence_strength": str(extra.pop("evidence_strength", "strong" if severity == "critical" else "needs-review")),
    }
    payload.update(extra)
    return payload


def operational_finding(severity: str, title: str, evidence: str, category: str, server: dict[str, Any] | None = None) -> dict[str, Any]:
    server = server or {}
    priority = "P1" if severity == "critical" and is_core_server(server) else "P2" if severity == "critical" else "P3"
    impact = impact_profile(server)
    return finding(
        severity,
        title,
        evidence,
        category,
        priority=priority,
        due_time=PRIORITY_DUE_TIMES.get(priority, ""),
        impact=impact,
        impact_summary=impact["summary"],
        recommendation="复核主机指标、关键服务状态和最近变更，必要时安排容量或服务恢复处置。",
        next_actions=["确认指标采集时间点和主机负载。", "检查相关服务、日志和最近变更。", "处置后重跑巡检确认恢复。"],
        review_required=severity != "critical",
        evidence_strength="strong",
    )


def rollup_status(findings: list[dict[str, Any]], default: str = "healthy") -> str:
    severities = {item.get("severity") for item in findings}
    if "critical" in severities:
        return "critical"
    if "warning" in severities:
        return "warning"
    if default == "unknown":
        return "unknown"
    return "healthy"


def server_priority(findings: list[dict[str, Any]]) -> str:
    order = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}
    priorities = [str(item.get("priority") or "") for item in findings if item.get("severity") != "info"]
    if not priorities:
        return ""
    return min(priorities, key=lambda item: order.get(item, 99))


def summarize_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    clean = sanitize_mapping(metrics if isinstance(metrics, dict) else {})
    allowed = {}
    for key in ("cpu_percent", "memory_percent", "load_per_core", "uptime_days", "disks"):
        if key in clean:
            allowed[key] = clean[key]
    return allowed


def summarize_services(services: list[Any]) -> list[dict[str, Any]]:
    clean_services = []
    for item in services if isinstance(services, list) else []:
        if isinstance(item, dict):
            clean_services.append(
                {
                    "name": str(item.get("name") or "service"),
                    "status": str(item.get("status") or item.get("state") or "unknown"),
                    "expected": str(item.get("expected") or "running"),
                }
            )
    return clean_services


def summarize_processes(processes: list[Any]) -> list[dict[str, Any]]:
    clean_processes = []
    for item in processes if isinstance(processes, list) else []:
        if not isinstance(item, dict):
            continue
        process = {
            "name": str(item.get("name") or "process")[:80],
            "state": str(item.get("state") or "unknown")[:32],
        }
        pid = item.get("pid")
        if isinstance(pid, int):
            process["pid"] = pid
        if item.get("user") is not None:
            process["user"] = str(item.get("user") or "")[:32]
        for key in ("cpu_percent", "memory_percent", "cpu_seconds", "memory_mb"):
            value = item.get(key)
            if isinstance(value, (int, float)):
                process[key] = value
        clean_processes.append(process)
    return sorted(
        clean_processes,
        key=lambda item: (float(item.get("cpu_percent") or 0), float(item.get("memory_percent") or 0), float(item.get("memory_mb") or 0)),
        reverse=True,
    )[:30]


def default_auth_security(status: str = "not_enabled", window_days: int = 7, method: str = "unavailable") -> dict[str, Any]:
    return {
        "status": status,
        "window_days": int(window_days or 7),
        "method": method,
        "log_evidence": {
            "failed_login_count": 0,
            "successful_login_count": 0,
            "unique_source_count": 0,
            "top_sources": [],
            "top_users": [],
            "patterns": [],
        },
        "protection_config": {
            "password_login_enabled": None,
            "root_login_enabled": None,
            "max_auth_tries": None,
            "account_lockout_enabled": None,
            "fail2ban_enabled": None,
            "rdp_nla_enabled": None,
            "winrm_basic_enabled": None,
            "audit_policy_enabled": None,
        },
        "password_strength": {
            "status": "not_enabled",
            "weak_count": 0,
            "medium_count": 0,
            "strong_count": 0,
            "reuse_group_count": 0,
            "findings": [],
        },
    }


def summarize_auth_security(value: Any) -> dict[str, Any]:
    clean = default_auth_security()
    if not isinstance(value, dict):
        return clean
    clean["status"] = str(value.get("status") or "not_enabled")
    clean["window_days"] = int(number_or_none(value.get("window_days")) or 7)
    clean["method"] = str(value.get("method") or "unavailable")
    log_evidence = value.get("log_evidence") if isinstance(value.get("log_evidence"), dict) else {}
    for key in ("failed_login_count", "successful_login_count", "unique_source_count"):
        clean["log_evidence"][key] = int(number_or_none(log_evidence.get(key)) or 0)
    for key, item_key in (("top_sources", "source"), ("top_users", "user")):
        rows = []
        for item in log_evidence.get(key, []) if isinstance(log_evidence.get(key), list) else []:
            if isinstance(item, dict):
                rows.append({item_key: str(item.get(item_key) or "unknown")[:80], "count": int(number_or_none(item.get("count")) or 0)})
        clean["log_evidence"][key] = rows[:10]
    patterns = []
    for item in log_evidence.get("patterns", []) if isinstance(log_evidence.get("patterns"), list) else []:
        if isinstance(item, dict):
            patterns.append(sanitize_mapping(item))
    clean["log_evidence"]["patterns"] = patterns[:20]
    protection = value.get("protection_config") if isinstance(value.get("protection_config"), dict) else {}
    for key in clean["protection_config"]:
        if key in protection:
            clean["protection_config"][key] = protection.get(key)
    strength = value.get("password_strength") if isinstance(value.get("password_strength"), dict) else {}
    clean["password_strength"]["status"] = str(strength.get("status") or "not_enabled")
    for key in ("weak_count", "medium_count", "strong_count", "reuse_group_count"):
        clean["password_strength"][key] = int(number_or_none(strength.get(key)) or 0)
    findings = []
    for item in strength.get("findings", []) if isinstance(strength.get("findings"), list) else []:
        if isinstance(item, dict):
            findings.append(
                {
                    "account": str(item.get("account") or "")[:80],
                    "severity": str(item.get("severity") or "unknown")[:32],
                    "rule": str(item.get("rule") or "")[:240],
                }
            )
    clean["password_strength"]["findings"] = findings[:20]
    if strength.get("source"):
        clean["password_strength"]["source"] = str(strength.get("source"))[:80]
    return clean


def summarize_collection_errors(errors: Any) -> list[dict[str, str]]:
    clean_errors = []
    for item in errors if isinstance(errors, list) else []:
        if isinstance(item, dict):
            clean_errors.append(
                {
                    "stage": str(item.get("stage") or "host-metrics")[:80],
                    "type": str(item.get("type") or item.get("error") or "unknown")[:120],
                }
            )
    return clean_errors


def evidence_boundary(server: dict[str, Any], offline: bool) -> str:
    if offline:
        return "仅离线清单验证；本次未连接服务器。"
    collect = server.get("collect", {}) if isinstance(server.get("collect", {}), dict) else {}
    if collect.get("self_node_metrics"):
        target = collect.get("doops_target") or server.get("address") or "doops"
        return f"通过 doops 工作区直接采集 {target} doops 节点自身 CPU、内存、磁盘、负载、主要进程和服务状态；无需 SSH/WinRM/SNMP，也未读取目标业务服务器账号。"
    if collect.get("host_metrics"):
        method = str(collect.get("metrics_method") or "not-supported")
        target = collect.get("metrics_probe_target") or "unknown"
        status = collect.get("host_metrics_status") or "failed"
        if status == "collected":
            return f"通过 doops 目标 {target} 从内网使用 {method} 只读采集主机指标、磁盘、主要进程与服务状态；未展示或保存账号、密码、私钥或连接令牌。"
        if collect.get("doops_probe") or server.get("network_observation"):
            return f"已通过 doops 目标 {target} 完成网络可达性探测，但主机指标无法监测；未展示或保存账号、密码、私钥或连接令牌。"
        return f"已尝试通过 doops 目标 {target} 使用 {method} 只读采集主机指标，结果无法监测；未展示或保存账号、密码、私钥或连接令牌。"
    if collect.get("doops_probe"):
        return f"通过 doops 目标 {collect.get('probe_target') or 'unknown'} 从内网只读探测服务器网络与端口可达性；未展示或保存连接令牌。"
    if collect.get("doops"):
        return "通过 doops 只读进入目标环境并采集主机指标、磁盘、主要进程与服务状态；未展示或保存连接令牌。"
    if server.get("credential_status") in {"not-provided", "reference-only"}:
        return "仅网络层检查；除非清单已提供指标，否则不代表主机内部状态。"
    return "检测到凭证引用；本次仍按只读方式记录已采集的健康证据。"


def host_metrics_coverage(servers: list[dict[str, Any]]) -> dict[str, str]:
    self_metric_servers = [
        server
        for server in servers
        if isinstance(server.get("collect"), dict) and server.get("collect", {}).get("self_node_metrics")
    ]
    host_metric_servers = [
        server
        for server in servers
        if isinstance(server.get("collect"), dict) and server.get("collect", {}).get("host_metrics")
    ]
    has_metrics = any(server.get("metrics") for server in servers)
    has_services = any(server.get("services") for server in servers)
    has_processes = any(server.get("processes") for server in servers)
    has_doops = any(isinstance(server.get("collect"), dict) and server.get("collect", {}).get("doops") for server in servers)
    if self_metric_servers and not host_metric_servers:
        self_metrics_collected = all(server.get("metrics") for server in self_metric_servers)
        self_services_collected = all(server.get("services") for server in self_metric_servers)
        self_processes_collected = all(server.get("processes") for server in self_metric_servers)
        return {
            "host_metrics": "doops-self-collected" if self_metrics_collected else "partial-host-metrics",
            "services": "doops-self-collected" if self_services_collected else "not-supplied",
            "processes": "doops-self-collected" if self_processes_collected else "not-supplied",
        }
    if not host_metric_servers:
        return {
            "host_metrics": "doops-collected" if has_doops and has_metrics else "inventory-supplied" if has_metrics else "not-supplied",
            "services": "doops-collected" if has_doops and has_services else "inventory-supplied" if has_services else "not-supplied",
            "processes": "doops-collected" if has_doops and has_processes else "inventory-supplied" if has_processes else "not-supplied",
        }

    collected = [
        server
        for server in host_metric_servers
        if server.get("metrics") and server.get("collect", {}).get("host_metrics_status") == "collected"
    ]
    attempted_methods = {str(server.get("collect", {}).get("metrics_method") or "") for server in host_metric_servers}
    collected_with_processes = [server for server in collected if server.get("processes")]
    if not collected or len(collected) != len(host_metric_servers):
        if attempted_methods == {"snmpv3"}:
            return {
                "host_metrics": "partial-snmp-metrics",
                "services": "not-supplied" if not has_services else "partial-snmp-metrics",
                "processes": "not-supplied" if not has_processes else "partial-snmp-metrics",
            }
        return {
            "host_metrics": "partial-host-metrics",
            "services": "partial-host-metrics",
            "processes": "partial-host-metrics" if collected_with_processes else "not-supplied",
        }

    methods = {str(server.get("collect", {}).get("metrics_method") or "") for server in collected}
    if methods == {"snmpv3"}:
        label = "snmp-collected"
    elif "ssh" in methods and "winrm" in methods:
        label = "ssh-winrm-collected"
    elif "winrm" in methods:
        label = "winrm-collected"
    elif "ssh" in methods:
        label = "ssh-collected"
    else:
        label = "partial-host-metrics"
    return {
        "host_metrics": label,
        "services": label if has_services else "not-supplied",
        "processes": label if len(collected_with_processes) == len(collected) and label != "snmp-collected" else "inventory-supplied" if has_processes else "not-supplied",
    }


def auth_security_summary(servers: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(servers)
    enabled = covered = brute_force = weak = protection_gap = uncovered = 0
    for server in servers:
        auth_security = summarize_auth_security(server.get("auth_security", {}))
        status = str(auth_security.get("status") or "not_enabled")
        if status != "not_enabled":
            enabled += 1
        if status in {"collected", "partial"}:
            covered += 1
        if status in {"unavailable", "partial"}:
            uncovered += 1
        log_evidence = auth_security.get("log_evidence", {}) if isinstance(auth_security.get("log_evidence"), dict) else {}
        patterns = log_evidence.get("patterns", []) if isinstance(log_evidence.get("patterns"), list) else []
        failed = int(number_or_none(log_evidence.get("failed_login_count")) or 0)
        if failed >= 50 or any(
            isinstance(pattern, dict) and pattern.get("type") in {"failed-then-success", "source-password-spray", "distributed-account-attack"}
            for pattern in patterns
        ):
            brute_force += 1
        strength = auth_security.get("password_strength", {}) if isinstance(auth_security.get("password_strength"), dict) else {}
        if int(number_or_none(strength.get("weak_count")) or 0) > 0:
            weak += 1
        protection = auth_security.get("protection_config", {}) if isinstance(auth_security.get("protection_config"), dict) else {}
        if protection.get("password_login_enabled") is True and protection.get("account_lockout_enabled") in {False, None}:
            protection_gap += 1
        if protection.get("root_login_enabled") is True and protection.get("password_login_enabled") is True:
            protection_gap += 1
        if protection.get("winrm_basic_enabled") is True and protection.get("allow_unencrypted") is True:
            protection_gap += 1
    return {
        "enabled_servers": enabled,
        "covered_servers": covered,
        "brute_force_servers": brute_force,
        "weak_password_servers": weak,
        "protection_gap_servers": protection_gap,
        "uncovered_servers": uncovered,
        "coverage": "not-supplied" if enabled == 0 else "auth-security-collected" if total and covered == total else "partial-auth-security",
    }


def sorted_actionable_findings(servers: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    severity_rank = {"critical": 0, "warning": 1, "info": 2}
    priority_rank = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
    pairs = [
        (server, item)
        for server in servers
        for item in server.get("findings", [])
        if isinstance(item, dict) and item.get("severity") != "info"
    ]
    return sorted(
        pairs,
        key=lambda pair: (
            priority_rank.get(str(pair[1].get("priority") or ""), 9),
            severity_rank.get(str(pair[1].get("severity") or ""), 9),
            str(pair[0].get("name") or ""),
        ),
    )


def build_risk_queue(servers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queue = []
    for server, item in sorted_actionable_findings(servers)[:8]:
        queue.append(
            {
                "server": server.get("name") or "",
                "address": server.get("address") or "",
                "severity": item.get("severity") or "warning",
                "severity_label": severity_label(str(item.get("severity") or "")),
                "priority": item.get("priority") or "-",
                "due_time": item.get("due_time") or "-",
                "title": item.get("title") or "",
                "evidence": item.get("evidence") or "",
                "recommendation": item.get("recommendation") or "",
                "review_required": bool(item.get("review_required")),
                "evidence_strength": item.get("evidence_strength") or "-",
            }
        )
    if queue:
        return queue
    return [
        {
            "server": "全部服务器",
            "address": "",
            "severity": "info",
            "severity_label": "信息",
            "priority": "观察",
            "due_time": "按计划复测",
            "title": "当前检查范围内未形成处置队列",
            "evidence": "未发现严重或预警级运行健康问题；仍需按证据边界补齐未覆盖项。",
            "recommendation": "保留本次报告作为基线，下一轮巡检继续对比趋势。",
            "review_required": False,
            "evidence_strength": "baseline",
        }
    ]


def build_coverage_gaps(servers: list[dict[str, Any]], coverage: dict[str, str]) -> list[str]:
    gaps = []
    if coverage.get("host_metrics") == "doops-self-collected":
        if coverage.get("network") == "offline-simulated":
            gaps.append("网络探测处于离线模拟模式，不能作为生产可达性结论。")
        return gaps or ["本次为 zheyin doops 节点自身监测，未发现需要补采的关键证据。"]
    if coverage.get("network") == "offline-simulated":
        gaps.append("网络探测处于离线模拟模式，不能作为生产可达性结论。")
    if coverage.get("host_metrics") in {"not-supplied", "partial-host-metrics", "partial-snmp-metrics"}:
        gaps.append("主机 CPU、内存、磁盘等指标未完全覆盖，容量和性能判断需要补采。")
    if coverage.get("services") in {"not-supplied", "partial-host-metrics"}:
        gaps.append("关键服务状态未完全覆盖，进程、数据库和应用健康仍需结合业务侧证据确认。")
    if coverage.get("processes") in {"not-supplied", "partial-host-metrics", "partial-snmp-metrics"}:
        gaps.append("主要进程列表未完全覆盖，无法定位高 CPU、高内存或异常进程来源。")
    return gaps or ["本次报告未发现明显覆盖缺口；建议按周期保留同口径复测。"]


def build_metric_insights(servers: list[dict[str, Any]], coverage: dict[str, str]) -> list[str]:
    if coverage.get("host_metrics") == "doops-self-collected":
        prefix = "doops 节点自身监测："
    else:
        prefix = ""
    if coverage.get("host_metrics") == "not-supplied":
        return ["本次未采集主机指标；报告只说明网络或清单证据，不能判断 CPU、内存、磁盘和负载健康。"]
    if coverage.get("host_metrics") == "partial-host-metrics":
        return ["主机指标为部分覆盖；未采集成功的服务器应优先核对只读监控账号、SSH/WinRM 策略和采集节点访问路径。"]

    if coverage.get("host_metrics") == "partial-snmp-metrics":
        return ["SNMPv3 主机指标为部分覆盖；未采集成功的服务器应优先核对 UDP 161 可达性、SNMPv3 用户、auth/priv 参数和采集节点工具。"]

    insights = []
    cpu_items = []
    memory_items = []
    disk_items = []
    for server in servers:
        metrics = server.get("metrics") if isinstance(server.get("metrics"), dict) else {}
        if isinstance(metrics.get("cpu_percent"), (int, float)):
            cpu_items.append((float(metrics["cpu_percent"]), server.get("name") or ""))
        if isinstance(metrics.get("memory_percent"), (int, float)):
            memory_items.append((float(metrics["memory_percent"]), server.get("name") or ""))
        for disk in metrics.get("disks", []) if isinstance(metrics.get("disks"), list) else []:
            if isinstance(disk, dict) and isinstance(disk.get("used_percent"), (int, float)):
                disk_items.append((float(disk["used_percent"]), server.get("name") or "", disk.get("mount") or "磁盘"))
    if cpu_items:
        value, name = max(cpu_items)
        insights.append(f"{prefix}CPU 最高为 {name} 的 {value:.1f}%，建议结合业务高峰继续观察。")
    if memory_items:
        value, name = max(memory_items)
        insights.append(f"{prefix}内存最高为 {name} 的 {value:.1f}%，如接近阈值需排查进程和缓存占用。")
    if disk_items:
        value, name, mount = max(disk_items)
        insights.append(f"{prefix}磁盘使用率最高为 {name} 的 {mount}：{value:.1f}%，建议纳入容量趋势跟踪。")
    return insights or [f"{prefix}已采集主机指标，但未发现超过阈值的容量或性能异常。"]


def build_evidence_confidence(servers: list[dict[str, Any]], coverage: dict[str, str], summary: dict[str, Any]) -> dict[str, Any]:
    score = 92
    reasons = [f"网络探测：{coverage_label(coverage.get('network', ''))}。"]
    if coverage.get("network") == "offline-simulated":
        score -= 20
        reasons.append("离线模式不能替代实时网络探测。")
    if coverage.get("host_metrics") == "not-supplied":
        score -= 14
        reasons.append("缺少主机指标，性能和容量判断受限。")
    elif coverage.get("host_metrics") in {"partial-host-metrics", "partial-snmp-metrics"}:
        score -= 10
        reasons.append("主机指标只覆盖部分服务器。")
    else:
        reasons.append(f"主机指标：{coverage_label(coverage.get('host_metrics', ''))}。")
        if coverage.get("host_metrics") == "doops-self-collected":
            reasons.append("doops 节点自身指标由 doops 工作区直接采集，无需 SSH/WinRM/SNMP 凭证。")
    if coverage.get("services") == "not-supplied":
        score -= 8
        reasons.append("缺少服务状态，应用层健康需要另行确认。")
    elif coverage.get("services") == "partial-host-metrics":
        score -= 6
        reasons.append("服务状态只覆盖部分服务器。")
    if summary.get("review_required_findings", 0):
        score -= min(12, int(summary.get("review_required_findings", 0)) * 3)
        reasons.append("存在需要人工复核的发现项。")
    score = max(0, min(100, score))
    if score >= 85:
        level = "高"
    elif score >= 65:
        level = "中"
    else:
        level = "有限"
    return {"score": score, "level": level, "reasons": reasons}


def build_action_board(risk_queue: list[dict[str, Any]], gaps: list[str]) -> list[dict[str, Any]]:
    urgent = [
        f"{item['server']}：{item['title']}，{item['due_time']}。"
        for item in risk_queue
        if item.get("priority") in {"P1", "P2"}
    ][:4]
    if not urgent:
        urgent = ["当前无 P1/P2 处置项；保持巡检基线并关注覆盖缺口。"]
    review = [
        f"{item['server']}：{item['title']}。"
        for item in risk_queue
        if item.get("review_required")
    ][:4]
    if not review:
        review = ["未形成单独复核队列；按证据边界复核关键资产即可。"]
    return [
        {"track": "立即处置", "items": urgent},
        {"track": "复核确认", "items": review},
        {"track": "补齐证据", "items": gaps[:4]},
    ]


def build_reading_map() -> list[dict[str, str]]:
    return [
        {"section": "管理简报", "purpose": "先读结论、证据可信度和质量分。"},
        {"section": "风险队列", "purpose": "按优先级找到最需要处理的服务器。"},
        {"section": "覆盖缺口", "purpose": "确认哪些结论还不能由本次证据支撑。"},
        {"section": "处置行动板", "purpose": "把发现项转成工单、复核和补采动作。"},
        {"section": "技术证据", "purpose": "展开查看端口、指标、主要进程、服务和采集边界。"},
    ]


ADVANCED_REPORT_SECTIONS = (
    ("decision_summary", "decision-summary", "决策摘要"),
    ("risk_heatmap", "risk-heatmap", "风险热力"),
    ("owner_brief", "owner-brief", "优先级简报"),
    ("sla_timeline", "sla-timeline", "SLA 时间线"),
    ("evidence_ladder", "evidence-ladder", "证据阶梯"),
    ("data_quality", "data-quality-panel", "数据质量"),
    ("remediation_roadmap", "remediation-roadmap", "处置路线图"),
    ("change_watchlist", "change-watchlist", "变更观察"),
    ("service_health", "service-health-panel", "服务健康"),
    ("process_health", "process-health-panel", "进程健康"),
    ("capacity_summary", "capacity-panel", "容量概览"),
    ("asset_segments", "asset-segmentation", "资产分层"),
    ("business_impact", "business-impact-panel", "业务影响"),
    ("control_checklist", "control-checklist", "控制核查"),
    ("work_order_actions", "work-order-actions", "工单动作"),
    ("appendix_index", "appendix-index", "附录索引"),
    ("readability_score", "readability-score", "可读性评分"),
    ("report_narrative", "report-narrative", "报告叙事"),
    ("review_questions", "review-questions", "复核问题"),
    ("scope_statement", "scope-statement", "范围声明"),
    ("next_report_plan", "next-report-plan", "下期计划"),
)


ADVANCED_SECTION_LABELS = {key: title for key, _, title in ADVANCED_REPORT_SECTIONS}


def build_advanced_insights(
    report: dict[str, Any],
    risk_queue: list[dict[str, Any]],
    coverage_gaps: list[str],
    metric_insights: list[str],
    evidence_confidence: dict[str, Any],
    quality_score: int,
) -> dict[str, Any]:
    summary = report["summary"]
    servers = report["servers"]
    coverage = summary["coverage"]
    trend = summary.get("trend", {})
    os_counts: dict[str, int] = {}
    missing_fields = {"业务影响": 0, "预期端口": 0}
    service_total = service_abnormal = service_unknown = 0
    process_total = process_abnormal = 0
    top_processes: list[dict[str, Any]] = []
    capacity_signals: list[dict[str, Any]] = []
    for server in servers:
        os_type = str(server.get("os_type") or "unknown")
        os_counts[os_type] = os_counts.get(os_type, 0) + 1
        if not str(server.get("impact_note") or "").strip():
            missing_fields["业务影响"] += 1
        if not server.get("network", {}).get("ports"):
            missing_fields["预期端口"] += 1
        for service in server.get("services", []) if isinstance(server.get("services"), list) else []:
            service_total += 1
            state = str(service.get("status") or "").lower()
            expected = str(service.get("expected") or "running").lower()
            if not state or state == "unknown":
                service_unknown += 1
            elif state != expected:
                service_abnormal += 1
        for process in server.get("processes", []) if isinstance(server.get("processes"), list) else []:
            if not isinstance(process, dict):
                continue
            process_total += 1
            state = str(process.get("state") or "").lower()
            cpu_value = process.get("cpu_percent")
            memory_value = process.get("memory_percent")
            if state.startswith("z") or "zombie" in state or "defunct" in state:
                process_abnormal += 1
            if isinstance(cpu_value, (int, float)) or isinstance(memory_value, (int, float)):
                top_processes.append(
                    {
                        "server": server.get("name") or "",
                        "name": process.get("name") or "process",
                        "pid": process.get("pid") or "",
                        "cpu_percent": float(cpu_value) if isinstance(cpu_value, (int, float)) else 0,
                        "memory_percent": float(memory_value) if isinstance(memory_value, (int, float)) else 0,
                        "state": process.get("state") or "unknown",
                    }
                )
        metrics = server.get("metrics") if isinstance(server.get("metrics"), dict) else {}
        if isinstance(metrics.get("cpu_percent"), (int, float)):
            capacity_signals.append({"server": server.get("name") or "", "metric": "CPU", "value": float(metrics["cpu_percent"])})
        if isinstance(metrics.get("memory_percent"), (int, float)):
            capacity_signals.append({"server": server.get("name") or "", "metric": "内存", "value": float(metrics["memory_percent"])})
        for disk in metrics.get("disks", []) if isinstance(metrics.get("disks"), list) else []:
            if isinstance(disk, dict) and isinstance(disk.get("used_percent"), (int, float)):
                capacity_signals.append(
                    {
                        "server": server.get("name") or "",
                        "metric": f"磁盘 {disk.get('mount') or disk.get('name') or ''}".strip(),
                        "value": float(disk["used_percent"]),
                    }
                )
    priority_counts = summary.get("priority_counts", {})
    risk_heatmap = [
        {
            "priority": priority,
            "critical": sum(
                1
                for server in servers
                if str(server.get("priority") or "") == priority and str(server.get("status") or "") == "critical"
            ),
            "warning": sum(
                1
                for server in servers
                if str(server.get("priority") or "") == priority and str(server.get("status") or "") == "warning"
            ),
            "review_required": sum(
                1
                for server in servers
                for item in server.get("findings", [])
                if str(item.get("priority") or "") == priority and item.get("review_required")
            ),
            "total": int(priority_counts.get(priority, 0)),
        }
        for priority in ("P1", "P2", "P3", "P4")
    ]
    data_quality_score = max(0, 100 - sum(missing_fields.values()) * 5)
    urgent_items = [item for item in risk_queue if item.get("priority") in {"P1", "P2"}]
    capacity_signals.sort(key=lambda item: float(item.get("value") or 0), reverse=True)
    top_processes.sort(key=lambda item: (float(item.get("cpu_percent") or 0), float(item.get("memory_percent") or 0)), reverse=True)
    return {
        "decision_summary": [
            f"总体状态：{status_label(summary['overall_status'])}",
            f"优先处置：{risk_queue[0]['server']} - {risk_queue[0]['title']}",
            f"证据可信度：{evidence_confidence.get('level')} / {evidence_confidence.get('score')}",
        ],
        "risk_heatmap": risk_heatmap,
        "owner_brief": {
            "priority_counts": [{"name": name, "count": int(priority_counts.get(name, 0))} for name in ("P1", "P2", "P3", "P4")],
            "handoff_hint": "按优先级和建议处理时限派发，先处理 P1/P2，再处理需复核项。",
        },
        "sla_timeline": [
            {"priority": "P1", "due_time": "当日处理", "count": int(priority_counts.get("P1", 0)), "focus": "恢复或确认业务影响"},
            {"priority": "P2", "due_time": "两个工作日内处理", "count": int(priority_counts.get("P2", 0)), "focus": "排期修复与复核确认"},
            {"priority": "P3/P4", "due_time": "复核确认或补齐清单", "count": int(priority_counts.get("P3", 0)) + int(priority_counts.get("P4", 0)), "focus": "补证、复核和下期对比"},
        ],
        "evidence_ladder": [
            {"layer": "网络探测", "coverage": coverage_label(coverage.get("network", "")), "meaning": "判断端口和路径可达性"},
            {"layer": "主机指标", "coverage": coverage_label(coverage.get("host_metrics", "")), "meaning": "判断 CPU、内存、磁盘和负载健康"},
            {"layer": "主要进程", "coverage": coverage_label(coverage.get("processes", "not-supplied")), "meaning": "定位高 CPU、高内存和异常进程状态"},
            {"layer": "服务状态", "coverage": coverage_label(coverage.get("services", "")), "meaning": "判断数据库和应用服务状态"},
            {"layer": "趋势对比", "coverage": str(trend.get("summary") or "本次为基线巡检"), "meaning": "识别新增、恢复和持续问题"},
        ],
        "data_quality": {
            "score": data_quality_score,
            "missing_fields": missing_fields,
            "gaps": coverage_gaps,
            "summary": f"清单数据质量 {data_quality_score} 分；缺失项会影响业务影响面和端口证据判断。",
        },
        "remediation_roadmap": [
            {
                "phase": "今日",
                "focus": "确认 P1/P2 风险和业务影响",
                "items": [f"{item.get('server')}：{item.get('title')}" for item in urgent_items[:3]] or ["当前无 P1/P2，保持复测窗口。"],
            },
            {
                "phase": "两个工作日",
                "focus": "完成修复、复核和工单闭环",
                "items": [f"{item.get('server')}：{item.get('recommendation') or item.get('title')}" for item in risk_queue[:3]],
            },
            {"phase": "下期巡检", "focus": "补齐证据并形成趋势对比", "items": coverage_gaps[:3]},
        ],
        "change_watchlist": [
            {"label": "新增问题", "count": int(trend.get("new_findings", 0)), "hint": "优先判断是否与近期变更相关"},
            {"label": "已恢复问题", "count": int(trend.get("resolved_findings", 0)), "hint": "确认恢复证据并关闭工单"},
            {"label": "持续问题", "count": int(trend.get("persistent_findings", 0)), "hint": "需要升级处置或补充根因分析"},
            {"label": "状态变化服务器", "count": int(trend.get("status_changed_servers", 0)), "hint": "复核服务窗口和变更记录"},
        ],
        "service_health": {
            "coverage": coverage_label(coverage.get("services", "")),
            "total": service_total,
            "abnormal": service_abnormal,
            "unknown": service_unknown,
            "summary": "未提供服务状态；应用层健康需结合业务侧证据确认。"
            if service_total == 0
            else f"已记录 {service_total} 个服务状态，其中 {service_abnormal} 个未达预期，{service_unknown} 个未知。",
        },
        "process_health": {
            "coverage": coverage_label(coverage.get("processes", "not-supplied")),
            "total": process_total,
            "abnormal": process_abnormal,
            "top_processes": top_processes[:8],
            "summary": "未采集主要进程列表；无法定位高 CPU、高内存或异常进程来源。"
            if process_total == 0
            else f"已记录 {process_total} 个主要进程，其中 {process_abnormal} 个存在异常状态；高占用进程已在技术证据中展示。",
        },
        "capacity_summary": {
            "summary": metric_insights[0] if metric_insights else "本次未形成容量指标摘要。",
            "top_signals": capacity_signals[:5],
            "watch_hint": "容量指标缺失时，不得把网络可达判断写成主机性能健康结论。",
        },
        "asset_segments": [
            {"segment": "操作系统", "items": [{"name": name, "count": count} for name, count in os_counts.items()]},
        ],
        "business_impact": {
            "core_assets": sum(1 for server in servers if is_core_server(server)),
            "missing_impact": missing_fields["业务影响"],
            "summary": f"{missing_fields['业务影响']} 台服务器缺少业务影响说明，需由业务侧确认。",
        },
        "control_checklist": [
            {"item": "敏感信息未入报告", "state": "已审计", "action": "质量审计扫描密码、会话凭据、私钥和接口密钥。"},
            {"item": "只读采集", "state": "已声明", "action": "证据边界中说明只读路径和未覆盖项。"},
            {"item": "导览图存在", "state": "已审计", "action": "HTML 表头必须展示 GPT 或 HTML/CSS 导览图。"},
            {"item": "趋势对比", "state": str(trend.get("summary") or "基线巡检"), "action": "下一轮沿用 JSON 作为上一期。"},
        ],
        "work_order_actions": [
            {
                "server": str(item.get("server") or ""),
                "priority": str(item.get("priority") or "-"),
                "due_time": str(item.get("due_time") or "-"),
                "content": f"{item.get('server')}｜{item.get('priority')}｜{item.get('title')}｜{item.get('due_time')}｜{item.get('recommendation')}",
            }
            for item in risk_queue[:6]
        ],
        "appendix_index": [
            {"artifact": "final-report.html", "purpose": "正式可视化报告入口"},
            {"artifact": "final-report.pdf", "purpose": "归档和流转版本"},
            {"artifact": "final-report.json", "purpose": "结构化证据和系统集成数据"},
            {"artifact": "quality-audit.json", "purpose": "机器可读质量审计结果"},
            {"artifact": "delivery-manifest.md", "purpose": "交付包入口清单"},
        ],
        "readability_score": {
            "score": quality_score,
            "level": "可交付" if quality_score >= 70 else "需复核",
            "signals": ["结论、风险、优先级、证据和附录按阅读顺序组织。", "桌面保留矩阵密度，移动端提供卡片视图。", "高级模块使用键值和列表版式，不以 JSON 作为正文主视觉。"],
        },
        "report_narrative": ["先看总体状态与优先队列，再按证据边界决定是否补采主机指标。", "网络可达性不等同于业务或主机内部健康。"],
        "review_questions": ["采集路径是否由安全策略允许？", "主机只读账号或 SNMPv3 用户是否已部署？", "业务端口清单是否完整？"],
        "scope_statement": {
            "included": f"{summary['server_count']} 台服务器、网络/端口证据、已提供的主机指标、主要进程和服务状态。",
            "excluded": "未授权登录操作、密码读取、破坏性变更、未提供凭证的主机内部状态。",
            "boundary": "网络层检查不能替代主机级持续监控；缺失证据以覆盖缺口呈现。",
        },
        "next_report_plan": ["补齐未覆盖主机指标", "确认业务影响和端口清单", "与下期报告进行趋势对比"],
    }


def build_report_insights(report: dict[str, Any]) -> dict[str, Any]:
    summary = report["summary"]
    servers = report["servers"]
    coverage = summary["coverage"]
    risk_queue = build_risk_queue(servers)
    coverage_gaps = build_coverage_gaps(servers, coverage)
    metric_insights = build_metric_insights(servers, coverage)
    evidence_confidence = build_evidence_confidence(servers, coverage, summary)
    quality_score = max(
        0,
        min(
            100,
            evidence_confidence["score"]
            - int(summary.get("critical_findings", 0)) * 6
            - int(summary.get("warning_findings", 0)) * 3,
        ),
    )
    executive_brief = [
        f"本次覆盖 {summary['server_count']} 台服务器，总体状态为{status_label(summary['overall_status'])}。",
        f"严重 {summary['critical_findings']} 项，预警 {summary['warning_findings']} 项，需复核 {summary.get('review_required_findings', 0)} 项。",
        f"证据可信度为{evidence_confidence['level']}，质量分 {quality_score} 分。",
        f"首要动作：{risk_queue[0]['server']} - {risk_queue[0]['title']}。",
    ]
    advanced = build_advanced_insights(report, risk_queue, coverage_gaps, metric_insights, evidence_confidence, quality_score)
    return {
        "executive_brief": executive_brief,
        "risk_queue": risk_queue,
        "evidence_confidence": evidence_confidence,
        "coverage_gaps": coverage_gaps,
        "metric_insights": metric_insights,
        "action_board": build_action_board(risk_queue, coverage_gaps),
        "reading_map": build_reading_map(),
        "quality_score": quality_score,
        "advanced": advanced,
    }


def build_report(inventory: dict[str, Any], offline: bool, timeout: float, previous_report: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = normalize_inventory(inventory)
    servers = [inspect_server(server, normalized["thresholds"], offline, timeout) for server in normalized["servers"]]
    all_findings = [finding_item for server in servers for finding_item in server["findings"]]
    status_counts = {status: sum(1 for server in servers if server["status"] == status) for status in ("healthy", "warning", "critical", "unknown")}
    has_doops = any(server.get("collect", {}).get("doops") for server in normalized["servers"])
    has_doops_probe = any(server.get("collect", {}).get("doops_probe") or server.get("network_observation") for server in normalized["servers"])
    metrics_coverage = host_metrics_coverage(normalized["servers"])
    auth_summary = auth_security_summary(servers)
    coverage = {
        "network": "offline-simulated" if offline else "doops-network-probe" if has_doops_probe else "doops-collected" if has_doops else "live-tcp-probe",
        "host_metrics": metrics_coverage["host_metrics"],
        "services": metrics_coverage["services"],
        "processes": metrics_coverage.get("processes", "not-supplied"),
        "auth_security": auth_summary["coverage"],
    }
    overall_status = rollup_status(all_findings, "unknown" if not servers or offline else "healthy")
    priority_counts = {
        priority: sum(1 for item in all_findings if item.get("priority") == priority and item.get("severity") != "info")
        for priority in ("P1", "P2", "P3", "P4")
    }
    trend = compare_trend(servers, previous_report)
    report = {
        "report_kind": "server-health",
        "generated_at": now_iso(),
        "environment": normalized["environment"],
        "summary": {
            "overall_status": overall_status,
            "server_count": len(servers),
            "status_counts": status_counts,
            "critical_findings": sum(1 for item in all_findings if item["severity"] == "critical"),
            "warning_findings": sum(1 for item in all_findings if item["severity"] == "warning"),
            "review_required_findings": sum(1 for item in all_findings if item.get("review_required")),
            "priority_counts": priority_counts,
            "coverage": coverage,
            "trend": trend,
            "doops_channel": normalized.get("doops_channel", {}),
            "ai_review": normalized.get("ai_review", {}),
            "inventory_groups": normalized.get("inventory_groups", {}),
            "auth_security": auth_summary if auth_summary.get("enabled_servers") else {},
        },
        "servers": servers,
        "thresholds": normalized["thresholds"],
    }
    report["management_conclusion"] = management_conclusion(report)
    report["summary"]["management_summary"] = report["management_conclusion"]
    report["summary"]["report_insights"] = build_report_insights(report)
    return report


def find_doops(doops_path: str | None = None) -> str:
    if doops_path:
        return doops_path
    return os.environ.get("DOOPS_BIN") or shutil.which("doops") or str(Path.home() / ".local" / "bin" / "doops")


def ai_review_prompt(report: dict[str, Any], scope: str) -> str:
    findings = []
    for server in report.get("servers", []):
        if not isinstance(server, dict):
            continue
        for item in server.get("findings", []) if isinstance(server.get("findings"), list) else []:
            if isinstance(item, dict) and item.get("severity") != "info":
                findings.append(
                    {
                        "server": server.get("name"),
                        "severity": item.get("severity"),
                        "priority": item.get("priority"),
                        "title": item.get("title"),
                        "evidence": item.get("evidence"),
                    }
                )
    payload = {
        "scope": scope,
        "overall_status": report.get("summary", {}).get("overall_status"),
        "coverage": report.get("summary", {}).get("coverage"),
        "findings": findings[:50] if scope == "findings" else findings[:10],
    }
    return (
        "请作为运维报告复核助手，基于以下已脱敏 findings 给出处置建议。"
        "不得改变状态、严重等级、优先级、处理时限或证据强度，只输出复核建议。\n"
        + json.dumps(payload, ensure_ascii=False)
    )


def apply_doops_ai_review(report: dict[str, Any], doops_target: str, scope: str, doops_path: str | None = None, timeout: int = 120) -> None:
    doops = find_doops(doops_path)
    prompt = ai_review_prompt(report, scope)
    result = subprocess.run(
        [doops, "ask", "--target", doops_target, "--prompt", prompt],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    report["summary"]["ai_review"] = {
        "status": "collected" if result.returncode == 0 else "failed",
        "target": doops_target,
        "scope": scope,
        "advice": redact_text(result.stdout if result.returncode == 0 else result.stderr, limit=4000),
        "note": "AI 辅助复核只作为处置建议，不作为故障事实证据。",
    }


def finding_stable_key(server: dict[str, Any], item: dict[str, Any]) -> str:
    address = str(server.get("address") or server.get("name") or "")
    port = str(item.get("port") or "")
    title = str(item.get("title") or "")
    category = str(item.get("category") or "")
    return "|".join([address, port, category, title])


def flatten_finding_keys(servers: list[dict[str, Any]]) -> set[str]:
    keys = set()
    for server in servers:
        for item in server.get("findings", []) if isinstance(server.get("findings", []), list) else []:
            if isinstance(item, dict) and item.get("severity") != "info":
                keys.add(finding_stable_key(server, item))
    return keys


def compare_trend(servers: list[dict[str, Any]], previous_report: dict[str, Any] | None) -> dict[str, Any]:
    if not previous_report:
        return {
            "mode": "baseline",
            "summary": "本次为基线巡检，暂无趋势对比。",
            "new_findings": 0,
            "resolved_findings": 0,
            "persistent_findings": 0,
            "status_changed_servers": 0,
        }
    previous_servers = previous_report.get("servers", []) if isinstance(previous_report, dict) else []
    if not isinstance(previous_servers, list):
        previous_servers = []
    current_keys = flatten_finding_keys(servers)
    previous_keys = flatten_finding_keys(previous_servers)
    current_status = {str(server.get("address") or server.get("name")): server.get("status") for server in servers}
    previous_status = {str(server.get("address") or server.get("name")): server.get("status") for server in previous_servers if isinstance(server, dict)}
    status_changed = sum(1 for key, value in current_status.items() if key in previous_status and previous_status[key] != value)
    return {
        "mode": "compared",
        "summary": "已与上一期报告对比。",
        "new_findings": len(current_keys - previous_keys),
        "resolved_findings": len(previous_keys - current_keys),
        "persistent_findings": len(current_keys & previous_keys),
        "status_changed_servers": status_changed,
    }


def management_conclusion(report: dict[str, Any]) -> str:
    status = report["summary"]["overall_status"]
    coverage = report["summary"]["coverage"]
    summary = report["summary"]
    trend = summary.get("trend", {})
    doops_channel = summary.get("doops_channel", {}) if isinstance(summary.get("doops_channel"), dict) else {}
    inventory_groups = summary.get("inventory_groups", {}) if isinstance(summary.get("inventory_groups"), dict) else {}
    self_target = str(doops_channel.get("target") or "zheyin")
    group_text = ""
    if inventory_groups:
        group_text = (
            f"清单分层：原始清单共 {inventory_groups.get('total_servers', 0)} 台；"
            f"仍在使用 {inventory_groups.get('active_servers', 0)} 台，已停用 {inventory_groups.get('inactive_servers', 0)} 台；"
            f"仍在使用中可正常监测 CPU/内存等主机指标 {inventory_groups.get('monitorable_servers', 0)} 台，"
            f"不可正常监测 {inventory_groups.get('unmonitorable_servers', 0)} 台。"
        )
    coverage_text = (
        f"本次覆盖 {summary['server_count']} 台服务器；网络探测为{coverage_label(coverage['network'])}，"
        f"主机指标为{coverage_label(coverage['host_metrics'])}，主要进程为{coverage_label(coverage.get('processes', 'not-supplied'))}，"
        f"服务状态为{coverage_label(coverage['services'])}。"
    )
    if coverage.get("host_metrics") == "doops-self-collected":
        coverage_text = (
            f"本次覆盖 {summary['server_count']} 个 doops 节点；当前范围为 {self_target} doops 节点自身监测，"
            f"直接采集 CPU、内存、磁盘、负载、主要进程和关键服务状态，不依赖 SSH/WinRM/SNMP。"
        )
    risk_text = (
        f"风险概览：严重 {summary['critical_findings']} 项，预警 {summary['warning_findings']} 项，"
        f"需复核 {summary.get('review_required_findings', 0)} 项；"
        f"P1 {summary['priority_counts'].get('P1', 0)} 项，P2 {summary['priority_counts'].get('P2', 0)} 项，P3 {summary['priority_counts'].get('P3', 0)} 项。"
    )
    boundary_text = "证据边界：网络层探测不能替代主机性能、进程、数据库或业务服务状态；未覆盖项需要在后续巡检中补齐。"
    if coverage["host_metrics"] != "not-supplied" or coverage["services"] != "not-supplied":
        boundary_text = "证据边界：报告按已采集证据判定，未覆盖的主机或服务仍需结合业务侧证据复核。"
    if coverage.get("host_metrics") == "doops-self-collected":
        boundary_text = (
            f"证据边界：本报告能判断 {self_target} doops 节点自身运行状态；"
            "不代表 Excel 清单内其他普通服务器的 CPU、内存、磁盘或业务服务状态。"
        )
    action_text = "首要建议：先复核端口来源和业务端口清单，再按优先级推进主机级采集、业务影响确认和处置闭环。"
    if coverage.get("host_metrics") == "doops-self-collected":
        action_text = "首要建议：将本次结果作为 zheyin doops 节点自身健康基线，后续按相同命令定期采集并对比 CPU、内存、磁盘、主要进程和服务状态趋势。"
    trend_text = trend.get("summary") or "本次为基线巡检，暂无趋势对比。"
    if status == "critical":
        lead = "至少一台服务器存在需要运维立即复核的严重证据。"
    if status == "warning":
        lead = "环境总体具备可检查基础，但存在应排期跟进的预警或需确认事项。"
    if coverage["network"] == "offline-simulated":
        lead = "这是一份离线验证报告；形成生产结论前，应补充实时网络探测、主机指标或服务状态。"
    if status == "unknown":
        lead = "当前证据不完整；建议补充网络访问、主机指标或服务状态后再下结论。"
    if status == "healthy":
        lead = "在本次检查范围内，未发现严重或预警级服务器运行健康证据。"
    if coverage.get("host_metrics") == "doops-self-collected" and status == "healthy":
        lead = f"在本次检查范围内，{self_target} doops 节点自身 CPU、内存、磁盘、主要进程和关键服务状态未发现严重或预警级异常。"
    return "\n".join([item for item in [lead, group_text, coverage_text, risk_text, boundary_text, trend_text, action_text] if item])


def render_streamlined_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    coverage = summary["coverage"]
    inventory_groups = summary.get("inventory_groups", {}) if isinstance(summary.get("inventory_groups"), dict) else {}
    core_overview = build_core_metric_overview(report)
    service_overview = build_key_service_overview(report)
    lines = [
        f"# {report['environment']['name']} 服务器运行健康报告",
        "",
        f"- 生成时间：{display_timestamp(report['generated_at'])}",
        f"- 总体状态：{status_label(summary['overall_status'])}",
        f"- 服务器数量：{summary['server_count']}",
        f"- 严重问题：{summary['critical_findings']}",
        f"- 预警问题：{summary['warning_findings']}",
        f"- 需复核问题：{summary.get('review_required_findings', 0)}",
        "",
        "## 管理结论",
        "",
        report["management_conclusion"],
        "",
    ]
    if inventory_groups:
        lines.extend(
            [
                "## 清单分层摘要",
                "",
                f"- 原始清单服务器总数：{inventory_groups.get('total_servers', 0)}",
                f"- 仍在使用：{inventory_groups.get('active_servers', 0)}",
                f"- 已停用：{inventory_groups.get('inactive_servers', 0)}",
                f"- 可正常监测 CPU/内存等运行状态：{inventory_groups.get('monitorable_servers', 0)}",
                f"- 不可正常监测 CPU/内存等运行状态：{inventory_groups.get('unmonitorable_servers', 0)}",
                "",
            ]
        )
    lines.extend(["## 核心指标", ""])
    for card in core_overview.get("cards", []):
        lines.append(
            f"- {escape_md(card.get('label', '指标'))}：{escape_md(card.get('value', '未采集'))}（{escape_md(card.get('note', ''))}）"
        )
    lines.extend(["", "## 关键服务", ""])
    lines.append(f"- 覆盖口径：{escape_md(service_overview.get('coverage', '未提供'))}")
    lines.append(f"- 结论：{escape_md(service_overview.get('message', '本次未形成关键服务摘要。'))}")
    for card in service_overview.get("cards", []):
        lines.append(
            f"- {escape_md(card.get('label', '服务'))}：{escape_md(card.get('value', '未采集'))}（{escape_md(card.get('note', ''))}）"
        )
    rows = service_overview.get("rows", []) if isinstance(service_overview.get("rows"), list) else []
    if rows:
        lines.extend(["", "| 服务器 | 服务 | 状态 | 预期 |", "| --- | --- | --- | --- |"])
        for row in rows:
            lines.append(
                "| {server} | {name} | {status} | {expected} |".format(
                    server=escape_md(row.get("server", "")),
                    name=escape_md(row.get("name", "")),
                    status=escape_md(row.get("status", "")),
                    expected=escape_md(row.get("expected", "")),
                )
            )
    else:
        lines.append("- 说明：需要服务状态时，请在采集侧补充关键服务清单或启用可读取服务状态的只读通道。")
    lines.append("")
    doops_channel = summary.get("doops_channel", {}) if isinstance(summary.get("doops_channel"), dict) else {}
    if doops_channel:
        lines.extend(
            [
                "## doops 采集通道",
                "",
                f"- 目标：{escape_md(doops_channel.get('target') or '未提供')}",
                f"- Session：{escape_md(doops_channel.get('session') or '未提供')}",
                f"- 传输模式：{escape_md(doops_channel.get('transport_mode') or '未提供')}",
                f"- 在线状态：{'在线' if doops_channel.get('target_online') else '离线或未确认'}",
                f"- 工作区清理：{escape_md(doops_channel.get('cleanup_status') or '未提供')}",
                "",
            ]
        )
    ai_review = summary.get("ai_review", {}) if isinstance(summary.get("ai_review"), dict) else {}
    if ai_review:
        lines.extend(
            [
                "## AI 辅助复核",
                "",
                "- 说明：AI 辅助复核只作为处置建议，不作为故障事实证据，不改变状态、严重等级、优先级和处理时限。",
                f"- 状态：{escape_md(ai_review.get('status') or '未提供')}",
                f"- 范围：{escape_md(ai_review.get('scope') or '未提供')}",
                f"- 建议：{escape_md(ai_review.get('advice') or ai_review.get('output') or '未提供')}",
                "",
            ]
        )
    application_lines = []
    for server in report["servers"]:
        observations = server.get("application_observation") if isinstance(server.get("application_observation"), list) else []
        for observation in observations:
            if not isinstance(observation, dict):
                continue
            application_lines.append(
                f"- {escape_md(server['name'])}：{escape_md(observation.get('status') or 'unknown')}；"
                f"{escape_md(observation.get('namespace') or '-')}/{escape_md(observation.get('deployment') or '-')}"
            )
    if application_lines:
        lines.extend(["## 应用一致性", "", *application_lines, ""])
    lines.extend(["## 服务器矩阵", ""])
    lines.append("| 服务器 | 地址 | 业务角色 | 状态 | CPU | 内存 | 磁盘最高占用 | 主要进程数 | 优先级 | 建议处理时限 | 证据边界 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for server in report["servers"]:
        metrics = server.get("metrics") if isinstance(server.get("metrics"), dict) else {}
        disks = metrics.get("disks") if isinstance(metrics.get("disks"), list) else []
        disk_values = [float(item["used_percent"]) for item in disks if isinstance(item, dict) and isinstance(item.get("used_percent"), (int, float))]
        processes = server.get("processes") if isinstance(server.get("processes"), list) else []
        lines.append(
            "| {name} | {address} | {role} | {status} | {cpu} | {memory} | {disk} | {processes} | {priority} | {due_time} | {boundary} |".format(
                name=escape_md(server["name"]),
                address=escape_md(server["address"]),
                role=escape_md(server["role"]),
                status=status_label(server["status"]),
                cpu=escape_md(f"{float(metrics['cpu_percent']):.1f}%" if isinstance(metrics.get("cpu_percent"), (int, float)) else "未采集"),
                memory=escape_md(f"{float(metrics['memory_percent']):.1f}%" if isinstance(metrics.get("memory_percent"), (int, float)) else "未采集"),
                disk=escape_md(f"{max(disk_values):.1f}%" if disk_values else "未采集"),
                processes=escape_md(str(len(processes)) if processes else "未采集"),
                priority=escape_md(server.get("priority") or "-"),
                due_time=escape_md(server.get("due_time") or "-"),
                boundary=escape_md("已采集主机指标" if metrics else "仅网络/端口证据" if server.get("network", {}).get("ports") else "证据不足"),
            )
        )
    lines.extend(["", "## 问题与建议", ""])
    findings = [(server["name"], item) for server in report["servers"] for item in server["findings"] if item["severity"] != "info"]
    if not findings:
        lines.append("在当前检查范围内未发现严重或预警级问题。")
    for server_name, item in findings:
        review_text = "；需复核" if item.get("review_required") else ""
        lines.append(
            f"- **{severity_label(item['severity'])}** `{escape_md(server_name)}` {escape_md(item['title'])}"
            f"（优先级：{escape_md(item.get('priority') or '-')}；时限：{escape_md(item.get('due_time') or '-')}；证据强度：{escape_md(item.get('evidence_strength') or '-')}{review_text}）"
        )
        lines.append(f"  - 证据：{escape_md(item['evidence'])}")
        lines.append(f"  - 影响：{escape_md(item.get('impact_summary') or '业务影响未在清单中提供，需由业务侧确认。')}")
        lines.append(f"  - 建议：{escape_md(item.get('recommendation') or '')}")
        actions = item.get("next_actions") if isinstance(item.get("next_actions"), list) else []
        if actions:
            lines.append(f"  - 下一步：{escape_md('；'.join(str(action) for action in actions))}")
    trend = summary.get("trend", {})
    lines.extend(
        [
            "",
            "## 趋势与证据边界",
            "",
            f"- 趋势状态：{escape_md(trend.get('summary') or '本次为基线巡检，暂无趋势对比。')}",
            f"- 新增/恢复/持续问题：{trend.get('new_findings', 0)} / {trend.get('resolved_findings', 0)} / {trend.get('persistent_findings', 0)}",
        ]
    )
    for key, value in coverage.items():
        lines.append(f"- {coverage_key_label(key)}：{coverage_label(value)}")
    return "\n".join(lines).strip() + "\n"


def render_markdown(report: dict[str, Any]) -> str:
    if is_compact_self_node_report(report):
        return render_compact_self_node_markdown(report)
    return render_streamlined_markdown(report)
    insights = report["summary"].get("report_insights", {})
    inventory_groups = report["summary"].get("inventory_groups", {}) if isinstance(report["summary"].get("inventory_groups"), dict) else {}
    lines = [
        f"# {report['environment']['name']} 服务器运行健康报告",
        "",
        f"- 生成时间：{display_timestamp(report['generated_at'])}",
        f"- 总体状态：{status_label(report['summary']['overall_status'])}",
        f"- 服务器数量：{report['summary']['server_count']}",
        f"- 严重问题：{report['summary']['critical_findings']}",
        f"- 预警问题：{report['summary']['warning_findings']}",
        f"- 需复核问题：{report['summary'].get('review_required_findings', 0)}",
        "",
        "## 管理结论",
        "",
        report["management_conclusion"],
        "",
        "## 管理简报",
        "",
    ]
    if inventory_groups:
        lines.extend(
            [
                "## 清单分层摘要",
                "",
                f"- 原始清单服务器总数：{inventory_groups.get('total_servers', 0)}",
                f"- 仍在使用：{inventory_groups.get('active_servers', 0)}",
                f"- 已停用：{inventory_groups.get('inactive_servers', 0)}",
                f"- 可正常监测 CPU/内存等运行状态：{inventory_groups.get('monitorable_servers', 0)}",
                f"- 不可正常监测 CPU/内存等运行状态：{inventory_groups.get('unmonitorable_servers', 0)}",
                "",
            ]
        )
    for item in insights.get("executive_brief", []):
        lines.append(f"- {escape_md(item)}")
    confidence = insights.get("evidence_confidence", {})
    lines.extend(
        [
            "",
            f"- 证据可信度：{escape_md(confidence.get('level', '未评估'))}（{confidence.get('score', 0)} 分）",
            f"- 报告质量分：{insights.get('quality_score', 0)}",
            "",
            "## 风险队列",
            "",
        ]
    )
    for item in insights.get("risk_queue", []):
        lines.append(
            f"- `{escape_md(item.get('priority', '-'))}` {escape_md(item.get('server', ''))}："
            f"{escape_md(item.get('title', ''))}（{escape_md(item.get('due_time', '-'))}）"
        )
    lines.extend(["", "## 覆盖缺口", ""])
    for item in insights.get("coverage_gaps", []):
        lines.append(f"- {escape_md(item)}")
    lines.extend(["", "## 处置行动板", ""])
    for track in insights.get("action_board", []):
        lines.append(f"- {escape_md(track.get('track', ''))}：{escape_md('；'.join(track.get('items', [])))}")
    lines.extend(
        [
            "",
        "## 检查覆盖范围",
        "",
        ]
    )
    advanced = insights.get("advanced", {}) if isinstance(insights.get("advanced"), dict) else {}
    lines.extend(["", "## 决策摘要", ""])
    for item in markdown_items_for(advanced.get("decision_summary", [])):
        lines.append(f"- {escape_md(item)}")
    lines.extend(["", "## 优先级与时限", ""])
    owner_brief = advanced.get("owner_brief", {}) if isinstance(advanced.get("owner_brief"), dict) else {}
    if owner_brief.get("handoff_hint"):
        lines.append(f"- {escape_md(owner_brief.get('handoff_hint'))}")
    for item in markdown_items_for(advanced.get("sla_timeline", [])):
        lines.append(f"- {escape_md(item)}")
    lines.extend(["", "## 证据与数据质量", ""])
    for item in markdown_items_for(advanced.get("evidence_ladder", [])):
        lines.append(f"- {escape_md(item)}")
    for item in markdown_items_for(advanced.get("data_quality", {})):
        lines.append(f"- {escape_md(item)}")
    lines.extend(["", "## 处置路线图", ""])
    for item in markdown_items_for(advanced.get("remediation_roadmap", [])):
        lines.append(f"- {escape_md(item)}")
    lines.extend(["", "## 复核问题清单", ""])
    for item in advanced.get("review_questions", []) if isinstance(advanced.get("review_questions"), list) else []:
        lines.append(f"- {escape_md(item)}")
    for key, value in report["summary"]["coverage"].items():
        lines.append(f"- {coverage_key_label(key)}：{coverage_label(value)}")
    trend = report["summary"].get("trend", {})
    lines.extend(
        [
            "",
            "## 趋势对比",
            "",
            f"- 趋势状态：{escape_md(trend.get('summary') or '本次为基线巡检，暂无趋势对比。')}",
            f"- 新增问题：{trend.get('new_findings', 0)}",
            f"- 已恢复问题：{trend.get('resolved_findings', 0)}",
            f"- 持续问题：{trend.get('persistent_findings', 0)}",
            f"- 状态变化服务器：{trend.get('status_changed_servers', 0)}",
        ]
    )
    doops_channel = report["summary"].get("doops_channel", {}) if isinstance(report["summary"].get("doops_channel"), dict) else {}
    if doops_channel:
        self_node_note = []
        if report["summary"]["coverage"].get("host_metrics") == "doops-self-collected":
            self_node_note = [
                "- 采集对象：zheyin doops 节点自身监测",
                "- 凭证边界：无需 SSH/WinRM/SNMP，未读取目标业务服务器账号",
            ]
        lines.extend(
            [
                "",
                "## doops 采集通道",
                "",
                f"- 目标：{escape_md(doops_channel.get('target') or '未提供')}",
                f"- Session：{escape_md(doops_channel.get('session') or '未提供')}",
                f"- 传输模式：{escape_md(doops_channel.get('transport_mode') or '未提供')}",
                f"- 在线状态：{'在线' if doops_channel.get('target_online') else '离线或未确认'}",
                f"- 忙碌状态：{'忙碌' if doops_channel.get('target_busy') else '未忙碌或未确认'}",
                f"- 最近心跳：{escape_md(display_timestamp(doops_channel.get('last_seen')))}",
                f"- 采集节点状态：{escape_md(doops_channel.get('collector_info_status') or '未确认')}",
                f"- 工作区清理：{escape_md(doops_channel.get('cleanup_status') or '未提供')}",
            ]
            + self_node_note
        )
    ai_review = report["summary"].get("ai_review", {}) if isinstance(report["summary"].get("ai_review"), dict) else {}
    if ai_review:
        lines.extend(
            [
                "",
                "## AI 辅助复核",
                "",
                "- 说明：AI 辅助复核只作为处置建议，不作为故障事实证据，不改变状态、严重等级、优先级和处理时限。",
                f"- 状态：{escape_md(ai_review.get('status') or '未提供')}",
                f"- 范围：{escape_md(ai_review.get('scope') or '未提供')}",
                f"- 建议：{escape_md(ai_review.get('advice') or ai_review.get('output') or '未提供')}",
            ]
        )
    lines.extend(["", "## 服务器矩阵", ""])
    lines.append("| 服务器 | 地址 | 业务角色 | 状态 | 优先级 | 建议处理时限 | 证据边界 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for server in report["servers"]:
        lines.append(
            "| {name} | {address} | {role} | {status} | {priority} | {due_time} | {boundary} |".format(
                name=escape_md(server["name"]),
                address=escape_md(server["address"]),
                role=escape_md(server["role"]),
                status=status_label(server["status"]),
                priority=escape_md(server.get("priority") or "-"),
                due_time=escape_md(server.get("due_time") or "-"),
                boundary=escape_md(server["evidence_boundary"]),
            )
        )
    lines.extend(["", "## 问题与风险", ""])
    findings = [(server["name"], item) for server in report["servers"] for item in server["findings"] if item["severity"] != "info"]
    if not findings:
        lines.append("在当前检查范围内未发现严重或预警级问题。")
    for server_name, item in findings:
        review_text = "；需复核" if item.get("review_required") else ""
        lines.append(
            f"- **{severity_label(item['severity'])}** `{escape_md(server_name)}` {escape_md(item['title'])}"
            f"（优先级：{escape_md(item.get('priority') or '-')}；时限：{escape_md(item.get('due_time') or '-')}；证据强度：{escape_md(item.get('evidence_strength') or '-')}{review_text}）"
        )
        lines.append(f"  - 证据：{escape_md(item['evidence'])}")
        lines.append(f"  - 影响：{escape_md(item.get('impact_summary') or '业务影响未在清单中提供，需由业务侧确认。')}")
        lines.append(f"  - 建议：{escape_md(item.get('recommendation') or '')}")
        actions = item.get("next_actions") if isinstance(item.get("next_actions"), list) else []
        if actions:
            lines.append(f"  - 下一步：{escape_md('；'.join(str(action) for action in actions))}")
    lines.extend(["", "## 技术证据", ""])
    for server in report["servers"]:
        lines.append(f"### {escape_md(server['name'])}")
        lines.append("")
        lines.append(f"- 网络检查模式：{coverage_label(server['network']['mode'])}")
        if server["network"]["ports"]:
            port_text = ", ".join(
                f"{port['port']}={PORT_STATUS_LABELS.get(port['status'], port['status'])}"
                f"（端口来源：{port_source_label(port.get('source'))}；用途：{port_usage_label(port.get('usage'))}）"
                for port in server["network"]["ports"]
            )
            lines.append(f"- 端口：{port_text}")
        else:
            lines.append("- 端口：未声明")
        if server["metrics"]:
            lines.append(f"- 指标：`{json.dumps(server['metrics'], ensure_ascii=False)}`")
        if server.get("processes"):
            lines.append(f"- 主要进程：`{json.dumps(server['processes'][:12], ensure_ascii=False)}`")
        if server["services"]:
            lines.append(f"- 服务：`{json.dumps(server['services'], ensure_ascii=False)}`")
        trace = server.get("collection_trace") if isinstance(server.get("collection_trace"), dict) else {}
        if trace:
            lines.append(
                "- doops 采集轨迹："
                + escape_md(
                    f"target={trace.get('doops_target') or '-'}；session={trace.get('session') or '-'}；"
                    f"transport={trace.get('transport_mode') or '-'}；cleanup={trace.get('cleanup_status') or '-'}"
                )
            )
        observations = server.get("application_observation") if isinstance(server.get("application_observation"), list) else []
        if observations:
            lines.append(f"- 应用一致性：`{json.dumps(observations, ensure_ascii=False)}`")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def is_compact_self_node_report(report: dict[str, Any]) -> bool:
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    coverage = summary.get("coverage", {}) if isinstance(summary.get("coverage"), dict) else {}
    return (
        coverage.get("host_metrics") == "doops-self-collected"
        and coverage.get("services") == "doops-self-collected"
        and int(summary.get("server_count", 0) or 0) == 1
    )


def first_server(report: dict[str, Any]) -> dict[str, Any]:
    servers = report.get("servers", []) if isinstance(report.get("servers"), list) else []
    return servers[0] if servers and isinstance(servers[0], dict) else {}


def compact_doops_channel_lines(report: dict[str, Any]) -> list[str]:
    channel = report.get("summary", {}).get("doops_channel", {})
    if not isinstance(channel, dict) or not channel:
        return ["- doops 通道：未提供"]
    online = "在线" if channel.get("target_online") else "离线或未确认"
    busy = "忙碌" if channel.get("target_busy") else "未忙碌或未确认"
    cleanup = str(channel.get("cleanup_status") or "未提供")
    lines = [
        f"- 目标：{escape_md(channel.get('target') or '未提供')}",
        f"- Session：{escape_md(channel.get('session') or '未提供')}",
        f"- 传输模式：{escape_md(channel.get('transport_mode') or '未提供')}",
        f"- 在线状态：{online}",
        f"- 忙碌状态：{busy}",
        f"- 最近心跳：{escape_md(display_timestamp(channel.get('last_seen')))}",
        f"- 采集节点状态：{escape_md(channel.get('collector_info_status') or '未确认')}",
        f"- 工作区清理：{escape_md(cleanup)}",
    ]
    if cleanup == "failed":
        lines.append("- 清理说明：doops clean 当前未成功；这只影响远端工作区清理状态，不影响已采集的 CPU、内存、磁盘和服务证据。")
    return lines


def compact_metric_lines(server: dict[str, Any]) -> list[str]:
    metrics = server.get("metrics") if isinstance(server.get("metrics"), dict) else {}
    if not metrics:
        return ["- 指标：未采集到 CPU、内存、磁盘或负载数据。"]
    lines = []
    if isinstance(metrics.get("cpu_percent"), (int, float)):
        lines.append(f"- CPU 使用率：{float(metrics['cpu_percent']):.1f}%")
    if isinstance(metrics.get("memory_percent"), (int, float)):
        lines.append(f"- 内存使用率：{float(metrics['memory_percent']):.1f}%")
    if isinstance(metrics.get("load_per_core"), (int, float)):
        lines.append(f"- 单核负载：{float(metrics['load_per_core']):.2f}")
    if isinstance(metrics.get("uptime_days"), (int, float)):
        lines.append(f"- 运行时长：{float(metrics['uptime_days']):.1f} 天")
    disks = metrics.get("disks") if isinstance(metrics.get("disks"), list) else []
    if disks:
        disk_text = []
        for disk in disks:
            if not isinstance(disk, dict):
                continue
            mount = disk.get("mount") or "磁盘"
            used = disk.get("used_percent")
            if isinstance(used, (int, float)):
                disk_text.append(f"{mount} {float(used):.1f}%")
        if disk_text:
            lines.append(f"- 磁盘使用率：{escape_md('；'.join(disk_text))}")
    return lines or ["- 指标：已采集，但未解析到可展示的 CPU、内存、磁盘或负载字段。"]


def compact_service_lines(server: dict[str, Any]) -> list[str]:
    services = server.get("services") if isinstance(server.get("services"), list) else []
    if not services:
        return ["- 服务状态：未采集到关键服务列表。"]
    lines = []
    for item in services:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or "未命名服务"
        status = item.get("status") or "unknown"
        expected = item.get("expected") or "未声明"
        lines.append(f"- {escape_md(name)}：{escape_md(status)}（期望：{escape_md(expected)}）")
    return lines or ["- 服务状态：未采集到关键服务列表。"]


def compact_process_lines(server: dict[str, Any]) -> list[str]:
    processes = server.get("processes") if isinstance(server.get("processes"), list) else []
    if not processes:
        return ["- 主要进程：未采集到进程列表。"]
    lines = []
    for item in processes[:8]:
        if not isinstance(item, dict):
            continue
        details = []
        if isinstance(item.get("cpu_percent"), (int, float)):
            details.append(f"CPU {float(item['cpu_percent']):.1f}%")
        if isinstance(item.get("memory_percent"), (int, float)):
            details.append(f"内存 {float(item['memory_percent']):.1f}%")
        elif isinstance(item.get("memory_mb"), (int, float)):
            details.append(f"内存 {float(item['memory_mb']):.1f} MB")
        if item.get("state"):
            details.append(f"状态 {item.get('state')}")
        lines.append(f"- {escape_md(process_label(item))}：{escape_md('；'.join(details) or '已观测')}")
    return lines or ["- 主要进程：未采集到进程列表。"]


def compact_trend_lines(report: dict[str, Any]) -> list[str]:
    trend = report.get("summary", {}).get("trend", {})
    if not isinstance(trend, dict):
        return ["- 本次为基线巡检，暂无趋势对比。"]
    return [
        f"- 趋势状态：{escape_md(trend.get('summary') or '本次为基线巡检，暂无趋势对比。')}",
        f"- 新增问题：{trend.get('new_findings', 0)}",
        f"- 已恢复问题：{trend.get('resolved_findings', 0)}",
        f"- 持续问题：{trend.get('persistent_findings', 0)}",
    ]


def render_compact_self_node_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    server = first_server(report)
    findings = [
        item
        for item in server.get("findings", [])
        if isinstance(item, dict) and item.get("severity") != "info"
    ]
    lines = [
        f"# {report['environment']['name']} zheyin 自身节点健康报告",
        "",
        f"- 生成时间：{display_timestamp(report['generated_at'])}",
        f"- 总体状态：{status_label(summary['overall_status'])}",
        f"- 检测对象：zheyin doops 节点自身",
        "- 证据边界：直接通过 doops 工作区采集 CPU、内存、磁盘、负载、主要进程和关键服务；无需 SSH/WinRM/SNMP；不代表 Excel 清单内其他普通服务器。",
        "",
        "## 管理结论",
        "",
        report["management_conclusion"],
        "",
        "## 核心指标",
        "",
        *compact_metric_lines(server),
        "",
        "## 主要进程",
        "",
        *compact_process_lines(server),
        "",
        "## 关键服务",
        "",
        *compact_service_lines(server),
        "",
        "## doops 通道",
        "",
        *compact_doops_channel_lines(report),
        "",
        "## 问题与建议",
        "",
    ]
    if findings:
        for item in findings:
            lines.append(
                f"- **{severity_label(item.get('severity', 'warning'))}** {escape_md(item.get('title') or '')}："
                f"{escape_md(item.get('recommendation') or item.get('evidence') or '')}"
            )
    else:
        lines.append("- 未发现严重或预警级异常；建议保留本次结果作为 zheyin 节点健康基线，后续按同口径定期对比。")
    lines.extend(["", "## 趋势", ""])
    lines.extend(compact_trend_lines(report))
    lines.extend(
        [
            "",
            "## 技术证据",
            "",
            f"- 节点名称：{escape_md(server.get('name') or '未提供')}",
            f"- 地址/目标：{escape_md(server.get('address') or 'zheyin')}",
            f"- 采集范围：{escape_md(server.get('evidence_boundary') or '未提供')}",
        ]
    )
    trace = server.get("collection_trace") if isinstance(server.get("collection_trace"), dict) else {}
    if trace:
        lines.append(
            "- 采集轨迹："
            + escape_md(
                f"target={trace.get('doops_target') or '-'}；session={trace.get('session') or '-'}；"
                f"transport={trace.get('transport_mode') or '-'}；cleanup={trace.get('cleanup_status') or '-'}"
            )
        )
    return "\n".join(lines).strip() + "\n"



def render_compact_self_node_html(report: dict[str, Any], markdown: str, guide_status: dict[str, Any]) -> str:
    summary = report["summary"]
    server = first_server(report)
    status = summary["overall_status"]
    metrics = server.get("metrics") if isinstance(server.get("metrics"), dict) else {}
    inventory_groups = summary.get("inventory_groups", {}) if isinstance(summary.get("inventory_groups"), dict) else {}
    inventory_group_html = ""
    if inventory_groups:
        inventory_group_html = """
      <section id="inventory-groups" class="fold-section">
        <div class="section-head">
          <h2>清单分层摘要</h2>
          <p class="section-note">先按是否仍在使用整理清单，再按 CPU/内存等主机指标是否可正常监测整理采集范围。</p>
        </div>
        <div class="metric-grid">
          <div class="metric-card"><span>原始清单总数</span><b>{total}</b><p>全部记录</p></div>
          <div class="metric-card"><span>仍在使用</span><b>{active}</b><p>纳入监测尝试</p></div>
          <div class="metric-card"><span>已停用</span><b>{inactive}</b><p>不进入采集</p></div>
          <div class="metric-card"><span>可正常监测</span><b>{monitorable}</b><p>生成单机报告</p></div>
          <div class="metric-card"><span>不可正常监测</span><b>{unmonitorable}</b><p>进入复核清单</p></div>
        </div>
      </section>
        """.format(
            total=html.escape(str(inventory_groups.get("total_servers", 0))),
            active=html.escape(str(inventory_groups.get("active_servers", 0))),
            inactive=html.escape(str(inventory_groups.get("inactive_servers", 0))),
            monitorable=html.escape(str(inventory_groups.get("monitorable_servers", 0))),
            unmonitorable=html.escape(str(inventory_groups.get("unmonitorable_servers", 0))),
    )
    inventory_group_html = ""
    if inventory_groups:
        inventory_group_html = """
      <section id="inventory-groups" class="fold-section">
        <div class="section-head">
          <h2>清单分层摘要</h2>
          <p class="section-note">先按是否仍在使用整理清单，再按 CPU/内存等主机指标是否可正常监测整理采集范围。</p>
        </div>
        <div class="metric-grid">
          <div class="metric-card"><span>原始清单总数</span><b>{total}</b><p>全部记录</p></div>
          <div class="metric-card"><span>仍在使用</span><b>{active}</b><p>纳入监测尝试</p></div>
          <div class="metric-card"><span>已停用</span><b>{inactive}</b><p>不进入采集</p></div>
          <div class="metric-card"><span>可正常监测</span><b>{monitorable}</b><p>生成单机报告</p></div>
          <div class="metric-card"><span>不可正常监测</span><b>{unmonitorable}</b><p>进入复核清单</p></div>
        </div>
      </section>
        """.format(
            total=html.escape(str(inventory_groups.get("total_servers", 0))),
            active=html.escape(str(inventory_groups.get("active_servers", 0))),
            inactive=html.escape(str(inventory_groups.get("inactive_servers", 0))),
            monitorable=html.escape(str(inventory_groups.get("monitorable_servers", 0))),
            unmonitorable=html.escape(str(inventory_groups.get("unmonitorable_servers", 0))),
        )
    guide_html = render_guide_visual(report, guide_status)
    generated_display = display_timestamp(report.get("generated_at"))
    conclusion_lines = [line.strip() for line in str(report.get("management_conclusion") or "").splitlines() if line.strip()]
    lead_conclusion = conclusion_lines[0] if conclusion_lines else "本次未形成管理结论。"
    conclusion_html = "\n".join(f"<p>{html.escape(line)}</p>" for line in conclusion_lines)
    lead_conclusion_html = f"<p>{html.escape(lead_conclusion)}</p>"
    guide_is_ai_image = guide_status.get("status") in {"generated", "reused"}
    cover_class = "ai-cover" if guide_is_ai_image else "fallback-cover"
    cover_kicker_html = f"""
        <div class="cover-kicker">
          <span class="status-pill"><i class="status-dot"></i>zheyin 自身节点：{html.escape(status_label(status))}</span>
          <span class="generated-at">生成时间：{html.escape(generated_display)}</span>
        </div>"""
    cover_title_html = f"""
        <p class="cover-eyebrow">{html.escape(report['environment']['name'])}</p>
        <h1>zheyin 自身节点健康报告</h1>
        <p class="cover-subtitle">面向 doops 节点自身的只读运行状态看板，聚焦 CPU、内存、磁盘、负载、主要进程、关键服务和采集链路。</p>"""
    hero_strip_html = f"""
        <div class="hero-strip">
          <div><span>严重问题</span><b>{summary['critical_findings']}</b></div>
          <div><span>预警问题</span><b>{summary['warning_findings']}</b></div>
          <div><span>需复核</span><b>{summary.get('review_required_findings', 0)}</b></div>
        </div>"""
    if guide_is_ai_image:
        cover_html = f"""
    <div class="cover-grid ai-cover-grid">
      <div class="cover-copy ai-cover-copy">
{cover_kicker_html}
{cover_title_html}
      </div>
      <div class="ai-cover-showcase">
        <div class="ai-guide-stage">
          {guide_html}
        </div>
        <aside class="ai-cover-rail">
          <div class="conclusion-panel">{lead_conclusion_html}</div>
{hero_strip_html}
        </aside>
      </div>
    </div>"""
    else:
        cover_html = f"""
    <div class="cover-grid fallback-cover-grid">
      <div class="cover-copy">
{cover_kicker_html}
{cover_title_html}
        <div class="conclusion-panel">{lead_conclusion_html}</div>
{hero_strip_html}
      </div>
      {guide_html}
    </div>"""

    def metric_display(key: str, suffix: str = "", precision: int = 1) -> str:
        value = metrics.get(key)
        if isinstance(value, (int, float)):
            return f"{float(value):.{precision}f}{suffix}"
        return "未采集"

    def metric_percent(key: str) -> int:
        value = metrics.get(key)
        if isinstance(value, (int, float)):
            return max(0, min(100, int(round(float(value)))))
        return 0

    def service_state_class(status_value: Any, expected_value: Any) -> str:
        status_text = str(status_value or "").lower()
        expected_text = str(expected_value or "").lower()
        return "ok" if status_text == expected_text == "running" else "warn"

    disk_cards = []
    for disk in metrics.get("disks", []) if isinstance(metrics.get("disks"), list) else []:
        if not isinstance(disk, dict) or not isinstance(disk.get("used_percent"), (int, float)):
            continue
        used = max(0, min(100, float(disk["used_percent"])))
        disk_cards.append(
            '<article class="metric-card disk-card"><span>{mount}</span><b>{used:.1f}%</b><div class="meter"><i style="width:{bar:.0f}%"></i></div></article>'.format(
                mount=html.escape(str(disk.get("mount") or "磁盘")),
                used=used,
                bar=used,
            )
        )
    disk_cards_html = "".join(disk_cards) or '<article class="metric-card disk-card"><span>磁盘</span><b>未采集</b><div class="meter"><i style="width:0%"></i></div></article>'
    services = server.get("services") if isinstance(server.get("services"), list) else []
    service_html = "".join(
        '<li class="{state_class}"><span>{name}</span><b>{status}</b><em>期望：{expected}</em></li>'.format(
            state_class=service_state_class(item.get("status"), item.get("expected")),
            name=html.escape(str(item.get("name") or "未命名服务")),
            status=html.escape(str(item.get("status") or "unknown")),
            expected=html.escape(str(item.get("expected") or "未声明")),
        )
        for item in services
        if isinstance(item, dict)
    )
    if not service_html:
        service_html = '<li class="warn"><span>关键服务</span><b>未采集</b><em>需复核</em></li>'
    processes = server.get("processes") if isinstance(server.get("processes"), list) else []
    process_html = "".join(
        '<li class="{state_class}"><span>{name}</span><b>{usage}</b><em>{detail}</em></li>'.format(
            state_class="warn" if str(item.get("state") or "").lower().startswith("z") else "ok",
            name=html.escape(process_label(item)),
            usage=html.escape(
                f"CPU {float(item['cpu_percent']):.1f}%"
                if isinstance(item.get("cpu_percent"), (int, float))
                else f"内存 {float(item['memory_mb']):.1f} MB"
                if isinstance(item.get("memory_mb"), (int, float))
                else "已观测"
            ),
            detail=html.escape(
                "；".join(
                    part
                    for part in [
                        f"内存 {float(item['memory_percent']):.1f}%" if isinstance(item.get("memory_percent"), (int, float)) else "",
                        f"状态 {item.get('state')}" if item.get("state") else "",
                        f"用户 {item.get('user')}" if item.get("user") else "",
                    ]
                    if part
                )
                or "主要运行进程"
            ),
        )
        for item in processes[:8]
        if isinstance(item, dict)
    )
    if not process_html:
        process_html = '<li class="warn"><span>主要进程</span><b>未采集</b><em>无法定位高占用进程来源</em></li>'
    channel_html = "".join(
        '<li><span>{key}</span><b>{value}</b></li>'.format(
            key=html.escape(str(line).lstrip("- ").split("：", 1)[0]),
            value=html.escape(str(line).lstrip("- ").split("：", 1)[1] if "：" in str(line) else str(line).lstrip("- ")),
        )
        for line in compact_doops_channel_lines(report)
    )
    trend_html = "".join(
        '<li><span>{key}</span><b>{value}</b></li>'.format(
            key=html.escape(str(line).lstrip("- ").split("：", 1)[0]),
            value=html.escape(str(line).lstrip("- ").split("：", 1)[1] if "：" in str(line) else str(line).lstrip("- ")),
        )
        for line in compact_trend_lines(report)
    )
    trace = server.get("collection_trace") if isinstance(server.get("collection_trace"), dict) else {}
    trace_text = (
        f"target={trace.get('doops_target') or '-'}；session={trace.get('session') or '-'}；"
        f"transport={trace.get('transport_mode') or '-'}；cleanup={trace.get('cleanup_status') or '-'}"
        if trace
        else "未提供"
    )
    findings = [item for item in server.get("findings", []) if isinstance(item, dict) and item.get("severity") != "info"]
    if findings:
        finding_html = "".join(
            '<li class="warn"><span>{title}</span><b>{severity}</b><em>{recommendation}</em></li>'.format(
                severity=html.escape(severity_label(str(item.get("severity") or "warning"))),
                title=html.escape(str(item.get("title") or "")),
                recommendation=html.escape(str(item.get("recommendation") or item.get("evidence") or "")),
            )
            for item in findings
        )
    else:
        finding_html = '<li class="ok"><span>未发现严重或预警级异常</span><b>正常</b><em>建议保留为基线，后续按同口径趋势对比。</em></li>'
    evidence_boundary = html.escape(str(server.get("evidence_boundary") or "通过 doops 工作区采集 zheyin 自身节点状态。"))

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(report['environment']['name'])} zheyin 自身节点健康报告</title>
  <style>
    :root {{ color-scheme: light; --ink:#172033; --muted:#667085; --line:#d7dee8; --paper:#ffffff; --soft:#f6f8fb; --good:#147a4b; --warn:#a15c00; --bad:#b42318; --accent:#1f6f8b; --amber:#f4c95d; --teal:#69d2c7; }}
    * {{ box-sizing:border-box; }}
    html {{ scroll-behavior:smooth; }}
    body {{ margin:0; font:14px/1.65 "Microsoft YaHei","Noto Sans CJK SC",Arial,sans-serif; color:var(--ink); background:#edf1f5; }}
    .guide-cover {{ padding:32px 6vw 28px; color:white; background:#14314c; }}
    .cover-grid {{ max-width:1220px; margin:0 auto; }}
    .fallback-cover-grid {{ display:grid; grid-template-columns:minmax(360px,1.05fr) minmax(310px,.72fr); gap:24px; align-items:stretch; }}
    .ai-cover {{ padding:28px 6vw 30px; }}
    .ai-cover-grid {{ display:grid; grid-template-columns:1fr; gap:18px; }}
    .cover-copy {{ min-width:0; }}
    .ai-cover-copy {{ max-width:1120px; }}
    .cover-kicker {{ display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin-bottom:14px; }}
    .status-pill {{ display:inline-flex; align-items:center; gap:7px; padding:5px 10px; border:1px solid rgba(255,255,255,.38); border-radius:999px; background:rgba(255,255,255,.12); font-size:12px; }}
    .status-dot {{ width:8px; height:8px; border-radius:50%; background:#7be0a2; box-shadow:0 0 0 4px rgba(123,224,162,.16); }}
    .generated-at {{ color:#c7d9e4; font-size:13px; }}
    .cover-eyebrow {{ margin:0 0 6px; color:#a9c2d3; font-size:13px; font-weight:700; }}
    .cover-copy h1 {{ margin:0; font-size:clamp(28px,3.6vw,42px); line-height:1.12; letter-spacing:0; max-width:760px; }}
    .ai-cover .cover-copy h1 {{ max-width:760px; font-size:clamp(34px,3.2vw,46px); line-height:1.08; }}
    .cover-subtitle {{ margin:10px 0 0; color:#cfe1ec; max-width:720px; }}
    .ai-cover .cover-subtitle {{ max-width:860px; margin-top:8px; }}
    .conclusion-panel {{ margin-top:16px; border:1px solid rgba(255,255,255,.22); border-radius:8px; padding:13px 15px; background:rgba(255,255,255,.10); max-width:780px; }}
    .conclusion-panel p {{ margin:0; color:#f2f8fb; font-size:15px; }}
    .ai-cover-showcase {{ display:grid; grid-template-columns:minmax(0,1fr) 306px; gap:16px; align-items:start; padding:14px; border:1px solid rgba(255,255,255,.42); border-radius:8px; background:#f7fafc; box-shadow:0 22px 56px rgba(5,18,32,.30); }}
    .ai-cover-rail {{ display:grid; gap:12px; align-content:start; min-width:0; }}
    .ai-cover .conclusion-panel {{ margin:0; max-width:none; min-height:0; display:flex; align-items:flex-start; padding:16px; border-color:#cfd9e6; background:#ffffff; }}
    .ai-cover .conclusion-panel p {{ color:#203044; font-size:15px; line-height:1.72; }}
    .management-detail {{ margin-top:14px; }}
    .management-detail .panel p {{ margin:0 0 8px; color:#334155; }}
    .hero-strip {{ display:grid; grid-template-columns:repeat(3,minmax(0,120px)); gap:10px; margin-top:14px; }}
    .ai-cover .hero-strip {{ margin:0; grid-template-columns:1fr; max-width:none; }}
    .hero-strip div {{ border:1px solid rgba(255,255,255,.18); border-radius:8px; padding:9px 11px; background:rgba(255,255,255,.09); }}
    .ai-cover .hero-strip div {{ display:flex; align-items:center; justify-content:space-between; gap:12px; min-height:72px; padding:13px 14px; border-color:#d4dde9; background:#edf3f8; }}
    .hero-strip span {{ display:block; color:#bdd3df; font-size:12px; }}
    .ai-cover .hero-strip span {{ color:#5c6f85; font-weight:700; }}
    .hero-strip b {{ display:block; margin-top:2px; font-size:18px; }}
    .ai-cover .hero-strip b {{ margin-top:0; color:#135f7b; font-size:28px; line-height:1; }}
    .guide-visual {{ margin:0; border:1px solid rgba(255,255,255,.24); border-radius:8px; overflow:hidden; background:rgba(255,255,255,.08); min-height:220px; display:flex; align-items:center; justify-content:center; }}
    .guide-visual img {{ width:100%; height:auto; display:block; }}
    .ai-guide-stage {{ width:100%; }}
    .ai-guide-stage .guide-visual {{ width:100%; min-height:0; aspect-ratio:3/2; border-color:#d1dbe8; background:#ffffff; }}
    .ai-guide-stage .guide-visual img {{ width:100%; height:100%; object-fit:cover; }}
    .html-guide-visual {{ padding:16px; }}
    .guide-map {{ width:100%; display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; color:#eef7fb; }}
    .guide-map-head {{ grid-column:1/-1; display:flex; justify-content:space-between; border-bottom:1px solid rgba(255,255,255,.26); padding-bottom:8px; }}
    .guide-flow {{ grid-column:1/-1; display:grid; grid-template-columns:repeat(4,1fr); gap:6px; }}
    .guide-flow span {{ height:5px; border-radius:999px; background:linear-gradient(90deg,var(--teal),var(--amber)); }}
    .guide-node {{ min-height:62px; border:1px solid rgba(255,255,255,.20); border-radius:8px; padding:10px; background:rgba(255,255,255,.10); }}
    .guide-node small {{ display:block; color:#b8d4e3; margin-bottom:4px; }}
    .report-nav {{ position:sticky; top:0; z-index:2; display:flex; gap:8px; padding:10px 6vw; background:rgba(255,255,255,.96); border-bottom:1px solid var(--line); box-shadow:0 8px 22px rgba(16,36,63,.06); overflow-x:auto; }}
    .report-nav a {{ color:var(--ink); text-decoration:none; font-weight:700; padding:7px 10px; border-radius:8px; white-space:nowrap; }}
    .report-nav a:hover {{ background:var(--soft); }}
    main {{ max-width:1220px; margin:0 auto; padding:24px 20px 46px; background:var(--paper); }}
    .fold-section {{ border-top:1px solid var(--line); padding:28px 0; }}
    .section-head {{ display:flex; justify-content:space-between; gap:18px; align-items:flex-end; margin-bottom:14px; }}
    .section-head h2 {{ margin:0; font-size:22px; }}
    .section-note {{ margin:0; color:var(--muted); max-width:620px; }}
    .metric-grid {{ display:grid; grid-template-columns:repeat(4,minmax(150px,1fr)); gap:12px; }}
    .metric-card {{ position:relative; min-height:128px; border:1px solid var(--line); border-radius:8px; padding:14px; background:#fff; box-shadow:0 10px 24px rgba(16,36,63,.06); overflow:hidden; }}
    .metric-card::before {{ content:""; position:absolute; inset:0 0 auto; height:4px; background:linear-gradient(90deg,var(--accent),var(--teal)); }}
    .metric-card span {{ color:var(--muted); display:block; font-size:13px; }}
    .metric-card b {{ display:block; margin-top:8px; font-size:30px; line-height:1.1; }}
    .metric-card small {{ display:block; margin-top:8px; color:var(--muted); }}
    .meter {{ height:7px; margin-top:14px; border-radius:999px; overflow:hidden; background:#e6ebf2; }}
    .meter i {{ display:block; height:100%; border-radius:999px; background:linear-gradient(90deg,var(--accent),var(--teal)); }}
    .two-col {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; }}
    .panel, .evidence-box {{ border:1px solid var(--line); border-radius:8px; padding:16px; background:white; box-shadow:0 8px 22px rgba(16,36,63,.05); }}
    .evidence-box {{ background:#fbfdff; }}
    ul.clean {{ list-style:none; padding:0; margin:0; display:grid; gap:9px; }}
    ul.clean li {{ display:grid; grid-template-columns:minmax(160px,1fr) auto; gap:8px 14px; align-items:center; border-bottom:1px solid var(--line); padding:0 0 10px; }}
    ul.clean li:last-child {{ border-bottom:0; padding-bottom:0; }}
    ul.clean li span {{ min-width:0; }}
    ul.clean b {{ justify-self:end; color:var(--good); }}
    ul.clean li.warn b {{ color:var(--warn); }}
    ul.clean em {{ grid-column:1/-1; color:var(--muted); font-style:normal; font-size:13px; }}
    .compact-doops-channel ul.clean li, #trend ul.clean li {{ grid-template-columns:170px 1fr; }}
    .muted {{ color:var(--muted); }}
    details {{ margin-top:12px; }}
    summary {{ cursor:pointer; font-weight:700; }}
    pre {{ overflow-x:auto; background:#111827; color:#eef2ff; padding:12px; border-radius:8px; }}
    @media print {{ body {{ background:white; }} .report-nav {{ position:static; box-shadow:none; }} main {{ max-width:none; padding:0; }} .guide-cover {{ background:#14314c; }} .metric-card,.panel,.evidence-box {{ box-shadow:none; }} }}
    @media (max-width:980px) {{ .fallback-cover-grid,.ai-cover-showcase,.two-col {{ grid-template-columns:1fr; }} .ai-cover-rail {{ grid-template-rows:auto; }} .ai-cover .hero-strip {{ grid-template-columns:repeat(3,minmax(0,1fr)); }} .metric-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} .section-head {{ display:block; }} }}
    @media (max-width:620px) {{ .guide-cover,.ai-cover {{ padding:22px 12px 24px; }} main {{ padding:18px 12px 34px; }} .hero-strip,.ai-cover .hero-strip,.metric-grid {{ grid-template-columns:1fr; }} ul.clean li,.compact-doops-channel ul.clean li,#trend ul.clean li {{ grid-template-columns:1fr; }} ul.clean b {{ justify-self:start; }} }}
  </style>
</head>
<body>
  <header class="guide-cover {cover_class}">
{cover_html}
  </header>
  <nav class="report-nav" aria-label="报告导航">
    <a href="#management">管理结论</a>
    <a href="#metrics">核心指标</a>
    <a href="#processes">主要进程</a>
    <a href="#services">关键服务</a>
    <a href="#channel">doops 通道</a>
    <a href="#findings">问题建议</a>
    <a href="#evidence">证据边界</a>
  </nav>
  <main class="compact-report">
    <section id="management" class="fold-section management-detail">
      <div class="section-head"><h2>管理结论</h2><p class="section-note">完整结论从首页下移，首页只保留一眼可读的核心状态。</p></div>
      <div class="panel">{conclusion_html}</div>
    </section>
    <section id="metrics" class="fold-section compact-metrics">
      <div class="section-head"><h2>核心指标</h2><p class="section-note">直接来自 zheyin doops 节点自身，不依赖 SSH/WinRM/SNMP。</p></div>
      <div class="metric-grid">
        <article class="metric-card"><span>CPU 使用率</span><b>{metric_display('cpu_percent', '%')}</b><div class="meter"><i style="width:{metric_percent('cpu_percent')}%"></i></div><small>节点当前计算资源压力</small></article>
        <article class="metric-card"><span>内存使用率</span><b>{metric_display('memory_percent', '%')}</b><div class="meter"><i style="width:{metric_percent('memory_percent')}%"></i></div><small>系统内存占用水平</small></article>
        <article class="metric-card"><span>单核负载</span><b>{metric_display('load_per_core', '', 2)}</b><div class="meter"><i style="width:{max(0, min(100, int(round(float(metrics.get('load_per_core', 0) or 0) * 100))))}%"></i></div><small>每核心平均负载</small></article>
        <article class="metric-card"><span>运行时长</span><b>{metric_display('uptime_days', ' 天')}</b><div class="meter"><i style="width:100%"></i></div><small>节点连续运行时间</small></article>
      </div>
      <div class="metric-grid" style="margin-top:12px">{disk_cards_html}</div>
    </section>
    <section id="processes" class="fold-section">
      <div class="section-head"><h2>主要进程</h2><p class="section-note">展示 CPU 或内存占用靠前的进程，用于定位异常来源；不展示命令行参数。</p></div>
      <div class="panel"><ul class="clean process-list">{process_html}</ul></div>
    </section>
    <section id="services" class="fold-section">
      <div class="section-head"><h2>关键服务</h2><p class="section-note">仅展示已采集到的 zheyin 节点关键服务状态。</p></div>
      <div class="panel"><ul class="clean service-list">{service_html}</ul></div>
    </section>
    <section id="channel" class="fold-section compact-doops-channel">
      <div class="section-head"><h2>doops 通道</h2><p class="section-note">展示本次采集链路和工作区状态。</p></div>
      <div class="panel"><ul class="clean">{channel_html}</ul></div>
    </section>
    <section id="findings" class="fold-section">
      <div class="section-head"><h2>问题与建议</h2><p class="section-note">只列出需要处理的异常；无异常时给出基线建议。</p></div>
      <div class="panel"><ul class="clean">{finding_html}</ul></div>
    </section>
    <section id="trend" class="fold-section">
      <div class="section-head"><h2>趋势</h2><p class="section-note">无上一期报告时，本次作为基线。</p></div>
      <div class="panel"><ul class="clean">{trend_html}</ul></div>
    </section>
    <section id="evidence" class="fold-section compact-evidence">
      <div class="section-head"><h2>证据边界</h2><p class="section-note">明确本报告能证明什么，不能证明什么。</p></div>
      <div class="two-col">
        <div class="evidence-box"><h3>已覆盖</h3><p>zheyin doops 节点自身 CPU、内存、磁盘、负载、运行时长、主要进程、关键服务和 doops 通道状态。</p></div>
        <div class="evidence-box"><h3>未覆盖</h3><p>Excel 清单内其他普通业务服务器的主机性能、业务服务状态、数据库状态和用户侧可用性。</p></div>
      </div>
      <p class="muted">采集范围：{evidence_boundary}</p>
      <p class="muted">采集轨迹：{html.escape(trace_text)}</p>
      <details><summary>Markdown 报告文本</summary><pre>{html.escape(markdown)}</pre></details>
    </section>
  </main>
</body>
</html>
"""

def escape_md(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def plain_value_summary(value: Any) -> str:
    if isinstance(value, dict):
        return "；".join(f"{key}：{plain_value_summary(nested)}" for key, nested in list(value.items())[:4]) or "暂无数据"
    if isinstance(value, list):
        return "；".join(plain_value_summary(item) for item in value[:3]) if value else "暂无数据"
    return str(value)


def markdown_items_for(value: Any) -> list[str]:
    if isinstance(value, list):
        return [plain_value_summary(item) for item in value]
    if isinstance(value, dict):
        return [f"{key}：{plain_value_summary(nested)}" for key, nested in value.items()]
    return [str(value)]


def status_label(status: str) -> str:
    return STATUS_LABELS.get(str(status), str(status))


def severity_label(severity: str) -> str:
    return SEVERITY_LABELS.get(str(severity), str(severity))


def coverage_label(value: str) -> str:
    return COVERAGE_LABELS.get(str(value), str(value))


def coverage_key_label(key: str) -> str:
    return {"network": "网络探测", "host_metrics": "主机指标", "services": "服务状态", "processes": "主要进程"}.get(str(key), str(key))


def build_core_metric_overview(report: dict[str, Any]) -> dict[str, Any]:
    servers = report.get("servers", []) if isinstance(report.get("servers"), list) else []
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    coverage = summary.get("coverage", {}) if isinstance(summary.get("coverage"), dict) else {}
    total_servers = len(servers)
    metric_servers = [server for server in servers if isinstance(server.get("metrics"), dict) and server.get("metrics")]
    process_servers = [server for server in servers if isinstance(server.get("processes"), list) and server.get("processes")]

    def metric_records(key: str) -> list[tuple[float, dict[str, Any]]]:
        records = []
        for server in metric_servers:
            metrics = server.get("metrics") if isinstance(server.get("metrics"), dict) else {}
            value = number_or_none(metrics.get(key))
            if value is not None:
                records.append((value, server))
        return records

    def average(records: list[tuple[float, dict[str, Any]]]) -> float | None:
        if not records:
            return None
        return sum(value for value, _server in records) / len(records)

    def top_record(records: list[tuple[float, dict[str, Any]]]) -> tuple[float, dict[str, Any]] | None:
        if not records:
            return None
        return max(records, key=lambda item: item[0])

    def server_name(server: dict[str, Any]) -> str:
        return str(server.get("name") or server.get("address") or "未命名服务器")

    def percent_pair(label: str, records: list[tuple[float, dict[str, Any]]]) -> dict[str, str]:
        avg_value = average(records)
        top = top_record(records)
        if avg_value is None or top is None:
            return {"label": label, "value": "未采集", "note": f"本次未取得{label.replace(' 平均/最高', '')}指标。"}
        top_value, top_server = top
        return {
            "label": label,
            "value": f"{avg_value:.1f}% / {top_value:.1f}%",
            "note": f"最高：{server_name(top_server)}。",
        }

    cpu_records = metric_records("cpu_percent")
    memory_records = metric_records("memory_percent")
    load_records = metric_records("load_per_core")
    uptime_records = metric_records("uptime_days")
    disk_records: list[tuple[float, dict[str, Any], str]] = []
    for server in metric_servers:
        metrics = server.get("metrics") if isinstance(server.get("metrics"), dict) else {}
        disks = metrics.get("disks") if isinstance(metrics.get("disks"), list) else []
        for disk in disks:
            if not isinstance(disk, dict):
                continue
            used = number_or_none(disk.get("used_percent"))
            if used is not None:
                disk_records.append((used, server, str(disk.get("mount") or disk.get("name") or "磁盘")))

    metric_rate = (len(metric_servers) / total_servers * 100) if total_servers else 0
    process_rate = (len(process_servers) / total_servers * 100) if total_servers else 0
    disk_top = max(disk_records, key=lambda item: item[0]) if disk_records else None
    load_top = top_record(load_records)
    uptime_top = top_record(uptime_records)

    cards = [
        {
            "label": "主机指标覆盖",
            "value": f"{len(metric_servers)}/{total_servers}",
            "note": f"{coverage_label(coverage.get('host_metrics', 'not-supplied'))}，覆盖率 {metric_rate:.1f}%。",
        },
        percent_pair("CPU 平均/最高", cpu_records),
        percent_pair("内存 平均/最高", memory_records),
        {
            "label": "磁盘最高占用",
            "value": f"{disk_top[0]:.1f}%" if disk_top else "未采集",
            "note": f"最高：{server_name(disk_top[1])} {disk_top[2]}。" if disk_top else "本次未取得磁盘使用率明细。",
        },
        {
            "label": "负载/核最高",
            "value": f"{load_top[0]:.2f}" if load_top else "未采集",
            "note": f"最高：{server_name(load_top[1])}。" if load_top else "本次未取得单核负载指标。",
        },
        {
            "label": "主要进程覆盖",
            "value": f"{len(process_servers)}/{total_servers}",
            "note": f"{coverage_label(coverage.get('processes', 'not-supplied'))}，覆盖率 {process_rate:.1f}%。",
        },
    ]
    if uptime_top:
        cards.append(
            {
                "label": "最长运行时长",
                "value": f"{uptime_top[0]:.1f} 天",
                "note": f"服务器：{server_name(uptime_top[1])}。",
            }
        )
    return {
        "metric_servers": len(metric_servers),
        "total_servers": total_servers,
        "process_servers": len(process_servers),
        "cards": cards,
    }


def build_key_service_overview(report: dict[str, Any]) -> dict[str, Any]:
    servers = report.get("servers", []) if isinstance(report.get("servers"), list) else []
    summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
    coverage = summary.get("coverage", {}) if isinstance(summary.get("coverage"), dict) else {}
    service_rows: list[dict[str, str]] = []
    service_servers = 0
    running = 0
    abnormal = 0
    unknown = 0
    for server in servers:
        services = server.get("services") if isinstance(server.get("services"), list) else []
        if services:
            service_servers += 1
        for service in services:
            if not isinstance(service, dict):
                continue
            state = str(service.get("status") or service.get("state") or "unknown")
            expected = str(service.get("expected") or "running")
            state_key = state.lower()
            expected_key = expected.lower()
            if not state_key or state_key == "unknown":
                row_class = "unknown"
                unknown += 1
            elif state_key == expected_key:
                row_class = "ok"
                running += 1
            else:
                row_class = "warn"
                abnormal += 1
            service_rows.append(
                {
                    "server": str(server.get("name") or server.get("address") or "未命名服务器"),
                    "name": str(service.get("name") or "未命名服务"),
                    "status": state,
                    "expected": expected,
                    "class": row_class,
                }
            )
    total = len(service_rows)
    server_total = len(servers)
    coverage_text = coverage_label(coverage.get("services", "not-supplied"))
    if total:
        visible_rows = sorted(service_rows, key=lambda item: {"warn": 0, "unknown": 1, "ok": 2}.get(item["class"], 3))[:12]
        cards = [
            {"label": "服务覆盖", "value": f"{service_servers}/{server_total}", "note": coverage_text},
            {"label": "服务总数", "value": str(total), "note": "来自已采集关键服务清单。"},
            {"label": "正常运行", "value": str(running), "note": "观测状态达到预期。"},
            {"label": "异常/未知", "value": f"{abnormal}/{unknown}", "note": "优先复核未达预期或未知状态。"},
        ]
        message = f"已采集 {service_servers} 台服务器的 {total} 个关键服务状态。"
    else:
        cards = [
            {"label": "服务覆盖", "value": f"0/{server_total}", "note": coverage_text},
            {"label": "关键服务状态", "value": "未采集", "note": "本次没有服务状态明细。"},
            {"label": "异常服务", "value": "未判断", "note": "不能仅凭 CPU/内存或端口探测判断应用服务健康。"},
        ]
        visible_rows = []
        message = "本次未采集关键服务状态；报告仅能说明已取得的主机指标、网络探测和证据边界。"
    return {
        "total": total,
        "running": running,
        "abnormal": abnormal,
        "unknown": unknown,
        "service_servers": service_servers,
        "server_total": server_total,
        "coverage": coverage_text,
        "cards": cards,
        "rows": visible_rows,
        "message": message,
    }


def advanced_value_summary(value: Any) -> str:
    if isinstance(value, dict):
        parts = []
        for key, nested in list(value.items())[:4]:
            parts.append(f"{key}：{advanced_value_summary(nested)}")
        return "；".join(parts) if parts else "暂无数据"
    if isinstance(value, list):
        if not value:
            return "暂无数据"
        return "；".join(advanced_value_summary(item) for item in value[:3])
    return str(value)


def render_advanced_item_html(item: Any) -> str:
    if isinstance(item, dict):
        pairs = "".join(
            '<div><dt>{key}</dt><dd>{value}</dd></div>'.format(
                key=html.escape(str(key)),
                value=html.escape(advanced_value_summary(value)),
            )
            for key, value in item.items()
        )
        return f'<li><dl class="advanced-kv">{pairs}</dl></li>'
    return f"<li>{html.escape(str(item))}</li>"


def render_advanced_payload_html(value: Any) -> str:
    if isinstance(value, list):
        items = "".join(render_advanced_item_html(item) for item in value)
        return f'<ul class="advanced-list">{items}</ul>'
    if isinstance(value, dict):
        pairs = "".join(
            '<div><dt>{key}</dt><dd>{value}</dd></div>'.format(
                key=html.escape(str(key)),
                value=html.escape(advanced_value_summary(nested)),
            )
            for key, nested in value.items()
        )
        return f'<dl class="advanced-kv">{pairs}</dl>'
    return f'<p>{html.escape(str(value))}</p>'


def advanced_section_signal(key: str, value: Any) -> tuple[bool, str]:
    if key == "risk_heatmap" and isinstance(value, list):
        total = sum(int(item.get("total", 0) or 0) for item in value if isinstance(item, dict))
        return total > 0, "无 P1-P4 风险项，热力表全为 0"
    if key == "sla_timeline" and isinstance(value, list):
        total = sum(int(item.get("count", 0) or 0) for item in value if isinstance(item, dict))
        return total > 0, "无处置时限项"
    if key == "change_watchlist" and isinstance(value, list):
        total = sum(int(item.get("count", 0) or 0) for item in value if isinstance(item, dict))
        return total > 0, "基线报告暂无趋势变化"
    if key == "service_health" and isinstance(value, dict):
        total = int(value.get("total", 0) or 0)
        abnormal = int(value.get("abnormal", 0) or 0)
        unknown = int(value.get("unknown", 0) or 0)
        return total > 0 or abnormal > 0 or unknown > 0, "未提供服务状态明细"
    if key == "capacity_summary" and isinstance(value, dict):
        signals = value.get("top_signals")
        return isinstance(signals, list) and bool(signals), "未提供容量指标明细"
    if key == "work_order_actions" and isinstance(value, list):
        meaningful = [
            item
            for item in value
            if isinstance(item, dict) and str(item.get("priority") or "") not in {"观察", "-", ""}
        ]
        return bool(meaningful), "无实际工单动作"
    if key == "appendix_index":
        return False, "附录索引保留在交付清单中"
    if key == "control_checklist":
        return False, "控制核查已由质量审计覆盖"
    return True, ""


def visible_advanced_sections(advanced: dict[str, Any]) -> tuple[list[tuple[str, str, str, Any]], list[str]]:
    visible = []
    hidden = []
    for key, marker, title in ADVANCED_REPORT_SECTIONS:
        value = advanced.get(key)
        show, reason = advanced_section_signal(key, value)
        if show:
            visible.append((key, marker, title, value))
        else:
            hidden.append(f"{title}：{reason}")
    return visible, hidden


def render_html(report: dict[str, Any], markdown: str, guide_status: dict[str, Any]) -> str:
    if is_compact_self_node_report(report):
        return render_compact_self_node_html(report, markdown, guide_status)
    status = report["summary"]["overall_status"]
    summary = report["summary"]
    priority_counts = summary.get("priority_counts", {})
    status_counts = summary.get("status_counts", {})
    insights = summary.get("report_insights", {})
    inventory_groups = summary.get("inventory_groups", {}) if isinstance(summary.get("inventory_groups"), dict) else {}
    confidence = insights.get("evidence_confidence", {})
    conclusion_html = "\n".join(
        f"<p>{html.escape(line.strip())}</p>"
        for line in str(report.get("management_conclusion") or "").splitlines()
        if line.strip()
    )
    def runtime_value(server: dict[str, Any], key: str, suffix: str = "%") -> str:
        metrics = server.get("metrics") if isinstance(server.get("metrics"), dict) else {}
        value = metrics.get(key)
        if isinstance(value, (int, float)):
            return f"{float(value):.1f}{suffix}"
        return "未采集"

    def disk_peak_value(server: dict[str, Any]) -> str:
        metrics = server.get("metrics") if isinstance(server.get("metrics"), dict) else {}
        disks = metrics.get("disks") if isinstance(metrics.get("disks"), list) else []
        values = [float(item["used_percent"]) for item in disks if isinstance(item, dict) and isinstance(item.get("used_percent"), (int, float))]
        return f"{max(values):.1f}%" if values else "未采集"

    def process_count_value(server: dict[str, Any]) -> str:
        processes = server.get("processes") if isinstance(server.get("processes"), list) else []
        return str(len(processes)) if processes else "未采集"

    def short_boundary(server: dict[str, Any]) -> str:
        metrics = server.get("metrics") if isinstance(server.get("metrics"), dict) else {}
        if metrics:
            return "已采集主机指标"
        if server.get("network", {}).get("ports"):
            return "仅网络/端口证据"
        return "证据不足"

    core_overview = build_core_metric_overview(report)
    core_metric_cards_html = "\n".join(
        '<article class="metric-card"><span>{label}</span><b>{value}</b><p>{note}</p></article>'.format(
            label=html.escape(str(card.get("label") or "指标")),
            value=html.escape(str(card.get("value") or "未采集")),
            note=html.escape(str(card.get("note") or "")),
        )
        for card in core_overview.get("cards", [])
        if isinstance(card, dict)
    )
    service_overview = build_key_service_overview(report)
    key_service_cards_html = "\n".join(
        '<article class="metric-card"><span>{label}</span><b>{value}</b><p>{note}</p></article>'.format(
            label=html.escape(str(card.get("label") or "服务")),
            value=html.escape(str(card.get("value") or "未采集")),
            note=html.escape(str(card.get("note") or "")),
        )
        for card in service_overview.get("cards", [])
        if isinstance(card, dict)
    )
    service_rows = service_overview.get("rows", []) if isinstance(service_overview.get("rows"), list) else []
    if service_rows:
        key_service_list_html = "<ul class=\"clean service-list\">" + "".join(
            '<li class="{state_class}"><span>{server} / {name}</span><b>{status}</b><em>预期：{expected}</em></li>'.format(
                state_class=html.escape(str(row.get("class") or "unknown")),
                server=html.escape(str(row.get("server") or "")),
                name=html.escape(str(row.get("name") or "")),
                status=html.escape(str(row.get("status") or "unknown")),
                expected=html.escape(str(row.get("expected") or "running")),
            )
            for row in service_rows
            if isinstance(row, dict)
        ) + "</ul>"
    else:
        key_service_list_html = (
            '<p class="empty-state">'
            + html.escape(str(service_overview.get("message") or "本次未采集关键服务状态。"))
            + " 如需判断应用、数据库、中间件或系统守护进程健康，请在采集侧补充关键服务清单或启用可读取服务状态的只读通道。"
            + "</p>"
        )

    auth_summary = summary.get("auth_security", {}) if isinstance(summary.get("auth_security"), dict) else {}
    auth_metric_cards_html = "\n".join(
        [
            '<article class="metric-card"><span>认证日志覆盖</span><b>{}</b><p>可读取认证日志的服务器数量</p></article>'.format(
                html.escape(str(auth_summary.get("covered_servers", 0)))
            ),
            '<article class="metric-card"><span>爆破迹象</span><b>{}</b><p>存在失败登录异常或失败后成功登录模式</p></article>'.format(
                html.escape(str(auth_summary.get("brute_force_servers", 0)))
            ),
            '<article class="metric-card"><span>弱口令风险</span><b>{}</b><p>本地强度评分发现弱口令的服务器数量</p></article>'.format(
                html.escape(str(auth_summary.get("weak_password_servers", 0)))
            ),
            '<article class="metric-card"><span>证据未覆盖</span><b>{}</b><p>日志或防护配置读取权限不足</p></article>'.format(
                html.escape(str(auth_summary.get("uncovered_servers", 0)))
            ),
        ]
    )
    auth_rows = []
    for server in report["servers"]:
        auth_security = server.get("auth_security") if isinstance(server.get("auth_security"), dict) else {}
        if str(auth_security.get("status") or "not_enabled") == "not_enabled":
            continue
        log_evidence = auth_security.get("log_evidence", {}) if isinstance(auth_security.get("log_evidence"), dict) else {}
        strength = auth_security.get("password_strength", {}) if isinstance(auth_security.get("password_strength"), dict) else {}
        protection = auth_security.get("protection_config", {}) if isinstance(auth_security.get("protection_config"), dict) else {}
        auth_rows.append(
            "<li><span>{server}</span><b>{failed} 次失败 / 弱口令 {weak}</b><em>{method}；锁定策略：{lockout}</em></li>".format(
                server=html.escape(str(server.get("name") or "")),
                failed=html.escape(str(log_evidence.get("failed_login_count", 0))),
                weak=html.escape(str(strength.get("weak_count", 0))),
                method=html.escape(str(auth_security.get("method") or "unavailable")),
                lockout=html.escape("已启用" if protection.get("account_lockout_enabled") is True else "未确认或未启用"),
            )
        )
    auth_rows_html = (
        '<ul class="clean service-list">' + "".join(auth_rows[:30]) + "</ul>"
        if auth_rows
        else '<p class="empty-state">本次未启用认证安全巡检；报告不判断密码爆破迹象、登录防护配置或本地口令强度。</p>'
    )

    server_rows = "\n".join(
        "<tr><td>{name}</td><td>{address}</td><td>{role}</td><td><span class=\"badge {status_class}\">{status}</span></td><td>{cpu}</td><td>{memory}</td><td>{disk}</td><td>{processes}</td><td>{priority}</td><td>{due_time}</td><td>{boundary}</td></tr>".format(
            name=html.escape(server["name"]),
            address=html.escape(server["address"]),
            role=html.escape(server["role"]),
            status_class=html.escape(server["status"]),
            status=html.escape(status_label(server["status"])),
            cpu=html.escape(runtime_value(server, "cpu_percent")),
            memory=html.escape(runtime_value(server, "memory_percent")),
            disk=html.escape(disk_peak_value(server)),
            processes=html.escape(process_count_value(server)),
            priority=html.escape(str(server.get("priority") or "-")),
            due_time=html.escape(str(server.get("due_time") or "-")),
            boundary=html.escape(short_boundary(server)),
        )
        for server in report["servers"]
    )
    matrix_cards = "\n".join(
        (
            "<article class=\"matrix-card {status_class}\">"
            "<div class=\"matrix-card-head\"><h3>{name}</h3><span class=\"badge {status_class}\">{status}</span></div>"
            "<dl>"
            "<div><dt>地址</dt><dd>{address}</dd></div>"
            "<div><dt>业务角色</dt><dd>{role}</dd></div>"
            "<div><dt>CPU</dt><dd>{cpu}</dd></div>"
            "<div><dt>内存</dt><dd>{memory}</dd></div>"
            "<div><dt>磁盘最高占用</dt><dd>{disk}</dd></div>"
            "<div><dt>主要进程数</dt><dd>{processes}</dd></div>"
            "<div><dt>优先级</dt><dd>{priority}</dd></div>"
            "<div><dt>处理时限</dt><dd>{due_time}</dd></div>"
            "</dl>"
            "<p>{boundary}</p>"
            "</article>"
        ).format(
            status_class=html.escape(server["status"]),
            name=html.escape(server["name"]),
            status=html.escape(status_label(server["status"])),
            address=html.escape(server["address"]),
            role=html.escape(server["role"]),
            cpu=html.escape(runtime_value(server, "cpu_percent")),
            memory=html.escape(runtime_value(server, "memory_percent")),
            disk=html.escape(disk_peak_value(server)),
            processes=html.escape(process_count_value(server)),
            priority=html.escape(str(server.get("priority") or "-")),
            due_time=html.escape(str(server.get("due_time") or "-")),
            boundary=html.escape(short_boundary(server)),
        )
        for server in report["servers"]
    )
    finding_cards = []
    for server in report["servers"]:
        actionable = [item for item in server["findings"] if item["severity"] != "info"]
        if not actionable:
            continue
        items = "".join(
            "<li>"
            "<div class=\"finding-title\"><strong>{severity}</strong><span>{title}</span></div>"
            "<div class=\"finding-meta\"><span>{priority}</span><span>{due_time}</span><span>{evidence_strength}{review}</span></div>"
            "<p><b>证据</b>{evidence}</p>"
            "<p><b>影响</b>{impact}</p>"
            "<p><b>建议</b>{recommendation}</p>"
            "</li>".format(
                severity=html.escape(severity_label(item["severity"])),
                title=html.escape(item["title"]),
                priority=html.escape(str(item.get("priority") or "-")),
                due_time=html.escape(str(item.get("due_time") or "-")),
                evidence_strength=html.escape(str(item.get("evidence_strength") or "-")),
                review="；需复核" if item.get("review_required") else "",
                evidence=html.escape(str(item.get("evidence") or "")),
                impact=html.escape(str(item.get("impact_summary") or "业务影响未在清单中提供，需由业务侧确认。")),
                recommendation=html.escape(str(item.get("recommendation") or "")),
            )
            for item in actionable
        )
        finding_cards.append(
            f"<section class=\"finding-card\"><div class=\"finding-card-head\"><h3>{html.escape(server['name'])}</h3>"
            f"<span class=\"badge {html.escape(server['status'])}\">{html.escape(status_label(server['status']))}</span></div><ul>{items}</ul></section>"
        )
    findings_html = "\n".join(finding_cards) or "<p class=\"empty-state\">在当前检查范围内未发现严重或预警级问题。</p>"
    evidence_sections = "\n".join(render_server_evidence(server) for server in report["servers"])
    coverage = report["summary"]["coverage"]
    trend = report["summary"].get("trend", {})
    doops_channel = report["summary"].get("doops_channel", {}) if isinstance(report["summary"].get("doops_channel"), dict) else {}
    ai_review = report["summary"].get("ai_review", {}) if isinstance(report["summary"].get("ai_review"), dict) else {}
    doops_channel_html = ""
    if doops_channel:
        self_node_banner = ""
        if coverage.get("host_metrics") == "doops-self-collected":
            self_node_banner = (
                "<p class=\"channel-note\"><b>zheyin 自身节点监测：</b>"
                "本次直接通过 doops 工作区采集该节点 CPU、内存、磁盘、负载和关键服务状态，"
                "无需 SSH/WinRM/SNMP，也不代表其他普通服务器主机指标。</p>"
            )
        doops_channel_html = """
      <section id="doops-channel" class="panel-block doops-channel">
        <div class="section-head"><h2>doops 采集通道</h2><p class="section-note">展示采集通道和工作区证据状态，不直接替代被巡检服务器健康结论。</p></div>
        {self_node_banner}
        <dl class="summary-kv">
          <div><dt>目标</dt><dd>{target}</dd></div>
          <div><dt>Session</dt><dd>{session}</dd></div>
          <div><dt>传输模式</dt><dd>{transport}</dd></div>
          <div><dt>在线状态</dt><dd>{online}</dd></div>
          <div><dt>忙碌状态</dt><dd>{busy}</dd></div>
          <div><dt>最近心跳</dt><dd>{last_seen}</dd></div>
          <div><dt>采集节点状态</dt><dd>{collector}</dd></div>
          <div><dt>工作区清理</dt><dd>{cleanup}</dd></div>
        </dl>
      </section>
        """.format(
            self_node_banner=self_node_banner,
            target=html.escape(str(doops_channel.get("target") or "未提供")),
            session=html.escape(str(doops_channel.get("session") or "未提供")),
            transport=html.escape(str(doops_channel.get("transport_mode") or "未提供")),
            online="在线" if doops_channel.get("target_online") else "离线或未确认",
            busy="忙碌" if doops_channel.get("target_busy") else "未忙碌或未确认",
            last_seen=html.escape(display_timestamp(doops_channel.get("last_seen"))),
            collector=html.escape(str(doops_channel.get("collector_info_status") or "未确认")),
            cleanup=html.escape(str(doops_channel.get("cleanup_status") or "未提供")),
        )
    ai_review_html = ""
    if ai_review:
        ai_review_html = """
      <section id="ai-review" class="panel-block ai-review">
        <div class="section-head"><h2>AI 辅助复核</h2><p class="section-note">仅作为处置建议，不作为故障事实证据，不改变状态、严重等级、优先级和处理时限。</p></div>
        <p>{advice}</p>
        <dl class="summary-kv"><div><dt>状态</dt><dd>{status}</dd></div><div><dt>范围</dt><dd>{scope}</dd></div></dl>
      </section>
        """.format(
            advice=html.escape(str(ai_review.get("advice") or ai_review.get("output") or "未提供")),
            status=html.escape(str(ai_review.get("status") or "未提供")),
            scope=html.escape(str(ai_review.get("scope") or "未提供")),
        )
    application_items = []
    for server in report["servers"]:
        observations = server.get("application_observation") if isinstance(server.get("application_observation"), list) else []
        for observation in observations:
            if not isinstance(observation, dict):
                continue
            application_items.append(
                "<li><strong>{server}</strong><span>{status}</span><em>{namespace}/{deployment}</em></li>".format(
                    server=html.escape(server["name"]),
                    status=html.escape(str(observation.get("status") or "unknown")),
                    namespace=html.escape(str(observation.get("namespace") or "-")),
                    deployment=html.escape(str(observation.get("deployment") or "-")),
                )
            )
    application_html = ""
    if application_items:
        application_html = """
      <section id="application-consistency" class="fold-section compact-application">
        <div class="section-head"><h2>应用一致性</h2><p class="section-note">仅展示清单显式声明的应用部署检查结果。</p></div>
        <div class="finding-card"><ul>{items}</ul></div>
      </section>
        """.format(items="".join(application_items))
    inventory_group_html = ""
    if inventory_groups:
        inventory_group_html = """
      <section id="inventory-groups" class="fold-section">
        <div class="section-head">
          <h2>清单分层摘要</h2>
          <p class="section-note">先按是否仍在使用整理清单，再按 CPU/内存等主机指标是否可正常监测整理采集范围。</p>
        </div>
        <div class="metric-grid">
          <div class="metric-card"><span>原始清单总数</span><b>{total}</b><p>全部记录</p></div>
          <div class="metric-card"><span>仍在使用</span><b>{active}</b><p>纳入监测尝试</p></div>
          <div class="metric-card"><span>已停用</span><b>{inactive}</b><p>不进入采集</p></div>
          <div class="metric-card"><span>可正常监测</span><b>{monitorable}</b><p>生成单机报告</p></div>
          <div class="metric-card"><span>不可正常监测</span><b>{unmonitorable}</b><p>进入复核清单</p></div>
        </div>
      </section>
        """.format(
            total=html.escape(str(inventory_groups.get("total_servers", 0))),
            active=html.escape(str(inventory_groups.get("active_servers", 0))),
            inactive=html.escape(str(inventory_groups.get("inactive_servers", 0))),
            monitorable=html.escape(str(inventory_groups.get("monitorable_servers", 0))),
            unmonitorable=html.escape(str(inventory_groups.get("unmonitorable_servers", 0))),
        )
    guide_html = render_guide_visual(report, guide_status)
    generated_display = display_timestamp(report.get("generated_at"))
    conclusion_lines = [line.strip() for line in str(report.get("management_conclusion") or "").splitlines() if line.strip()]
    lead_conclusion = conclusion_lines[0] if conclusion_lines else "本次未形成管理结论。"
    lead_conclusion_html = f"<p>{html.escape(lead_conclusion)}</p>"
    guide_is_ai_image = guide_status.get("status") in {"generated", "reused"}
    cover_class = "ai-cover" if guide_is_ai_image else "fallback-cover"
    active_count = inventory_groups.get("active_servers") if inventory_groups else None
    monitorable_count = inventory_groups.get("monitorable_servers") if inventory_groups else None
    if active_count is not None and monitorable_count is not None:
        cover_subtitle = (
            f"本次覆盖 {inventory_groups.get('total_servers', summary['server_count'])} 条清单记录，"
            f"其中 {active_count} 台仍在使用、{monitorable_count} 台已成功采集 CPU/内存等运行状态，"
            "用于管理复核、工单分派和单机报告下钻。"
        )
    else:
        cover_subtitle = "面向多服务器资产的只读运行状态巡检，聚焦风险规模、证据边界、责任优先级和处置路径。"
    cover_kicker_html = f"""
        <div class="cover-kicker">
          <span class="status-pill"><i class="status-dot"></i>服务器运行健康：{html.escape(status_label(status))}</span>
          <span class="generated-at">生成时间：{html.escape(generated_display)}</span>
        </div>"""
    cover_title_html = f"""
        <p class="cover-eyebrow">{html.escape(report['environment']['name'])}</p>
        <h1>服务器运行健康报告</h1>
        <p class="cover-subtitle">{html.escape(cover_subtitle)}</p>"""
    hero_strip_html = f"""
        <div class="hero-strip">
          <div><span>服务器</span><b>{summary['server_count']}</b></div>
          <div><span>严重</span><b>{summary['critical_findings']}</b></div>
          <div><span>预警</span><b>{summary['warning_findings']}</b></div>
          <div><span>需复核</span><b>{summary.get('review_required_findings', 0)}</b></div>
        </div>"""
    if guide_is_ai_image:
        cover_html = f"""
    <div class="cover-grid ai-cover-grid">
      <div class="cover-copy ai-cover-copy">
{cover_kicker_html}
{cover_title_html}
      </div>
      <div class="ai-cover-showcase">
        <div class="ai-guide-stage">
          {guide_html}
        </div>
        <aside class="ai-cover-rail">
          <div class="conclusion-panel">{lead_conclusion_html}</div>
{hero_strip_html}
        </aside>
      </div>
    </div>"""
    else:
        cover_html = f"""
    <div class="cover-grid fallback-cover-grid">
      <div class="cover-copy">
{cover_kicker_html}
{cover_title_html}
        <div class="conclusion-panel">{lead_conclusion_html}</div>
{hero_strip_html}
      </div>
      {guide_html}
    </div>"""
    executive_brief_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in insights.get("executive_brief", []))
    markdown = markdown.replace("## 绠＄悊绠€鎶?", "## 管理简报")
    markdown = markdown.replace("## 椋庨櫓闃熷垪", "## 风险队列")
    markdown = markdown.replace("## 瑕嗙洊缂哄彛", "## 覆盖缺口")
    markdown = markdown.replace("## 澶勭疆琛屽姩鏉?", "## 处置行动板")
    confidence_reasons_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in confidence.get("reasons", []))
    coverage_gaps_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in insights.get("coverage_gaps", []))
    metric_insights_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in insights.get("metric_insights", []))
    reading_map_html = "".join(
        "<li><strong>{section}</strong><span>{purpose}</span></li>".format(
            section=html.escape(str(item.get("section") or "")),
            purpose=html.escape(str(item.get("purpose") or "")),
        )
        for item in insights.get("reading_map", [])
        if isinstance(item, dict)
    )
    action_board_html = "".join(
        "<section class=\"action-track\"><h3>{track}</h3><ul>{items}</ul></section>".format(
            track=html.escape(str(track.get("track") or "")),
            items="".join(f"<li>{html.escape(str(item))}</li>" for item in track.get("items", [])),
        )
        for track in insights.get("action_board", [])
        if isinstance(track, dict)
    )
    risk_queue_html = "".join(
        (
            "<article class=\"risk-item {severity}\">"
            "<div class=\"risk-item-head\"><span>{priority}</span><strong>{server}</strong><em>{due_time}</em></div>"
            "<h3>{title}</h3>"
            "<p>{evidence}</p>"
            "<p><b>建议</b>{recommendation}</p>"
            "<div class=\"risk-meta\"><span>{severity_label}</span><span>{strength}</span><span>{review}</span></div>"
            "</article>"
        ).format(
            severity=html.escape(str(item.get("severity") or "warning")),
            priority=html.escape(str(item.get("priority") or "-")),
            server=html.escape(str(item.get("server") or "")),
            due_time=html.escape(str(item.get("due_time") or "-")),
            title=html.escape(str(item.get("title") or "")),
            evidence=html.escape(str(item.get("evidence") or "")),
            recommendation=html.escape(str(item.get("recommendation") or "")),
            severity_label=html.escape(str(item.get("severity_label") or "")),
            strength=html.escape(str(item.get("evidence_strength") or "")),
            review="需复核" if item.get("review_required") else "无需额外复核",
        )
        for item in insights.get("risk_queue", [])
        if isinstance(item, dict)
    )
    advanced = insights.get("advanced", {}) if isinstance(insights.get("advanced"), dict) else {}
    visible_advanced, hidden_advanced = visible_advanced_sections(advanced)
    hidden_advanced_html = ""
    if hidden_advanced:
        hidden_advanced_html = (
            '<aside class="advanced-hidden-summary"><strong>已隐藏低信号模块</strong><ul>'
            + "".join(f"<li>{html.escape(item)}</li>" for item in hidden_advanced)
            + "</ul></aside>"
        )
    advanced_html = "\n".join(
        '<article id="{marker}" class="advanced-card {marker}"><h3>{title}</h3><div class="advanced-payload">{payload}</div></article>'.format(
            marker=html.escape(marker),
            title=html.escape(title),
            payload=render_advanced_payload_html(advanced.get(key)),
        )
        for key, marker, title, value in visible_advanced
    )
    quality_score = int(insights.get("quality_score", 0) or 0)
    confidence_score = int(confidence.get("score", 0) or 0)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(report['environment']['name'])} 服务器运行健康报告</title>
  <style>
    :root {{ color-scheme: light; --ink:#172033; --muted:#667085; --line:#d8dee8; --paper:#ffffff; --soft:#f5f7fb; --good:#147a4b; --warn:#a15c00; --bad:#b42318; --unknown:#4b5565; --accent:#1f6f8b; --gold:#b7791f; }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{ margin: 0; font: 14px/1.6 "Microsoft YaHei", "Noto Sans CJK SC", Arial, Helvetica, sans-serif; color: var(--ink); background: #eef2f6; }}
    .guide-cover {{ padding:32px 6vw 28px; color:white; background:#14314c; }}
    .cover-grid {{ max-width:1220px; margin:0 auto; }}
    .fallback-cover-grid {{ display:grid; grid-template-columns:minmax(360px,1.05fr) minmax(310px,.72fr); gap:24px; align-items:stretch; }}
    .ai-cover {{ padding:28px 6vw 30px; }}
    .ai-cover-grid {{ display:grid; grid-template-columns:1fr; gap:18px; }}
    .cover-copy {{ min-width:0; }}
    .ai-cover-copy {{ max-width:1120px; }}
    .cover-copy h1 {{ margin: 0; font-size: clamp(28px, 3.6vw, 42px); line-height: 1.12; letter-spacing: 0; max-width: 760px; }}
    .ai-cover .cover-copy h1 {{ max-width: 820px; font-size: clamp(34px, 3.2vw, 46px); line-height: 1.08; }}
    .cover-kicker {{ display:flex; flex-wrap:wrap; align-items:center; gap: 10px; margin-bottom:14px; }}
    .generated-at {{ color:#c7d9e4; font-size: 13px; }}
    .cover-eyebrow {{ margin:0 0 6px; color:#a9c2d3; font-size:13px; font-weight:700; }}
    .cover-subtitle {{ margin:10px 0 0; color:#cfe1ec; max-width:760px; }}
    .ai-cover .cover-subtitle {{ max-width:980px; margin-top:8px; }}
    .conclusion-panel {{ margin-top:16px; border:1px solid rgba(255,255,255,.22); border-radius:8px; padding:13px 15px; background:rgba(255,255,255,.10); max-width:780px; box-shadow: inset 0 1px 0 rgba(255,255,255,.12); }}
    .conclusion-panel p {{ margin:0; color:#f2f8fb; font-size:15px; line-height:1.72; }}
    .report-conclusion {{ margin:0 0 18px; border:1px solid var(--line); border-radius:8px; padding:15px 16px; background:#fff; max-width:none; box-shadow:0 8px 22px rgba(16,36,63,.05); }}
    .report-conclusion h3 {{ margin:0 0 8px; font-size:16px; }}
    .report-conclusion p {{ margin:0 0 8px; color:#334155; font-size:14px; line-height:1.7; }}
    .report-conclusion p:last-child {{ margin-bottom:0; }}
    .ai-cover-showcase {{ display:grid; grid-template-columns:minmax(0,1fr) 306px; gap:16px; align-items:start; padding:14px; border:1px solid rgba(255,255,255,.42); border-radius:8px; background:#f7fafc; box-shadow:0 22px 56px rgba(5,18,32,.30); }}
    .ai-cover-rail {{ display:grid; gap:12px; align-content:start; min-width:0; }}
    .ai-cover .conclusion-panel {{ margin:0; max-width:none; min-height:0; display:flex; align-items:flex-start; padding:16px; border-color:#cfd9e6; background:#ffffff; box-shadow:none; }}
    .ai-cover .conclusion-panel p {{ color:#203044; font-size:15px; line-height:1.72; }}
    .hero-strip {{ display:grid; grid-template-columns:repeat(4,minmax(0,118px)); gap:10px; margin-top:14px; }}
    .ai-cover .hero-strip {{ margin:0; grid-template-columns:1fr; max-width:none; }}
    .hero-strip div {{ border:1px solid rgba(255,255,255,.18); border-radius:8px; padding:9px 11px; background:rgba(255,255,255,.09); }}
    .ai-cover .hero-strip div {{ display:flex; align-items:center; justify-content:space-between; gap:12px; min-height:72px; padding:13px 14px; border-color:#d4dde9; background:#edf3f8; }}
    .hero-strip span {{ display:block; color:#bdd3df; font-size:12px; }}
    .ai-cover .hero-strip span {{ color:#5c6f85; font-weight:700; }}
    .hero-strip b {{ display:block; margin-top:2px; font-size:18px; }}
    .ai-cover .hero-strip b {{ margin-top:0; color:#135f7b; font-size:28px; line-height:1; }}
    .cover-stats {{ display:grid; grid-template-columns: repeat(4, minmax(86px, 1fr)); gap: 10px; }}
    .cover-stat {{ border: 1px solid rgba(255,255,255,.22); border-radius: 8px; padding: 10px 12px; background: rgba(255,255,255,.08); }}
    .cover-stat span {{ display:block; color:#c7d9e4; font-size: 12px; }}
    .cover-stat b {{ display:block; font-size: 22px; line-height: 1.2; }}
    .guide-visual {{ margin:0; border: 1px solid rgba(255,255,255,.24); border-radius: 8px; overflow: hidden; background: rgba(255,255,255,.08); min-height: 220px; display:flex; align-items:center; justify-content:center; }}
    .guide-visual img {{ display:block; width:100%; height:auto; }}
    .ai-guide-stage {{ width:100%; }}
    .ai-guide-stage .guide-visual {{ width:100%; min-height:0; aspect-ratio:3/2; border-color:#d1dbe8; background:#ffffff; }}
    .ai-guide-stage .guide-visual img {{ width:100%; height:100%; object-fit:cover; }}
    .html-guide-visual {{ padding: 16px; }}
    .guide-map {{ width: 100%; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; color: #e9f2f8; }}
    .guide-map-head {{ grid-column: 1 / -1; display:flex; align-items:center; justify-content:space-between; gap: 12px; padding-bottom: 6px; border-bottom: 1px solid rgba(255,255,255,.28); }}
    .guide-map-head span {{ font-weight: 700; }}
    .guide-map-head strong {{ padding: 3px 9px; border-radius: 999px; background: rgba(255,255,255,.16); }}
    .guide-flow {{ grid-column: 1 / -1; display:grid; grid-template-columns: repeat(4, 1fr); gap: 6px; }}
    .guide-flow span {{ height: 5px; border-radius: 999px; background: linear-gradient(90deg, #69d2c7, #f4c95d); opacity: .92; }}
    .guide-node {{ min-height: 58px; border: 1px solid rgba(255,255,255,.24); border-radius: 8px; padding: 10px; background: rgba(255,255,255,.10); }}
    .guide-node small {{ display:block; color: #b8d4e3; margin-bottom: 4px; }}
    .guide-node b {{ font-size: 13px; }}
    .guide-node.primary {{ background: rgba(105,210,199,.16); }}
    .guide-node.risk {{ background: rgba(244,201,93,.16); }}
    .guide-node.action {{ background: rgba(255,255,255,.14); }}
    .status-pill {{ display:inline-flex; align-items:center; gap:7px; padding:5px 10px; border:1px solid rgba(255,255,255,.38); border-radius:999px; background:rgba(255,255,255,.12); font-size:12px; }}
    .status-dot {{ width:8px; height:8px; border-radius:50%; background:#7be0a2; box-shadow:0 0 0 4px rgba(123,224,162,.16); }}
    .report-nav {{ position: sticky; top: 0; z-index: 2; display: flex; gap: 8px; padding: 10px 6vw; background: rgba(255,255,255,.96); border-bottom: 1px solid var(--line); box-shadow: 0 8px 22px rgba(16,36,63,.06); }}
    .report-nav a {{ color: var(--ink); text-decoration: none; font-weight: 700; padding: 6px 10px; border-radius: 8px; }}
    .report-nav a:hover {{ background: var(--soft); }}
    main.executive-layout {{ max-width: 1220px; margin: 0 auto; padding: 24px 20px 46px; background: var(--paper); }}
    .section-head {{ display:flex; justify-content:space-between; align-items:flex-end; gap: 18px; margin-bottom: 14px; }}
    .section-head h2 {{ margin: 0; font-size: 22px; }}
    .section-note {{ margin: 0; color: var(--muted); max-width: 620px; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(4, minmax(150px, 1fr)); gap: 12px; margin: 18px 0; }}
    .core-metric-grid {{ grid-template-columns: repeat(3, minmax(150px, 1fr)); }}
    .key-service-grid {{ grid-template-columns: repeat(2, minmax(150px, 1fr)); }}
    .metric, .metric-card {{ position:relative; min-height:128px; border: 1px solid var(--line); border-radius: 8px; padding: 14px; background: #fff; box-shadow:0 10px 24px rgba(16,36,63,.06); overflow:hidden; }}
    .metric::before, .metric-card::before {{ content:""; position:absolute; inset:0 0 auto; height:4px; background:linear-gradient(90deg,var(--accent),#69d2c7); }}
    .metric span, .metric-card span {{ color: var(--muted); display:block; font-size:13px; }}
    .metric b, .metric-card b {{ display:block; margin-top:8px; font-size: 28px; line-height: 1.15; }}
    .metric p, .metric-card p {{ margin:8px 0 0; color:var(--muted); }}
    .metric.critical b {{ color: var(--bad); }}
    .metric.warning b {{ color: var(--warn); }}
    .metric.review b {{ color: var(--accent); }}
    .coverage-strip, .trend-strip {{ display:grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 12px; }}
    .trend-strip {{ grid-template-columns: repeat(4, minmax(0, 1fr)); }}
    .strip-item {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; background: #fff; }}
    .strip-item span {{ display:block; color: var(--muted); font-size: 12px; }}
    .strip-item b {{ display:block; margin-top: 2px; }}
    .fold-section {{ border-top: 1px solid var(--line); padding: 28px 0; }}
    .table-scroll {{ overflow-x: auto; border: 1px solid var(--line); border-radius: 8px; background: #fff; }}
    table {{ width: 100%; min-width: 980px; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 10px 11px; text-align: left; vertical-align: top; }}
    th {{ position: sticky; top: 0; background: #edf3f9; font-size: 12px; color: #334155; z-index: 1; }}
    tbody tr:nth-child(even) {{ background: #fafcff; }}
    tbody tr:hover {{ background: #f2f7fc; }}
    .matrix-card-list {{ display: none; }}
    .matrix-card {{ border: 1px solid var(--line); border-left: 4px solid var(--unknown); border-radius: 8px; padding: 13px 14px; background: #fff; box-shadow: 0 8px 18px rgba(16,36,63,.05); }}
    .matrix-card.healthy {{ border-left-color: var(--good); }}
    .matrix-card.warning {{ border-left-color: var(--warn); }}
    .matrix-card.critical {{ border-left-color: var(--bad); }}
    .matrix-card-head {{ display:flex; align-items:flex-start; justify-content:space-between; gap: 10px; margin-bottom: 10px; }}
    .matrix-card h3 {{ margin: 0; font-size: 16px; line-height: 1.35; }}
    .matrix-card dl {{ display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 12px; margin: 0; }}
    .matrix-card dl div {{ min-width: 0; }}
    .matrix-card dt {{ color: var(--muted); font-size: 12px; }}
    .matrix-card dd {{ margin: 1px 0 0; word-break: break-word; }}
    .matrix-card p {{ margin: 10px 0 0; padding-top: 10px; border-top: 1px solid var(--line); color: #334155; }}
    .badge {{ display: inline-block; min-width: 76px; padding: 3px 8px; border-radius: 999px; text-align: center; color: white; font-size: 12px; }}
    .badge.healthy {{ background: var(--good); }}
    .badge.warning {{ background: var(--warn); }}
    .badge.critical {{ background: var(--bad); }}
    .badge.unknown {{ background: var(--unknown); }}
    .finding-list {{ display:grid; gap: 12px; }}
    .service-list {{ list-style:none; padding:0; margin:0; display:grid; gap:9px; }}
    .service-list li {{ display:grid; grid-template-columns:minmax(170px,1fr) auto; gap:8px 14px; align-items:center; border-bottom:1px solid var(--line); padding:0 0 10px; }}
    .service-list li:last-child {{ border-bottom:0; padding-bottom:0; }}
    .service-list li.ok b {{ color:var(--good); }}
    .service-list li.warn b {{ color:var(--warn); }}
    .service-list li.unknown b {{ color:var(--unknown); }}
    .service-list li span {{ min-width:0; }}
    .service-list li em {{ grid-column:1/-1; color:var(--muted); font-style:normal; font-size:13px; }}
    .finding-card {{ border: 1px solid var(--line); border-radius: 8px; padding: 16px; background: #fff; box-shadow: 0 8px 22px rgba(16,36,63,.05); }}
    .finding-card-head {{ display:flex; align-items:center; justify-content:space-between; gap: 12px; margin-bottom: 8px; }}
    .finding-card h3 {{ margin: 0; font-size: 18px; }}
    .finding-card ul {{ list-style:none; padding:0; margin:0; display:grid; gap: 10px; }}
    .finding-card li {{ border-top: 1px solid var(--line); padding-top: 10px; }}
    .finding-title {{ display:flex; align-items:center; gap: 10px; font-weight: 700; }}
    .finding-title strong {{ color: var(--bad); }}
    .finding-meta {{ display:flex; flex-wrap:wrap; gap: 8px; margin: 8px 0; }}
    .finding-meta span {{ padding: 3px 8px; border-radius: 999px; background: #eef4fb; color:#334155; font-size: 12px; }}
    .finding-card p {{ margin: 6px 0; color: #334155; }}
    .finding-card p b {{ display:inline-block; min-width: 42px; color: var(--ink); }}
    .empty-state {{ border: 1px dashed var(--line); border-radius: 8px; padding: 18px; background: #fbfdff; color: var(--muted); }}
    .evidence-grid {{ display:grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }}
    details {{ border: 1px solid var(--line); border-radius: 8px; padding: 12px; margin: 0; background: #fff; }}
    summary {{ cursor: pointer; font-weight: 700; }}
    pre {{ overflow-x: auto; background: #111827; color: #eef2ff; padding: 12px; border-radius: 8px; }}
    @media print {{ body {{ background:white; }} .report-nav {{ position: static; box-shadow:none; }} main.executive-layout {{ max-width: none; padding: 0; }} .guide-cover {{ background:#14314c; }} .table-scroll {{ overflow: visible; }} details, .metric, .metric-card {{ break-inside: avoid; }} }}
    @media (max-width: 980px) {{ .fallback-cover-grid, .ai-cover-showcase {{ grid-template-columns: 1fr; }} .ai-cover .hero-strip {{ grid-template-columns:repeat(4,minmax(0,1fr)); }} .metric-grid, .coverage-strip, .trend-strip, .evidence-grid, .cover-stats {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} .core-metric-grid, .key-service-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} .report-nav {{ overflow-x:auto; }} .section-head {{ display:block; }} }}
    @media (max-width: 720px) {{ .table-scroll {{ display:none; }} .matrix-card-list {{ display:grid; gap: 10px; }} }}
    @media (max-width: 620px) {{ .guide-cover,.ai-cover {{ padding:22px 12px 24px; }} main.executive-layout {{ padding: 18px 12px 34px; }} .hero-strip,.ai-cover .hero-strip,.metric-grid, .coverage-strip, .trend-strip, .evidence-grid, .cover-stats, .matrix-card dl, .core-metric-grid, .key-service-grid {{ grid-template-columns: 1fr; }} .cover-copy h1 {{ font-size: 28px; }} .service-list li {{ grid-template-columns: 1fr; }} .service-list li em {{ grid-column:auto; }} }}
  </style>
</head>
<body>
  <header class="guide-cover {cover_class}">
{cover_html}
  </header>
  <nav class="report-nav" aria-label="报告导航">
    <a href="#summary">摘要</a>
    <a href="#core-metrics">核心指标</a>
    <a href="#key-services">关键服务</a>
    <a href="#auth-security">认证安全</a>
    <a href="#doops-channel">doops 通道</a>
    <a href="#inventory-groups">清单分层</a>
    <a href="#matrix">服务器矩阵</a>
    <a href="#findings">问题建议</a>
    <a href="#evidence-boundary">证据边界</a>
  </nav>
  <main class="compact-report executive-layout">
    <section id="summary" class="fold-section compact-summary">
      <div class="section-head">
        <h2>管理摘要</h2>
        <p class="section-note">只保留本批次决策需要的风险数量、采集覆盖和趋势状态。</p>
      </div>
      <div class="report-conclusion"><h3>管理结论</h3>{conclusion_html}</div>
      <div class="metric-grid">
        <div class="metric"><span>服务器数</span><b>{report['summary']['server_count']}</b></div>
        <div class="metric critical"><span>严重问题</span><b>{report['summary']['critical_findings']}</b></div>
        <div class="metric warning"><span>预警问题</span><b>{report['summary']['warning_findings']}</b></div>
        <div class="metric review"><span>需复核</span><b>{report['summary'].get('review_required_findings', 0)}</b></div>
      </div>
      <div class="coverage-strip">
        <div class="strip-item"><span>网络探测</span><b>{html.escape(coverage_label(coverage['network']))}</b></div>
        <div class="strip-item"><span>主机指标</span><b>{html.escape(coverage_label(coverage['host_metrics']))}</b></div>
        <div class="strip-item"><span>服务状态</span><b>{html.escape(coverage_label(coverage['services']))}</b></div>
      </div>
      <div class="trend-strip">
        <div class="strip-item"><span>趋势状态</span><b>{html.escape(str(trend.get('summary') or '基线巡检'))}</b></div>
        <div class="strip-item"><span>新增问题</span><b>{trend.get('new_findings', 0)}</b></div>
        <div class="strip-item"><span>已恢复问题</span><b>{trend.get('resolved_findings', 0)}</b></div>
        <div class="strip-item"><span>持续问题</span><b>{trend.get('persistent_findings', 0)}</b></div>
      </div>
    </section>
    <section id="core-metrics" class="fold-section compact-core-metrics">
      <div class="section-head">
        <h2>核心指标</h2>
        <p class="section-note">汇总本批次已采集到的 CPU、内存、磁盘、负载和进程覆盖，不展示空白明细。</p>
      </div>
      <div class="metric-grid core-metric-grid">{core_metric_cards_html}</div>
    </section>
    <section id="key-services" class="fold-section compact-key-services">
      <div class="section-head">
        <h2>关键服务</h2>
        <p class="section-note">只展示已采集到的服务状态；没有服务明细时明确写出证据边界。</p>
      </div>
      <div class="metric-grid key-service-grid">{key_service_cards_html}</div>
      <div class="finding-card">{key_service_list_html}</div>
    </section>
    <section id="auth-security" class="fold-section compact-auth-security">
      <div class="section-head">
        <h2>认证安全</h2>
        <p class="section-note">基于认证日志、防护配置和显式开启的本地口令强度评分判断爆破迹象；不展示明文密码、hash 或完整原始日志。</p>
      </div>
      <div class="metric-grid key-service-grid">{auth_metric_cards_html}</div>
      <div class="finding-card">{auth_rows_html}</div>
    </section>
    {doops_channel_html}
    {ai_review_html}
    {inventory_group_html}
    {application_html}
    <section id="matrix" class="fold-section compact-matrix">
      <div class="section-head">
        <h2>服务器矩阵</h2>
        <p class="section-note">集中展示运行状态和关键指标，不展示长期缺失字段。</p>
      </div>
      <div class="table-scroll">
        <table>
          <thead><tr><th>服务器</th><th>地址</th><th>业务角色</th><th>状态</th><th>CPU</th><th>内存</th><th>磁盘最高占用</th><th>主要进程数</th><th>优先级</th><th>建议处理时限</th><th>证据边界</th></tr></thead>
          <tbody>{server_rows}</tbody>
        </table>
      </div>
      <div class="matrix-card-list">{matrix_cards}</div>
    </section>
    <section id="findings" class="fold-section compact-findings">
      <div class="section-head">
        <h2>问题与建议</h2>
        <p class="section-note">只列出需要处理或复核的事项。</p>
      </div>
      <div class="finding-list">{findings_html}</div>
    </section>
    <section id="evidence-boundary" class="fold-section compact-evidence">
      <div class="section-head">
        <h2>证据边界</h2>
        <p class="section-note">说明本报告能证明什么，避免把网络可达性误读成业务完全健康。</p>
      </div>
      <div class="coverage-strip">
        <div class="strip-item"><span>网络探测</span><b>{html.escape(coverage_label(coverage['network']))}</b></div>
        <div class="strip-item"><span>主机指标</span><b>{html.escape(coverage_label(coverage['host_metrics']))}</b></div>
        <div class="strip-item"><span>主要进程</span><b>{html.escape(coverage_label(coverage.get('processes', 'not-supplied')))}</b></div>
        <div class="strip-item"><span>服务状态</span><b>{html.escape(coverage_label(coverage['services']))}</b></div>
      </div>
      <div class="trend-strip">
        <div class="strip-item"><span>趋势状态</span><b>{html.escape(str(trend.get('summary') or '本次为基线巡检'))}</b></div>
        <div class="strip-item"><span>新增问题</span><b>{trend.get('new_findings', 0)}</b></div>
        <div class="strip-item"><span>已恢复问题</span><b>{trend.get('resolved_findings', 0)}</b></div>
        <div class="strip-item"><span>持续问题</span><b>{trend.get('persistent_findings', 0)}</b></div>
      </div>
    </section>
  </main>
</body>
</html>
"""


def render_guide_visual(report: dict[str, Any], guide_status: dict[str, Any]) -> str:
    if guide_status.get("status") in {"generated", "reused"}:
        return '<figure class="guide-visual"><img src="./html-assets/guide-image.png" alt="服务器健康报告导览图"></figure>'
    summary = report["summary"]
    coverage = summary["coverage"]
    if coverage.get("host_metrics") == "doops-self-collected":
        target = summary.get("doops_channel", {}).get("target") if isinstance(summary.get("doops_channel"), dict) else "zheyin"
        object_label = f"{target or 'zheyin'} 自身节点"
        action_label = "基线采集 · 趋势对比 · 节点复核"
    else:
        object_label = f"{summary['server_count']} 台服务器"
        action_label = "证据复核 · 优先修复 · 回归验证"
    return f"""<div class="guide-visual html-guide-visual" id="guide-visual" aria-label="服务器健康报告导览图">
      <div class="guide-map">
        <div class="guide-map-head">
          <span>报告导览</span>
          <strong>{html.escape(status_label(summary['overall_status']))}</strong>
        </div>
        <div class="guide-flow" aria-hidden="true">
          <span></span><span></span><span></span><span></span>
        </div>
        <div class="guide-node primary">
          <small>覆盖对象</small>
          <b>{html.escape(object_label)}</b>
        </div>
        <div class="guide-node">
          <small>网络探测</small>
          <b>{html.escape(coverage_label(coverage['network']))}</b>
        </div>
        <div class="guide-node">
          <small>主机指标</small>
          <b>{html.escape(coverage_label(coverage['host_metrics']))}</b>
        </div>
        <div class="guide-node">
          <small>服务状态</small>
          <b>{html.escape(coverage_label(coverage['services']))}</b>
        </div>
        <div class="guide-node risk">
          <small>风险概览</small>
          <b>严重 {summary['critical_findings']} 项 · 预警 {summary['warning_findings']} 项 · 需复核 {summary.get('review_required_findings', 0)} 项</b>
        </div>
        <div class="guide-node action">
          <small>处置路径</small>
          <b>{html.escape(action_label)}</b>
        </div>
      </div>
    </div>"""


def render_server_evidence(server: dict[str, Any]) -> str:
    ports = server["network"].get("ports", [])
    port_rows = "".join(
        f"<tr><td>{port['port']}</td><td>{html.escape(PORT_STATUS_LABELS.get(port['status'], port['status']))}</td><td>{html.escape(str(port.get('latency_ms') or ''))}</td><td>{html.escape(port_source_label(port.get('source')))}</td><td>{html.escape(port_usage_label(port.get('usage')))}</td></tr>"
        for port in ports
    )
    if not port_rows:
        port_rows = "<tr><td colspan=\"5\">未声明预期端口。</td></tr>"
    process_rows = "".join(
        "<tr><td>{name}</td><td>{pid}</td><td>{state}</td><td>{cpu}</td><td>{memory}</td></tr>".format(
            name=html.escape(str(process.get("name") or "process")),
            pid=html.escape(str(process.get("pid") or "")),
            state=html.escape(str(process.get("state") or "unknown")),
            cpu=html.escape(f"{float(process['cpu_percent']):.1f}%" if isinstance(process.get("cpu_percent"), (int, float)) else ""),
            memory=html.escape(
                f"{float(process['memory_percent']):.1f}%"
                if isinstance(process.get("memory_percent"), (int, float))
                else f"{float(process['memory_mb']):.1f} MB"
                if isinstance(process.get("memory_mb"), (int, float))
                else ""
            ),
        )
        for process in server.get("processes", [])[:12]
        if isinstance(process, dict)
    )
    if not process_rows:
        process_rows = "<tr><td colspan=\"5\">未采集到主要进程列表。</td></tr>"
    payload = {
        "metrics": server.get("metrics", {}),
        "processes": server.get("processes", []),
        "services": server.get("services", []),
        "collection_errors": server.get("collection_errors", []),
        "collection_trace": server.get("collection_trace", {}),
        "application_observation": server.get("application_observation", []),
        "collection_scope": "doops 节点自身监测" if server.get("network", {}).get("mode") == "doops-collected" and "无需 SSH/WinRM/SNMP" in server.get("evidence_boundary", "") else "服务器健康证据",
        "credential_boundary": "无需 SSH/WinRM/SNMP；未读取目标业务服务器账号" if "无需 SSH/WinRM/SNMP" in server.get("evidence_boundary", "") else "按证据边界说明",
        "credential_status": CREDENTIAL_LABELS.get(server.get("credential_status"), server.get("credential_status")),
        "priority": server.get("priority") or "",
        "due_time": server.get("due_time") or "",
    }
    return f"""<details>
  <summary>{html.escape(server['name'])} 证据</summary>
  <table><thead><tr><th>端口</th><th>状态</th><th>延迟毫秒</th><th>端口来源</th><th>端口用途</th></tr></thead><tbody>{port_rows}</tbody></table>
  <table><thead><tr><th>进程</th><th>PID</th><th>状态</th><th>CPU</th><th>内存</th></tr></thead><tbody>{process_rows}</tbody></table>
  <pre>{html.escape(json.dumps(payload, ensure_ascii=False, indent=2))}</pre>
</details>"""


def write_pdf(path: Path, report: dict[str, Any], markdown: str) -> None:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.pdfgen import canvas
    except Exception as exc:  # pragma: no cover - environment guard
        raise RuntimeError("生成中文 PDF 需要 reportlab。") from exc

    font_name = register_chinese_font(pdfmetrics, TTFont)
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    left = 42
    top = height - 48
    line_height = 15
    lines = [f"{report['environment']['name']} 服务器运行健康报告", "", report["management_conclusion"], ""]
    lines.extend(markdown.splitlines())
    y = top
    for line in wrap_pdf_lines(lines):
        if y < 44:
            c.showPage()
            y = top
        if line.startswith("# "):
            c.setFont(font_name, 16)
            c.drawString(left, y, line[2:])
            y -= line_height + 8
        elif line.startswith("## "):
            c.setFont(font_name, 13)
            c.drawString(left, y, line[3:])
            y -= line_height + 5
        elif line.startswith("### "):
            c.setFont(font_name, 11)
            c.drawString(left, y, line[4:])
            y -= line_height + 2
        else:
            c.setFont(font_name, 9)
            c.drawString(left, y, line)
            y -= line_height
    c.save()


def register_chinese_font(pdfmetrics: Any, TTFont: Any) -> str:
    candidates = [
        Path(os.environ.get("SERVER_HEALTH_PDF_FONT", "")),
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]
    for candidate in candidates:
        if candidate and str(candidate) != "." and candidate.is_file():
            pdfmetrics.registerFont(TTFont("ServerHealthCJK", str(candidate)))
            return "ServerHealthCJK"
    raise RuntimeError("未找到可用中文字体；请设置 SERVER_HEALTH_PDF_FONT 指向 .ttf/.ttc 字体文件。")


def wrap_pdf_lines(lines: list[str], width: int = 58) -> list[str]:
    wrapped: list[str] = []
    for line in lines:
        if len(line) <= width:
            wrapped.append(line)
            continue
        for start in range(0, len(line), width):
            wrapped.append(line[start : start + width])
    return wrapped


def build_guide_prompt(report: dict[str, Any]) -> str:
    summary = report["summary"]
    coverage = summary["coverage"]
    doops_channel = summary.get("doops_channel", {}) if isinstance(summary.get("doops_channel"), dict) else {}
    auth_summary = summary.get("auth_security", {}) if isinstance(summary.get("auth_security"), dict) else {}
    auth_text = ""
    if auth_summary:
        auth_text = (
            "同时表现认证安全态势，包括认证日志覆盖、密码爆破迹象、防护配置缺口和本地口令强度风险；"
            "只画风险元素和统计，不出现任何密码内容、hash、账号明细或原始日志。"
        )
    if coverage.get("host_metrics") == "doops-self-collected":
        scope_text = (
            f"画面主题必须明确是 {doops_channel.get('target') or 'zheyin'} doops 节点自身运行状态监测，"
            "突出 CPU、内存、磁盘、负载、主要进程、关键服务、doops 心跳、workspace 采集链路和基线巡检；"
            "不要暗示已经覆盖 Excel 清单内其他普通业务服务器。"
        )
    else:
        scope_text = "画面应包含服务器、网络端口、CPU/内存/磁盘、主要进程、服务状态、风险分级、复测路径等可视元素；"
    return (
        "请生成一张中文服务器运行健康报告导览图，横向信息图风格，适合放在报告表头。"
        f"{scope_text}"
        f"{auth_text}"
        "整体专业、清晰、偏管理汇报风格，不要出现真实 IP、账号、密钥、密码或二维码。"
        f"环境名称：{report['environment']['name']}；"
        f"总体状态：{status_label(summary['overall_status'])}；"
        f"服务器数量：{summary['server_count']}；"
        f"严重问题：{summary['critical_findings']}；预警问题：{summary['warning_findings']}；"
        f"网络覆盖：{coverage_label(coverage['network'])}；主机指标：{coverage_label(coverage['host_metrics'])}；"
        f"主要进程：{coverage_label(coverage.get('processes', 'not-supplied'))}；服务状态：{coverage_label(coverage['services'])}。"
    )


def read_local_env_files() -> None:
    candidates = [Path.cwd() / ".env", Path(__file__).resolve().parents[1] / ".env"]
    for env_path in candidates:
        if not env_path.is_file():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")


def write_guide_status(status_path: Path, status: dict[str, Any]) -> dict[str, Any]:
    status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return status


def html_guide_status(reason: str) -> dict[str, Any]:
    return {"status": "html_guide_selected", "fallback_reason": reason, "generated_at": now_iso()}


def require_explicit_guide_decision() -> None:
    raise RuntimeError(
        "默认 auto 模式不能在缺少 AI 导览图和 API Key 时静默降级为 HTML/CSS。"
        "请先询问用户是否使用 AI 导览图，并优先尝试 Codex/助手自主 GPT 生图；如果失败，再询问用户是否提供 API Key。"
        "只有用户不提供 API Key 或明确不使用 AI 导览图并确认接受内置导览图时，才重新运行并传入 --guide-mode html-guide。"
    )


def prepare_guide_image(
    report: dict[str, Any],
    out_dir: Path,
    skip: bool,
    model: str,
    size: str,
    quality: str,
    guide_mode: str = "auto",
) -> dict[str, Any]:
    assets_dir = out_dir / "delivery" / "html-assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    image_path = assets_dir / "guide-image.png"
    status_path = out_dir / "guide-image-status.json"
    if skip:
        guide_mode = "html-guide"
    if guide_mode == "html-guide":
        return write_guide_status(status_path, html_guide_status("user_selected_html_guide"))
    if image_path.is_file() and guide_mode in {"auto", "reuse-existing"}:
        return write_guide_status(
            status_path,
            {"status": "reused", "image": "delivery/html-assets/guide-image.png", "generated_at": now_iso()},
        )
    if guide_mode == "reuse-existing":
        return write_guide_status(status_path, html_guide_status("missing_existing_image"))
    if skip:
        return write_guide_status(status_path, html_guide_status("user_selected_html_guide"))
    if not os.environ.get("OPENAI_API_KEY"):
        if guide_mode == "ai-image":
            return write_guide_status(status_path, html_guide_status("missing_api_key"))
        require_explicit_guide_decision()
    try:
        from openai import OpenAI

        client = OpenAI()
        result = client.images.generate(model=model, prompt=build_guide_prompt(report), size=size, quality=quality)
        image_base64 = result.data[0].b64_json
        image_path.write_bytes(base64.b64decode(image_base64))
        status = {
            "status": "generated",
            "image": "delivery/html-assets/guide-image.png",
            "model": model,
            "size": size,
            "quality": quality,
            "generated_at": now_iso(),
        }
    except Exception as exc:
        status = html_guide_status("image_api_failed")
        status["error_type"] = exc.__class__.__name__
    return write_guide_status(status_path, status)


def text_marker_hits(payloads: dict[str, str]) -> list[str]:
    hits = []
    for name, text in payloads.items():
        for marker in BAD_TEXT_MARKERS:
            if marker in text:
                hits.append(f"{name}:{marker}")
    return hits


def build_delivery_manifest(audit_status: str, report: dict[str, Any] | None = None) -> dict[str, Any]:
    doops_channel = {}
    ai_review_enabled = False
    if isinstance(report, dict):
        summary = report.get("summary", {}) if isinstance(report.get("summary"), dict) else {}
        doops_channel = summary.get("doops_channel", {}) if isinstance(summary.get("doops_channel"), dict) else {}
        ai_review_enabled = bool(summary.get("ai_review"))
    return {
        "entrypoints": {
            "html": "delivery/final-report.html",
            "pdf": "delivery/final-report.pdf",
            "markdown": "delivery/final-report.md",
            "json": "delivery/final-report.json",
        },
        "quality_status": audit_status,
        "generated_at": now_iso(),
        "doops_session": doops_channel.get("session", ""),
        "transport_mode": doops_channel.get("transport_mode", ""),
        "preflight_status": "online" if doops_channel.get("target_online") else "unknown",
        "cleanup_status": doops_channel.get("cleanup_status", ""),
        "ai_review_enabled": ai_review_enabled,
    }


def render_manifest_markdown(manifest: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# 交付清单",
            "",
            f"- HTML：`{manifest['entrypoints']['html']}`",
            f"- PDF：`{manifest['entrypoints']['pdf']}`",
            f"- Markdown：`{manifest['entrypoints']['markdown']}`",
            f"- JSON：`{manifest['entrypoints']['json']}`",
            f"- 质量状态：{manifest['quality_status']}",
            f"- doops session：{manifest.get('doops_session') or '未启用'}",
            f"- 传输模式：{manifest.get('transport_mode') or '未提供'}",
            f"- 工作区清理：{manifest.get('cleanup_status') or '未提供'}",
            f"- AI 复核：{'已启用' if manifest.get('ai_review_enabled') else '未启用'}",
            "",
        ]
    )


def audit_delivery(out_dir: Path, html_text: str, markdown: str, report_json: str, guide_status: dict[str, Any], manifest_md: str) -> dict[str, Any]:
    delivery = out_dir / "delivery"
    required = [
        "final-report.html",
        "final-report.pdf",
        "final-report.md",
        "final-report.json",
        "guide-image-status.json",
        "delivery-manifest.json",
        "delivery-manifest.md",
    ]
    check_items = []
    checks: dict[str, str] = {}
    report_payload: dict[str, Any] = {}
    try:
        report_payload = json.loads(report_json)
    except json.JSONDecodeError:
        report_payload = {}
    compact_self_node = is_compact_self_node_report(report_payload)

    def add_check(key: str, name: str, passed: bool, hits: list[str] | None = None) -> None:
        status = "pass" if passed else "fail"
        checks[key] = status
        item: dict[str, Any] = {"key": key, "name": name, "status": status}
        if hits is not None:
            item["hits"] = hits
        check_items.append(item)

    for name in required:
        add_check(f"file_{name.replace('-', '_').replace('.', '_')}", f"{name} 文件存在", (delivery / name).is_file())
    for marker in ("guide-cover", "report-nav", "fold-section"):
        add_check(f"template_{marker.replace('-', '_')}", f"HTML 正式模板标记 {marker}", marker in html_text)
    layout_markers = (
        [
            "compact-report",
            "compact-metrics",
            "service-list",
            "compact-doops-channel",
            "compact-evidence",
        ]
        if compact_self_node
        else [
            "compact-report",
            "compact-summary",
            "compact-core-metrics",
            "compact-key-services",
            "compact-auth-security",
            "compact-matrix",
            "compact-findings",
            "compact-evidence",
            "matrix-card-list",
        ]
    )
    missing_layout_markers = [marker for marker in layout_markers if marker not in html_text]
    add_check("layout_upgrade_markers", "10 轮升级版式标记完整", not missing_layout_markers, missing_layout_markers)
    advanced_payload = (
        report_payload.get("summary", {}).get("report_insights", {}).get("advanced", {})
        if isinstance(report_payload, dict)
        else {}
    )
    advanced_keys = [key for key, _, _ in ADVANCED_REPORT_SECTIONS]
    missing_advanced_keys = [key for key in advanced_keys if not isinstance(advanced_payload, dict) or key not in advanced_payload]
    add_check("advanced_upgrade_markers", "20 轮高级报告模块结构化数据完整", not missing_advanced_keys, missing_advanced_keys)
    visible_advanced_count = html_text.count("advanced-payload")
    hidden_summary_present = "advanced-hidden-summary" in html_text
    add_check(
        "advanced_visible_signal",
        "HTML 不展示低信号高级模块",
        True if compact_self_node else visible_advanced_count == 0 and not hidden_summary_present,
        [f"visible={visible_advanced_count}", f"hidden_summary={hidden_summary_present}"],
    )
    chinese_body_ok = (
        "zheyin 自身节点健康报告" in html_text and "## 核心指标" in markdown
        if compact_self_node
        else "服务器运行健康报告" in html_text and "服务器矩阵" in markdown
    )
    add_check("chinese_body", "报告正文为中文", chinese_body_ok)
    add_check("guide_visual", "表头导览图或导览占位存在", "guide-visual" in html_text)
    if guide_status.get("status") in {"generated", "reused"}:
        add_check("guide_image_file", "GPT 导览图文件存在", (delivery / "html-assets" / "guide-image.png").is_file())
    else:
        add_check("html_css_guide", "HTML/CSS 导览图存在", "html-guide-visual" in html_text)
    runtime_hits = [notice for notice in GUIDE_RUNTIME_NOTICES if notice in html_text or notice in markdown]
    add_check("guide_runtime_notice_hidden", "正式报告不展示导览图运行提示", not runtime_hits, runtime_hits)
    add_check("manifest_chinese_title", "交付清单使用中文标题", manifest_md.startswith("# 交付清单"))
    marker_hits = text_marker_hits(
        {
            "HTML": html_text,
            "Markdown": markdown,
            "JSON": report_json,
            "交付清单": manifest_md,
        }
    )
    add_check("text_marker_scan", "占位符和乱码扫描", not marker_hits, marker_hits)
    payload = html_text + report_json
    sensitive_patterns = {
        "openai_api_key": r"\bsk-[A-Za-z0-9_-]{20,}\b",
        "doops_gateway_token": r"\bdgw_user_[A-Za-z0-9_]{20,}\b",
        "authorization_header": r"(?i)authorization\s*[:=]\s*(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}",
        "bearer_token": r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{20,}",
        "private_key_block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
        "secret_json_value": r'(?i)"(?:password|passwd|pwd|secret|token|cookie|private_key|auth_key|priv_key|community|apikey|api_key)"\s*:\s*"(?!<redacted>|redacted|\*{3,}|")[^"]{3,}"',
        "secret_assignment": r"(?i)\b(?:password|passwd|pwd|secret|token|apikey|api_key)\s*=\s*(?!<redacted>|redacted|\*{3,})[^\s;&<>\"']{4,}",
    }
    forbidden_hits = [name for name, pattern in sensitive_patterns.items() if re.search(pattern, payload)]
    add_check("sensitive_data_scan", "敏感信息泄露扫描", not forbidden_hits, forbidden_hits)
    status = "pass" if all(item["status"] == "pass" for item in check_items) else "fail"
    return {"status": status, "checks": checks, "check_items": check_items, "generated_at": now_iso()}


def render_quality_markdown(audit: dict[str, Any]) -> str:
    lines = ["# 服务器运行健康报告质量审计", "", f"- 状态：{audit['status']}", f"- 生成时间：{audit['generated_at']}", "", "## 检查项", ""]
    for check in audit.get("check_items", []):
        suffix = ""
        if check.get("hits"):
            suffix = f" ({', '.join(check['hits'])})"
        lines.append(f"- {check['status']}：{check['name']}{suffix}")
    return "\n".join(lines) + "\n"


def slugify(value: Any, fallback: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "-", text)
    text = text.strip("-")
    return text or fallback


def server_report_inventory(report: dict[str, Any], server: dict[str, Any]) -> dict[str, Any]:
    return {
        "environment": {
            "name": f"{server['name']} 单服务器运行健康报告",
            "owner": server.get("owner", ""),
            "inspection_window": report.get("generated_at", ""),
            "notes": f"从 {report['environment'].get('name', '服务器批次')} 总巡检中拆分生成。",
        },
        "servers": [server],
        "thresholds": report.get("thresholds", {}),
    }


def build_batch_summary(report: dict[str, Any], server_entries: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {status: 0 for status in ("healthy", "warning", "critical", "unknown")}
    for entry in server_entries:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    counts["total"] = len(server_entries)
    return {
        "report_kind": "server-health-batch",
        "environment": report["environment"],
        "entrypoints": {
            "index": "index.html",
            "overall_html": "overall/final-report.html",
            "overall_pdf": "overall/final-report.pdf",
            "server_index": "servers/index.html",
        },
        "counts": counts,
        "inventory_groups": report.get("summary", {}).get("inventory_groups", {}),
        "servers": server_entries,
        "generated_at": now_iso(),
    }


def render_batch_index(summary: dict[str, Any]) -> str:
    rows = []
    for item in summary["servers"]:
        rows.append(
            "<tr><td>{index}</td><td>{name}</td><td>{role}</td><td><span class=\"badge {status_class}\">{status}</span></td><td><a class=\"report-link\" href=\"{report}\">打开报告</a></td></tr>".format(
                index=item["index"],
                name=html.escape(item["name"]),
                role=html.escape(item.get("role", "")),
                status_class=html.escape(item["status"]),
                status=html.escape(status_label(item["status"])),
                report=html.escape(item["report"]),
            )
        )
    counts = summary["counts"]
    inventory_groups = summary.get("inventory_groups", {}) if isinstance(summary.get("inventory_groups"), dict) else {}
    group_metric_cards = ""
    if inventory_groups:
        group_metric_cards = (
            f"<div class=\"metric\"><span>原始清单</span><b>{html.escape(str(inventory_groups.get('total_servers', 0)))}</b></div>"
            f"<div class=\"metric\"><span>仍在使用</span><b>{html.escape(str(inventory_groups.get('active_servers', 0)))}</b></div>"
            f"<div class=\"metric\"><span>已停用</span><b>{html.escape(str(inventory_groups.get('inactive_servers', 0)))}</b></div>"
            f"<div class=\"metric\"><span>可正常监测</span><b>{html.escape(str(inventory_groups.get('monitorable_servers', 0)))}</b></div>"
            f"<div class=\"metric\"><span>不可正常监测</span><b>{html.escape(str(inventory_groups.get('unmonitorable_servers', 0)))}</b></div>"
        )
    generated_display = display_timestamp(summary.get("generated_at"))
    environment_name = html.escape(str(summary["environment"].get("name", "服务器批次")))
    subtitle = f"本批次包含 {counts.get('total', 0)} 份单服务器报告，整体总报告和下钻报告已按同一套报告模板生成。"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>服务器运行健康巡检批次报告</title>
  <style>
    :root {{ --ink:#172033; --muted:#667085; --line:#d8dee8; --soft:#f5f7fb; --good:#147a4b; --warn:#a15c00; --bad:#b42318; --unknown:#4b5565; --accent:#1f6f8b; --teal:#69d2c7; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font:14px/1.65 "Microsoft YaHei", Arial, sans-serif; color:var(--ink); background:#edf1f5; }}
    .guide-cover {{ padding:32px 6vw 28px; color:white; background:#14314c; }}
    .cover-grid {{ max-width:1220px; margin:0 auto; }}
    .fallback-cover-grid {{ display:grid; grid-template-columns:minmax(360px,1.05fr) minmax(310px,.72fr); gap:24px; align-items:stretch; }}
    .cover-kicker {{ display:flex; flex-wrap:wrap; align-items:center; gap:10px; margin-bottom:14px; }}
    .status-pill {{ display:inline-flex; align-items:center; gap:7px; padding:5px 10px; border:1px solid rgba(255,255,255,.38); border-radius:999px; background:rgba(255,255,255,.12); font-size:12px; }}
    .status-dot {{ width:8px; height:8px; border-radius:50%; background:#7be0a2; box-shadow:0 0 0 4px rgba(123,224,162,.16); }}
    .generated-at {{ color:#c7d9e4; font-size:13px; }}
    .cover-eyebrow {{ margin:0 0 6px; color:#a9c2d3; font-size:13px; font-weight:700; }}
    header h1 {{ margin:0; font-size:clamp(30px,3.4vw,44px); line-height:1.1; letter-spacing:0; }}
    .cover-subtitle {{ margin:10px 0 0; color:#cfe1ec; max-width:760px; }}
    .hero-strip {{ display:grid; grid-template-columns:repeat(4,minmax(0,118px)); gap:10px; margin-top:16px; }}
    .hero-strip div {{ border:1px solid rgba(255,255,255,.18); border-radius:8px; padding:9px 11px; background:rgba(255,255,255,.09); }}
    .hero-strip span {{ display:block; color:#bdd3df; font-size:12px; }}
    .hero-strip b {{ display:block; margin-top:2px; font-size:22px; line-height:1.1; }}
    .batch-cta {{ align-self:stretch; display:grid; align-content:center; gap:12px; border:1px solid rgba(255,255,255,.22); border-radius:8px; padding:18px; background:rgba(255,255,255,.10); }}
    .batch-cta p {{ margin:0; color:#eef7fb; }}
    main {{ max-width:1220px; margin:0 auto; padding:26px 18px 42px; }}
    a {{ color:#1456a0; font-weight:700; }}
    .overall-link {{ display:inline-flex; align-items:center; gap:8px; padding:9px 12px; border:1px solid var(--line); border-radius:8px; background:white; text-decoration:none; }}
    .metrics {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:12px; margin:18px 0; }}
    .metric {{ position:relative; min-height:112px; background:white; border:1px solid var(--line); padding:16px; border-radius:8px; box-shadow:0 10px 24px rgba(16,36,63,.06); overflow:hidden; }}
    .metric::before {{ content:""; position:absolute; inset:0 0 auto; height:4px; background:linear-gradient(90deg,var(--accent),var(--teal)); }}
    .metric span {{ display:block; color:var(--muted); font-size:13px; }}
    .metric b {{ font-size:26px; }}
    .table-shell {{ overflow-x:auto; border:1px solid var(--line); border-radius:8px; background:white; }}
    table {{ width:100%; min-width:760px; border-collapse:collapse; }}
    th, td {{ padding:10px 12px; border-bottom:1px solid #e7edf4; text-align:left; vertical-align:top; }}
    th {{ background:#edf3f9; font-size:12px; color:#334155; }}
    tbody tr:nth-child(even) {{ background:#fafcff; }}
    .badge {{ display:inline-block; min-width:64px; padding:3px 8px; border-radius:999px; text-align:center; color:white; font-size:12px; }}
    .badge.healthy {{ background:var(--good); }}
    .badge.warning {{ background:var(--warn); }}
    .badge.critical {{ background:var(--bad); }}
    .badge.unknown {{ background:var(--unknown); }}
    .report-link {{ white-space:nowrap; }}
    @media (max-width:980px) {{ .fallback-cover-grid {{ grid-template-columns:1fr; }} .hero-strip {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
    @media (max-width:620px) {{ .guide-cover {{ padding:22px 12px 24px; }} .hero-strip {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header class="guide-cover fallback-cover">
    <div class="cover-grid fallback-cover-grid">
      <div class="cover-copy">
        <div class="cover-kicker">
          <span class="status-pill"><i class="status-dot"></i>批次巡检入口</span>
          <span class="generated-at">生成时间：{html.escape(generated_display)}</span>
        </div>
        <p class="cover-eyebrow">{environment_name}</p>
      <h1>服务器运行健康巡检批次报告</h1>
        <p class="cover-subtitle">{html.escape(subtitle)}</p>
        <div class="hero-strip">
          <div><span>服务器总数</span><b>{counts.get('total', 0)}</b></div>
          <div><span>健康</span><b>{counts.get('healthy', 0)}</b></div>
          <div><span>预警</span><b>{counts.get('warning', 0)}</b></div>
          <div><span>严重</span><b>{counts.get('critical', 0)}</b></div>
        </div>
      </div>
      <aside class="batch-cta">
        <p>先阅读整体总报告，再按服务器清单下钻到单机报告。</p>
        <a class="overall-link" href="{html.escape(summary['entrypoints']['overall_html'])}">打开整体总报告</a>
        <a class="overall-link" href="{html.escape(summary['entrypoints'].get('server_index', 'servers/index.html'))}">打开单机报告索引</a>
      </aside>
    </div>
  </header>
  <main class="compact-report batch-index">
    <section class="metrics">
      <div class="metric"><span>服务器总数</span><b>{counts.get('total', 0)}</b></div>
      <div class="metric"><span>健康</span><b>{counts.get('healthy', 0)}</b></div>
      <div class="metric"><span>预警</span><b>{counts.get('warning', 0)}</b></div>
      <div class="metric"><span>严重</span><b>{counts.get('critical', 0)}</b></div>
      <div class="metric"><span>未知</span><b>{counts.get('unknown', 0)}</b></div>
      {group_metric_cards}
    </section>
    <div class="table-shell">
      <table>
        <thead><tr><th>序号</th><th>服务器</th><th>角色</th><th>状态</th><th>报告</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
  </main>
</body>
</html>
"""


def render_server_report_index(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    generated_display = display_timestamp(summary.get("generated_at"))
    environment_name = html.escape(str(summary["environment"].get("name", "服务器批次")))
    cards = []
    for item in summary["servers"]:
        cards.append(
            """
      <article class="server-card {status_class}" data-status="{status_class}">
        <div class="server-card-head">
          <span class="server-index">{index:03d}</span>
          <span class="badge {status_class}">{status}</span>
        </div>
        <h2>{name}</h2>
        <p>{role}</p>
        <div class="card-actions">
          <a href="{report}">查看 HTML 报告</a>
          <a href="{pdf}">查看 PDF</a>
        </div>
      </article>
            """.format(
                index=int(item.get("index", 0) or 0),
                status_class=html.escape(str(item.get("status") or "unknown")),
                status=html.escape(status_label(item.get("status", "unknown"))),
                name=html.escape(str(item.get("name") or "未命名服务器")),
                role=html.escape(str(item.get("role") or "未提供业务角色")),
                report=html.escape(str(item.get("report", "")).replace("servers/", "", 1)),
                pdf=html.escape(str(item.get("pdf", "")).replace("servers/", "", 1)),
            )
        )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>单机服务器报告索引</title>
  <style>
    :root {{ --ink:#172033; --muted:#667085; --line:#d8dee8; --soft:#f5f7fb; --good:#147a4b; --warn:#a15c00; --bad:#b42318; --unknown:#4b5565; --accent:#1f6f8b; --teal:#69d2c7; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font:14px/1.65 "Microsoft YaHei", Arial, sans-serif; color:var(--ink); background:#edf1f5; }}
    .guide-cover {{ padding:34px 6vw 28px; color:white; background:#14314c; }}
    .cover-grid {{ max-width:1220px; margin:0 auto; display:grid; grid-template-columns:minmax(360px,1fr) 360px; gap:22px; align-items:end; }}
    .cover-kicker {{ display:flex; flex-wrap:wrap; gap:10px; align-items:center; margin-bottom:14px; }}
    .status-pill {{ display:inline-flex; align-items:center; gap:7px; padding:5px 10px; border:1px solid rgba(255,255,255,.38); border-radius:999px; background:rgba(255,255,255,.12); font-size:12px; }}
    .status-dot {{ width:8px; height:8px; border-radius:50%; background:#7be0a2; box-shadow:0 0 0 4px rgba(123,224,162,.16); }}
    .generated-at {{ color:#c7d9e4; font-size:13px; }}
    .cover-eyebrow {{ margin:0 0 6px; color:#a9c2d3; font-size:13px; font-weight:700; }}
    h1 {{ margin:0; font-size:clamp(30px,3.4vw,44px); line-height:1.1; letter-spacing:0; }}
    .cover-subtitle {{ margin:10px 0 0; color:#cfe1ec; max-width:760px; }}
    .summary-panel {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }}
    .summary-panel div {{ min-height:76px; border:1px solid rgba(255,255,255,.18); border-radius:8px; padding:11px 12px; background:rgba(255,255,255,.09); }}
    .summary-panel span {{ display:block; color:#bdd3df; font-size:12px; }}
    .summary-panel b {{ display:block; margin-top:2px; font-size:26px; line-height:1.1; }}
    .toolbar {{ position:sticky; top:0; z-index:2; display:flex; flex-wrap:wrap; gap:8px; padding:12px 6vw; background:rgba(255,255,255,.96); border-bottom:1px solid var(--line); box-shadow:0 8px 22px rgba(16,36,63,.06); }}
    .toolbar a {{ color:var(--ink); text-decoration:none; font-weight:700; padding:7px 10px; border-radius:8px; }}
    .toolbar a:hover {{ background:var(--soft); }}
    main {{ max-width:1220px; margin:0 auto; padding:24px 18px 44px; }}
    .server-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:12px; }}
    .server-card {{ border:1px solid var(--line); border-left:4px solid var(--unknown); border-radius:8px; padding:15px; background:white; box-shadow:0 10px 24px rgba(16,36,63,.06); min-height:186px; display:flex; flex-direction:column; }}
    .server-card.healthy {{ border-left-color:var(--good); }}
    .server-card.warning {{ border-left-color:var(--warn); }}
    .server-card.critical {{ border-left-color:var(--bad); }}
    .server-card-head {{ display:flex; justify-content:space-between; align-items:center; gap:10px; }}
    .server-index {{ color:var(--muted); font-weight:700; }}
    .server-card h2 {{ margin:12px 0 6px; font-size:18px; line-height:1.35; word-break:break-word; }}
    .server-card p {{ margin:0; color:var(--muted); min-height:42px; word-break:break-word; }}
    .card-actions {{ display:flex; gap:8px; flex-wrap:wrap; margin-top:auto; padding-top:14px; }}
    .card-actions a {{ display:inline-flex; align-items:center; justify-content:center; min-height:34px; padding:7px 10px; border-radius:8px; border:1px solid var(--line); color:#1456a0; text-decoration:none; font-weight:700; background:#fff; }}
    .badge {{ display:inline-block; min-width:64px; padding:3px 8px; border-radius:999px; text-align:center; color:white; font-size:12px; }}
    .badge.healthy {{ background:var(--good); }}
    .badge.warning {{ background:var(--warn); }}
    .badge.critical {{ background:var(--bad); }}
    .badge.unknown {{ background:var(--unknown); }}
    @media (max-width:900px) {{ .cover-grid {{ grid-template-columns:1fr; }} .summary-panel {{ grid-template-columns:repeat(4,minmax(0,1fr)); }} }}
    @media (max-width:620px) {{ .guide-cover {{ padding:22px 12px 24px; }} .toolbar {{ padding:10px 12px; }} main {{ padding:18px 12px 34px; }} .summary-panel {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} .server-grid {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header class="guide-cover">
    <div class="cover-grid">
      <div>
        <div class="cover-kicker">
          <span class="status-pill"><i class="status-dot"></i>单机报告索引</span>
          <span class="generated-at">生成时间：{html.escape(generated_display)}</span>
        </div>
        <p class="cover-eyebrow">{environment_name}</p>
        <h1>单机服务器运行健康报告索引</h1>
        <p class="cover-subtitle">这里是 96 份单机报告的正式入口，用于替代浏览器文件夹目录列表。建议按状态优先查看严重和预警服务器。</p>
      </div>
      <aside class="summary-panel">
        <div><span>单机报告</span><b>{counts.get('total', 0)}</b></div>
        <div><span>健康</span><b>{counts.get('healthy', 0)}</b></div>
        <div><span>预警</span><b>{counts.get('warning', 0)}</b></div>
        <div><span>严重</span><b>{counts.get('critical', 0)}</b></div>
      </aside>
    </div>
  </header>
  <nav class="toolbar">
    <a href="../index.html">批次首页</a>
    <a href="../overall/final-report.html">整体总报告</a>
    <a href="../batch-summary.json">批次 JSON</a>
  </nav>
  <main class="compact-report server-report-index">
    <section class="server-grid">
{''.join(cards)}
    </section>
  </main>
</body>
</html>
"""


def prepare_n_plus_one_delivery(
    report: dict[str, Any],
    out_dir: Path,
    skip_guide_image: bool,
    image_model: str,
    image_size: str,
    image_quality: str,
    guide_mode: str,
) -> None:
    servers = report.get("servers", [])
    has_inventory_groups = bool(report.get("summary", {}).get("inventory_groups"))
    if len(servers) <= 1 and not has_inventory_groups:
        return
    batch_dir = out_dir / "delivery-batch"
    if batch_dir.exists():
        shutil.rmtree(batch_dir)
    batch_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(out_dir / "delivery", batch_dir / "overall")

    server_entries = []
    used_slugs: set[str] = set()
    for index, server in enumerate(servers, start=1):
        base_slug = slugify(server.get("name"), f"server-{index:03d}")
        slug = f"{index:03d}-{base_slug}"
        dedupe = 2
        while slug in used_slugs:
            slug = f"{index:03d}-{base_slug}-{dedupe}"
            dedupe += 1
        used_slugs.add(slug)

        server_run_dir = out_dir / "_server-reports" / slug
        server_report = build_report(server_report_inventory(report, server), offline=False, timeout=0)
        write_outputs(
            server_report,
            server_run_dir,
            skip_guide_image,
            image_model,
            image_size,
            image_quality,
            guide_mode,
            include_batch=False,
        )
        target_delivery = batch_dir / "servers" / slug / "delivery"
        target_delivery.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(server_run_dir / "delivery", target_delivery)
        server_entries.append(
            {
                "index": index,
                "name": server["name"],
                "role": server.get("role", ""),
                "status": server["status"],
                "report": f"servers/{slug}/delivery/final-report.html",
                "pdf": f"servers/{slug}/delivery/final-report.pdf",
                "json": f"servers/{slug}/delivery/final-report.json",
            }
        )

    summary = build_batch_summary(report, server_entries)
    (batch_dir / "batch-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (batch_dir / "index.html").write_text(render_batch_index(summary), encoding="utf-8")
    (batch_dir / "servers" / "index.html").write_text(render_server_report_index(summary), encoding="utf-8")


def write_outputs(
    report: dict[str, Any],
    out_dir: Path,
    skip_guide_image: bool,
    image_model: str,
    image_size: str,
    image_quality: str,
    guide_mode: str = "auto",
    include_batch: bool = True,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    delivery = out_dir / "delivery"
    delivery.mkdir(parents=True, exist_ok=True)
    guide_status = prepare_guide_image(report, out_dir, skip_guide_image, image_model, image_size, image_quality, guide_mode)
    markdown = render_markdown(report)
    html_text = render_html(report, markdown, guide_status)
    report_json = json.dumps(report, ensure_ascii=False, indent=2)
    (out_dir / "final-report.json").write_text(report_json, encoding="utf-8")
    (out_dir / "final-report.md").write_text(markdown, encoding="utf-8")
    (out_dir / "final-report.html").write_text(html_text, encoding="utf-8")
    write_pdf(out_dir / "final-report.pdf", report, markdown)
    for name in ("final-report.json", "final-report.md", "final-report.html", "final-report.pdf", "guide-image-status.json"):
        source = out_dir / name
        target = delivery / name
        if source.is_file():
            target.write_bytes(source.read_bytes())

    manifest = build_delivery_manifest("pending", report)
    manifest_md = render_manifest_markdown(manifest)
    (delivery / "delivery-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (delivery / "delivery-manifest.md").write_text(manifest_md, encoding="utf-8")

    audit = audit_delivery(out_dir, html_text, markdown, report_json, guide_status, manifest_md)
    (out_dir / "quality-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "quality-audit.md").write_text(render_quality_markdown(audit), encoding="utf-8")
    (delivery / "quality-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    (delivery / "quality-audit.md").write_text(render_quality_markdown(audit), encoding="utf-8")
    manifest = build_delivery_manifest(audit["status"], report)
    (delivery / "delivery-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (delivery / "delivery-manifest.md").write_text(render_manifest_markdown(manifest), encoding="utf-8")
    if audit["status"] != "pass":
        raise RuntimeError(f"quality audit failed: {audit}")
    if include_batch:
        prepare_n_plus_one_delivery(report, out_dir, skip_guide_image, image_model, image_size, image_quality, guide_mode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="执行服务器运行健康检查，并生成中文 HTML/PDF/Markdown 报告。")
    parser.add_argument("--inventory", required=True, help="JSON、CSV 或 TSV 服务器清单路径。")
    parser.add_argument("--out", required=True, help="输出运行目录。")
    parser.add_argument("--previous-report", help="上一期 final-report.json，用于生成趋势对比。")
    parser.add_argument("--offline", action="store_true", help="不连接主机，仅用清单验证报告生成。")
    parser.add_argument("--timeout", type=float, default=2.5, help="实时 TCP 探测超时时间，单位秒。")
    parser.add_argument("--skip-guide-image", action="store_true", help="不调用 GPT 导览图接口，直接使用中文 HTML/CSS 导览图。")
    parser.add_argument("--guide-mode", choices=["auto", "ai-image", "html-guide", "reuse-existing"], default="auto", help="导览图策略：auto 有密钥则生成图像，auto 缺少明确导览图决策时中止并提示先询问用户；ai-image 调用图像接口；html-guide 使用 HTML/CSS；reuse-existing 复用既有图片。")
    parser.add_argument("--image-model", default=os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-2"), help="导览图生成模型。")
    parser.add_argument("--image-size", default=os.environ.get("OPENAI_IMAGE_SIZE", "1536x1024"), help="导览图尺寸。")
    parser.add_argument("--image-quality", default=os.environ.get("OPENAI_IMAGE_QUALITY", "medium"), help="导览图质量。")
    parser.add_argument("--doops-ai-review", action="store_true", help="调用 doops ask 对脱敏 findings 做辅助复核；不改变正式判定。")
    parser.add_argument("--doops-ai-review-target", help="执行 doops ask 的目标；默认使用 doops_channel.target。")
    parser.add_argument("--doops-ai-review-scope", choices=["summary", "findings"], default="summary", help="AI 复核摘要范围。")
    parser.add_argument("--doops", help="doops CLI 路径，供 --doops-ai-review 使用。")
    args = parser.parse_args(argv)

    read_local_env_files()
    inventory = load_inventory(Path(args.inventory))
    previous_report = json.loads(Path(args.previous_report).read_text(encoding="utf-8")) if args.previous_report else None
    report = build_report(inventory, offline=args.offline, timeout=args.timeout, previous_report=previous_report)
    if args.doops_ai_review:
        target = args.doops_ai_review_target or report.get("summary", {}).get("doops_channel", {}).get("target")
        if target:
            try:
                apply_doops_ai_review(report, str(target), args.doops_ai_review_scope, args.doops)
            except Exception as exc:
                report["summary"]["ai_review"] = {
                    "status": "failed",
                    "target": str(target),
                    "scope": args.doops_ai_review_scope,
                    "advice": redact_text(str(exc), limit=1200),
                    "note": "AI 辅助复核失败，不影响正式报告生成。",
                }
        else:
            report["summary"]["ai_review"] = {
                "status": "skipped",
                "scope": args.doops_ai_review_scope,
                "advice": "未提供 doops AI 复核目标。",
                "note": "AI 辅助复核未启用，不影响正式报告生成。",
            }
    write_outputs(report, Path(args.out), args.skip_guide_image, args.image_model, args.image_size, args.image_quality, args.guide_mode)
    print(f"服务器运行健康报告已生成：{Path(args.out) / 'delivery' / 'final-report.html'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
