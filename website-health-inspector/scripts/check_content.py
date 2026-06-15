from __future__ import annotations

import argparse
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse

import requests

from health_common import make_finding, module_report, read_json, tls_expiry_days, write_json


class TextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.text_parts = []
        self._in_title = False
        self._skip = False

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript"}:
            self._skip = True

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript"}:
            self._skip = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data.strip()
        elif not self._skip:
            text = data.strip()
            if text:
                self.text_parts.append(text)

    @property
    def text(self):
        return " ".join(self.text_parts)


def check_inventory(inventory: dict) -> dict:
    findings = []
    systems_summary = []
    checked = 0
    failed = 0
    latencies = []
    idx = 1
    for system in inventory.get("systems", []):
        system_findings = []
        for page in system.get("websites", []):
            checked += 1
            url = page.get("url", "")
            timeout = max(1, int(page.get("timeout_ms", 5000)) / 1000)
            try:
                start = time.perf_counter()
                response = requests.get(url, timeout=timeout, headers={"User-Agent": "WebsiteHealthInspector/1.0"})
                latency_ms = int((time.perf_counter() - start) * 1000)
                latencies.append(latency_ms)
                parser = TextParser()
                if "text/html" in response.headers.get("content-type", ""):
                    parser.feed(response.text[:800_000])
                body_text = parser.text
                expected = int(page.get("expected_status", 200))
                if response.status_code != expected:
                    failed += 1
                    finding = make_finding(
                        module="content",
                        index=idx,
                        system=system,
                        severity="critical" if response.status_code >= 500 else "high",
                        title=f"{page.get('name', url)} 状态码异常",
                        impact="管理员可能无法正常访问该管理页面或站点入口。",
                        evidence=f"expected_status={expected}, actual_status={response.status_code}",
                        target=url,
                        recommendation="检查网关、应用服务和页面发布状态。",
                    )
                    findings.append(finding)
                    system_findings.append(finding)
                    idx += 1
                checks = page.get("content_checks", {}) or {}
                min_length = int(checks.get("min_length") or 0)
                if min_length and len(body_text) < min_length:
                    finding = make_finding(
                        module="content",
                        index=idx,
                        system=system,
                        severity="medium",
                        title=f"{page.get('name', url)} 页面内容过短",
                        impact="页面可能未完整渲染，管理员看到的内容可能不完整。",
                        evidence=f"body_length={len(body_text)}, min_length={min_length}",
                        target=url,
                        recommendation="检查页面模板、静态资源和后端渲染接口。",
                    )
                    findings.append(finding)
                    system_findings.append(finding)
                    idx += 1
                for text in checks.get("required_text", []) or []:
                    if text and text not in response.text and text not in body_text:
                        finding = make_finding(
                            module="content",
                            index=idx,
                            system=system,
                            severity="medium",
                            title=f"{page.get('name', url)} 缺少关键文本",
                            impact="管理员可能无法确认页面内容完整或页面已发布到正确版本。",
                            evidence=f"missing required_text: {text}",
                            target=url,
                            recommendation="核对页面内容配置、模板发布和前端资源。",
                        )
                        findings.append(finding)
                        system_findings.append(finding)
                        idx += 1
                for text in checks.get("forbidden_text", []) or []:
                    if text and re.search(re.escape(text), body_text, flags=re.I):
                        finding = make_finding(
                            module="content",
                            index=idx,
                            system=system,
                            severity="high" if text in {"500", "Internal Server Error", "服务不可用"} else "medium",
                            title=f"{page.get('name', url)} 出现异常文本",
                            impact="页面可能正在展示错误、维护或异常状态，影响管理员判断系统状态。",
                            evidence=f"found forbidden_text: {text}",
                            target=url,
                            recommendation="检查应用错误日志和页面内容发布状态。",
                        )
                        findings.append(finding)
                        system_findings.append(finding)
                        idx += 1
                if latency_ms > int(page.get("timeout_ms", 5000)) * 0.8:
                    finding = make_finding(
                        module="content",
                        index=idx,
                        system=system,
                        severity="low",
                        title=f"{page.get('name', url)} 响应较慢",
                        impact="管理员访问该页面时可能感到明显等待，系统稳定性需要关注。",
                        evidence=f"latency_ms={latency_ms}",
                        target=url,
                        recommendation="关注应用性能、网络链路和后端接口耗时。",
                    )
                    findings.append(finding)
                    system_findings.append(finding)
                    idx += 1
                parsed = urlparse(url)
                if parsed.scheme == "https":
                    days = tls_expiry_days(parsed.hostname or "")
                    if days is not None and days < 30:
                        finding = make_finding(
                            module="content",
                            index=idx,
                            system=system,
                            severity="medium",
                            title=f"{page.get('name', url)} TLS 证书临期",
                            impact="证书到期后管理员和系统用户可能无法安全访问站点。",
                            evidence=f"tls_expiry_days={days}",
                            target=url,
                            recommendation="尽快续期并验证证书部署。",
                        )
                        findings.append(finding)
                        system_findings.append(finding)
                        idx += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                finding = make_finding(
                    module="content",
                    index=idx,
                    system=system,
                    severity="critical",
                    title=f"{page.get('name', url)} 无法访问",
                    impact="管理员无法打开该站点或关键页面。",
                    evidence=str(exc),
                    target=url,
                    recommendation="检查 DNS、网络连通性、网关和应用服务状态。",
                )
                findings.append(finding)
                system_findings.append(finding)
                idx += 1
        systems_summary.append(
            {
                "system_id": system.get("id"),
                "system_name": system.get("name"),
                "checked_pages": len(system.get("websites", [])),
                "findings": len(system_findings),
            }
        )
    metrics = {
        "checked_pages": checked,
        "failed_pages": failed,
        "avg_latency_ms": int(sum(latencies) / len(latencies)) if latencies else None,
        "max_latency_ms": max(latencies) if latencies else None,
    }
    return module_report("content-review", findings, systems_summary, metrics)


def main() -> None:
    parser = argparse.ArgumentParser(description="Check page accessibility and content integrity.")
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    report = check_inventory(read_json(args.inventory))
    output = Path(args.out) / "content-report.json"
    write_json(output, report)
    print(output)


if __name__ == "__main__":
    main()

