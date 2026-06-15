from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import requests

from health_common import make_finding, module_report, read_json, tcp_connect, write_json


def find_host(system: dict, host_id: str) -> dict:
    for host in system.get("hosts", []):
        if host.get("host_id") == host_id:
            return host
    return {}


def check_inventory(inventory: dict) -> dict:
    findings = []
    systems_summary = []
    idx = 1
    for system in inventory.get("systems", []):
        checked = 0
        system_findings = 0
        for service in system.get("services", []):
            checked += 1
            check_type = service.get("check_type")
            target = service.get("check_target", "")
            host = find_host(system, service.get("host_id", ""))
            if check_type == "http":
                try:
                    response = requests.get(target, timeout=5)
                    expected = int(service.get("expected") or 200)
                    if response.status_code != expected:
                        finding = make_finding(
                            module="host",
                            index=idx,
                            system=system,
                            severity="critical" if response.status_code >= 500 else "high",
                            title=f"{service.get('name')} 健康接口异常",
                            impact="该微服务健康状态异常，可能影响管理平台相关能力。",
                            evidence=f"expected={expected}, actual={response.status_code}, url={target}",
                            target=target,
                            recommendation="检查服务实例、依赖组件和应用日志。",
                        )
                        findings.append(finding)
                        idx += 1
                        system_findings += 1
                except Exception as exc:  # noqa: BLE001
                    finding = make_finding(
                        module="host",
                        index=idx,
                        system=system,
                        severity="critical",
                        title=f"{service.get('name')} 健康接口不可达",
                        impact="巡检无法确认该微服务可用，相关管理功能存在中断风险。",
                        evidence=str(exc),
                        target=target,
                        recommendation="检查服务端口、网络策略和应用进程。",
                    )
                    findings.append(finding)
                    idx += 1
                    system_findings += 1
            elif check_type == "port":
                port = int(target or service.get("expected") or host.get("port") or 0)
                ok, detail = tcp_connect(host.get("ip", ""), port, timeout=3)
                if not ok:
                    finding = make_finding(
                        module="host",
                        index=idx,
                        system=system,
                        severity="high",
                        title=f"{service.get('name')} 端口不可达",
                        impact="服务监听端口不可访问，可能导致管理平台功能不可用。",
                        evidence=f"{host.get('ip')}:{port} {detail}",
                        target=f"{host.get('ip')}:{port}",
                        recommendation="检查防火墙、监听进程和网络连通性。",
                    )
                    findings.append(finding)
                    idx += 1
                    system_findings += 1
            elif check_type == "systemd":
                if not host.get("ip") or not host.get("auth_ref"):
                    finding = make_finding(
                        module="host",
                        index=idx,
                        system=system,
                        severity="medium",
                        title=f"{service.get('name')} 缺少 systemd 检查凭证",
                        impact="本次无法远程确认该核心程序是否运行。",
                        evidence=f"host_id={service.get('host_id')}, auth_ref missing or host missing",
                        target=target,
                        recommendation="在主机清单中配置 IP 与 auth_ref，并在运行环境中提供对应凭证。",
                    )
                    findings.append(finding)
                    idx += 1
                    system_findings += 1
                else:
                    finding = make_finding(
                        module="host",
                        index=idx,
                        system=system,
                        severity="low",
                        title=f"{service.get('name')} systemd 检查未执行",
                        impact="当前版本未直接持有 SSH 连接实现，需接入平台凭证执行远程只读命令。",
                        evidence=f"unit={target}, auth_ref={host.get('auth_ref')}",
                        target=target,
                        recommendation="在平台侧接入受控 SSH 执行器后启用 systemctl is-active 检查。",
                    )
                    findings.append(finding)
                    idx += 1
                    system_findings += 1
            else:
                finding = make_finding(
                    module="host",
                    index=idx,
                    system=system,
                    severity="low",
                    title=f"{service.get('name')} 检查类型暂不支持",
                    impact="该服务未纳入本次自动健康判断。",
                    evidence=f"check_type={check_type}",
                    target=target,
                    recommendation="使用第一版支持的 http、port 或 systemd 检查类型。",
                )
                findings.append(finding)
                idx += 1
                system_findings += 1
        systems_summary.append(
            {
                "system_id": system.get("id"),
                "system_name": system.get("name"),
                "checked_services": checked,
                "findings": system_findings,
            }
        )
    return module_report(
        "host-service-health",
        findings,
        systems_summary,
        {"checked_services": sum(len(s.get("services", [])) for s in inventory.get("systems", []))},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Check host and microservice health.")
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = check_inventory(read_json(args.inventory))
    output = Path(args.out) / "host-report.json"
    write_json(output, report)
    print(output)


if __name__ == "__main__":
    main()

