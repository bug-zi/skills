from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from health_common import (
    ensure_dir,
    has_dangerous_word,
    make_finding,
    module_report,
    read_json,
    resolve_env_placeholder,
    write_json,
)


async def run_flow(playwright, system: dict, flow: dict, out_dir: Path, allow_mutation: bool, index: int):
    browser = await playwright.chromium.launch(headless=True)
    page = await browser.new_page()
    console_errors = []
    page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
    try:
        for step in flow.get("steps", []):
            action = step.get("action", "")
            target = step.get("target", "")
            value = resolve_env_placeholder(step.get("value", ""))
            expect = resolve_env_placeholder(step.get("expect", ""))
            if not allow_mutation and (has_dangerous_word(action) or has_dangerous_word(target) or has_dangerous_word(value)):
                raise RuntimeError(f"blocked dangerous administrator action: {action} {target}")
            if action == "goto":
                await page.goto(target, wait_until="domcontentloaded", timeout=15000)
            elif action == "click":
                await page.click(target, timeout=10000)
            elif action == "fill":
                await page.fill(target, value, timeout=10000)
            elif action == "wait_for":
                await page.wait_for_selector(target, timeout=10000)
            elif action == "expect_text":
                await page.get_by_text(expect or target).wait_for(timeout=10000)
            elif action == "expect_url_contains":
                if expect not in page.url:
                    await page.wait_for_url(f"**{expect}**", timeout=10000)
            elif action == "expect_selector":
                await page.wait_for_selector(target or expect, timeout=10000)
            else:
                raise RuntimeError(f"unsupported browser action: {action}")
        await browser.close()
        return None
    except Exception as exc:  # noqa: BLE001
        evidence_dir = ensure_dir(out_dir / "evidence")
        shot = evidence_dir / f"{system.get('id')}-{flow.get('flow_id')}.png"
        try:
            await page.screenshot(path=str(shot), full_page=True)
        except Exception:  # noqa: BLE001
            shot = None
        current_url = page.url
        await browser.close()
        return make_finding(
            module="function",
            index=index,
            system=system,
            severity="high",
            title=f"{flow.get('name', flow.get('flow_id'))} 执行失败",
            impact="管理员关键操作路径不可用或不稳定，可能影响后台管理工作。",
            evidence=f"{exc}; current_url={current_url}; console_errors={console_errors[:3]}",
            target=flow.get("flow_id", ""),
            recommendation="检查登录态、前端选择器、网关路由和相关后端服务。",
            evidence_files=[str(shot)] if shot else [],
        )


async def check_async(inventory: dict, out_dir: Path) -> dict:
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:  # noqa: BLE001
        system = {"id": "browser-runtime", "name": "浏览器运行环境", "priority": "medium"}
        finding = make_finding(
            module="function",
            index=1,
            system=system,
            severity="medium",
            title="浏览器自动化依赖不可用",
            impact="本次无法验证管理员功能操作路径。",
            evidence=str(exc),
            recommendation="安装或修复 Playwright 运行环境后重试。",
        )
        return module_report("function-availability", [finding], [], {"flows": 0})

    findings = []
    systems_summary = []
    allow_mutation = bool(inventory.get("global", {}).get("allow_mutation", False))
    idx = 1
    async with async_playwright() as playwright:
        for system in inventory.get("systems", []):
            system_findings = 0
            for flow in system.get("admin_flows", []):
                finding = await run_flow(playwright, system, flow, out_dir, allow_mutation, idx)
                if finding:
                    findings.append(finding)
                    idx += 1
                    system_findings += 1
            systems_summary.append(
                {
                    "system_id": system.get("id"),
                    "system_name": system.get("name"),
                    "checked_flows": len(system.get("admin_flows", [])),
                    "findings": system_findings,
                }
            )
    return module_report(
        "function-availability",
        findings,
        systems_summary,
        {"checked_flows": sum(len(s.get("admin_flows", [])) for s in inventory.get("systems", []))},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run administrator browser availability flows.")
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out_dir = ensure_dir(args.out)
    report = asyncio.run(check_async(read_json(args.inventory), out_dir))
    output = Path(out_dir) / "function-report.json"
    write_json(output, report)
    print(output)


if __name__ == "__main__":
    main()

