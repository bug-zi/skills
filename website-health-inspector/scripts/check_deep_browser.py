from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from health_common import ensure_dir, now_iso, read_json, resolve_env_placeholder, scrub_sensitive_text, write_json
from rendered_route_utils import classify_rendered_page, route_requires_parameters

SLOW_PAGE_THRESHOLD_MS = 3000


def same_origin(url: str, origin: str) -> bool:
    parsed = urlparse(urljoin(origin, url))
    base = urlparse(origin)
    return parsed.scheme == base.scheme and parsed.netloc == base.netloc


def clean_text(text: str, limit: int = 1800, secrets: list[str] | None = None) -> str:
    return scrub_sensitive_text(" ".join(str(text or "").split())[:limit], secrets)


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl().rstrip("/")


def finding(
    idx: int,
    *,
    system: dict,
    target: str,
    title: str,
    severity: str,
    priority: str,
    evidence: str,
    recommendation: str,
    business_impact: str = "可能影响部分页面体验或需要后续排查。",
    confidence: str = "review-needed",
    evidence_files: list[str] | None = None,
    **extra,
) -> dict:
    payload = {
        "finding_id": f"browser-{idx:03d}",
        "system_id": system.get("id"),
        "system_name": system.get("name"),
        "target": target,
        "title": title,
        "severity": severity,
        "priority": priority,
        "business_impact": business_impact,
        "technical_evidence": evidence,
        "recommendation": recommendation,
        "confidence": confidence,
        "evidence_files": evidence_files or [],
    }
    payload.update(extra)
    return payload


async def safe_screenshot(page, out_dir: Path, name: str) -> str:
    path = out_dir / f"{name}.png"
    await page.screenshot(path=str(path), full_page=True)
    return path.name


def positive_int_or_none(value: Any) -> int | None:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def average_ms(values: list[int]) -> int | None:
    return int(round(sum(values) / len(values))) if values else None


def performance_metrics(visited_pages: list[dict]) -> dict[str, int | None]:
    open_times = [
        value
        for value in (positive_int_or_none((page.get("performance") or {}).get("open_time_ms")) for page in visited_pages)
        if value is not None
    ]
    ttfb_times = [
        value
        for value in (positive_int_or_none((page.get("performance") or {}).get("ttfb_ms")) for page in visited_pages)
        if value is not None
    ]
    return {
        "checked_pages": len(visited_pages),
        "avg_open_time_ms": average_ms(open_times),
        "max_open_time_ms": max(open_times) if open_times else None,
        "slow_pages": sum(1 for value in open_times if value > SLOW_PAGE_THRESHOLD_MS),
        "avg_ttfb_ms": average_ms(ttfb_times),
        "max_ttfb_ms": max(ttfb_times) if ttfb_times else None,
    }


async def collect_navigation_performance(page, open_time_ms: int) -> dict[str, int | str | None]:
    payload: dict[str, Any]
    try:
        payload = await page.evaluate(
            """() => {
                const nav = performance.getEntriesByType('navigation')[0] || null;
                const resources = performance.getEntriesByType('resource') || [];
                const safeRound = (value) => Number.isFinite(value) && value >= 0 ? Math.round(value) : null;
                if (nav) {
                    return {
                        url: location.href,
                        ttfb_ms: safeRound(nav.responseStart - nav.requestStart),
                        dom_content_loaded_ms: safeRound(nav.domContentLoadedEventEnd - nav.startTime),
                        load_event_ms: safeRound(nav.loadEventEnd - nav.startTime),
                        transfer_size_bytes: safeRound(nav.transferSize),
                        encoded_body_size_bytes: safeRound(nav.encodedBodySize),
                        resource_count: resources.length
                    };
                }
                const timing = performance.timing || {};
                const navigationStart = timing.navigationStart || 0;
                return {
                    url: location.href,
                    ttfb_ms: timing.responseStart && timing.requestStart ? safeRound(timing.responseStart - timing.requestStart) : null,
                    dom_content_loaded_ms: timing.domContentLoadedEventEnd && navigationStart ? safeRound(timing.domContentLoadedEventEnd - navigationStart) : null,
                    load_event_ms: timing.loadEventEnd && navigationStart ? safeRound(timing.loadEventEnd - navigationStart) : null,
                    transfer_size_bytes: null,
                    encoded_body_size_bytes: null,
                    resource_count: resources.length
                };
            }"""
        )
    except Exception:  # noqa: BLE001
        payload = {}
    return {
        "open_time_ms": positive_int_or_none(open_time_ms),
        "ttfb_ms": positive_int_or_none(payload.get("ttfb_ms")),
        "dom_content_loaded_ms": positive_int_or_none(payload.get("dom_content_loaded_ms")),
        "load_event_ms": positive_int_or_none(payload.get("load_event_ms")),
        "transfer_size_bytes": positive_int_or_none(payload.get("transfer_size_bytes")),
        "encoded_body_size_bytes": positive_int_or_none(payload.get("encoded_body_size_bytes")),
        "resource_count": positive_int_or_none(payload.get("resource_count")),
        "url": str(payload.get("url") or page.url or ""),
    }


async def fill_first_available(page, selectors: list[str], value: str, timeout: int = 12000) -> str:
    deadline = asyncio.get_running_loop().time() + timeout / 1000
    last_error = None
    while asyncio.get_running_loop().time() < deadline:
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if await locator.count() and await locator.is_visible(timeout=500):
                    await locator.fill(value, timeout=2500)
                    return selector
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        await page.wait_for_timeout(300)
    raise RuntimeError(f"no fillable input found for selectors={selectors}; last_error={last_error}")


async def click_first_available(page, selectors: list[str], timeout: int = 12000) -> str:
    deadline = asyncio.get_running_loop().time() + timeout / 1000
    last_error = None
    while asyncio.get_running_loop().time() < deadline:
        for selector in selectors:
            locator = page.locator(selector).first
            try:
                if await locator.count() and await locator.is_visible(timeout=500):
                    await locator.click(timeout=2500)
                    return selector
            except Exception as exc:  # noqa: BLE001
                last_error = exc
        await page.wait_for_timeout(300)
    raise RuntimeError(f"no clickable login button found for selectors={selectors}; last_error={last_error}")


async def collect_page(page, out_dir: Path, label: str, url: str, secrets: list[str] | None = None) -> dict:
    start = asyncio.get_running_loop().time()
    await page.goto(url, wait_until="networkidle", timeout=30000)
    open_time_ms = int((asyncio.get_running_loop().time() - start) * 1000)
    performance = await collect_navigation_performance(page, open_time_ms)
    screenshot = await safe_screenshot(page, out_dir, label)
    title = await page.title()
    text = await page.locator("body").inner_text(timeout=5000)
    links = await page.eval_on_selector_all(
        "a[href]",
        "els => els.map(a => ({text: (a.innerText || a.textContent || '').trim(), href: a.href})).filter(x => x.href)",
    )
    buttons = await page.eval_on_selector_all(
        "button, [role=button]",
        "els => els.map(b => (b.innerText || b.textContent || b.getAttribute('aria-label') || '').trim()).filter(Boolean)",
    )
    return {
        "label": label,
        "url": page.url,
        "title": title,
        "text_excerpt": clean_text(text, secrets=secrets),
        "rendered_status": classify_rendered_page(page.url, text),
        "link_count": len(links),
        "button_labels": buttons[:30],
        "screenshot": screenshot,
        "links": links[:80],
        "performance": performance,
    }


def login_status_from_signals(
    *,
    username: str,
    body_text: str,
    current_url: str,
    has_login_form: bool,
    auth_success_seen: bool = False,
) -> bool:
    if "/login" in current_url.lower() or has_login_form:
        return False
    identity_tokens = [username, f"{username}@example.com", "admin@example.com"]
    if any(token and token in body_text for token in identity_tokens):
        return True
    nav_tokens = sum(
        1
        for token in [
            "课程",
            "课堂",
            "训练",
            "实验",
            "考试",
            "资源",
            "用户",
            "系统",
            "璇剧▼",
            "璇惧爞",
            "璁粌",
            "瀹為獙",
            "鑰冭瘯",
            "璧勬簮",
        ]
        if token in body_text
    )
    return auth_success_seen or nav_tokens >= 4


async def login_success_signal(page, username: str, auth_success_seen: bool = False) -> bool:
    try:
        text = await page.locator("body").inner_text(timeout=5000)
    except Exception:  # noqa: BLE001
        text = ""
    lowered_url = page.url.lower()
    has_login_form = await page.locator("input[type='password']").count() > 0
    nav_tokens = sum(1 for token in ["课程", "课堂", "训练", "实验", "考试", "资源"] if token in text)
    identity_tokens = [username, f"{username}@example.com", "admin@example.com"]
    if any(token in text for token in identity_tokens):
        return True
    if "/login" not in lowered_url and nav_tokens >= 4 and not has_login_form:
        return True
    return login_status_from_signals(
        username=username,
        body_text=text,
        current_url=page.url,
        has_login_form=has_login_form,
        auth_success_seen=auth_success_seen,
    )


def seed_route_candidates(origin: str) -> list[dict]:
    route_map = [
        ("首页", "/"),
        ("课程", "/courses"),
        ("课堂", "/classrooms"),
        ("训练", "/practice"),
        ("实验", "/labs"),
        ("考试", "/exam"),
        ("资源", "/resources"),
        ("证书", "/certificate"),
        ("帮助", "/help"),
        ("隐私", "/privacy"),
        ("条款", "/terms"),
        ("数据集", "/datasets"),
        ("工作台", "/workspace"),
        ("系统设置", "/system/settings"),
        ("项目中心", "/projects"),
        ("用户管理", "/users"),
    ]
    return [{"text": label, "href": urljoin(origin, path)} for label, path in route_map]


async def collect_same_origin_links(page, origin: str) -> list[dict]:
    links = await page.eval_on_selector_all(
        "a[href], button, [role=button]",
        """els => els.map((el) => {
            const text = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim();
            const href = el.href || el.getAttribute('href') || '';
            return {text, href};
        }).filter(x => x.text || x.href)""",
    )
    route_map = {
        "首页": "/",
        "课程": "/courses",
        "课堂": "/classrooms",
        "训练": "/practice",
        "实验": "/labs",
        "考试": "/exam",
        "资源": "/resources",
        "证书": "/certificate",
    }
    candidates = []
    for item in links:
        href = item.get("href") or ""
        text = item.get("text") or ""
        if href and same_origin(href, origin):
            candidates.append({"text": text, "href": href})
        for seeded in seed_route_candidates(origin):
            if seeded["text"] in text:
                candidates.append(seeded)
        for label, path in route_map.items():
            if label in text:
                candidates.append({"text": label, "href": urljoin(origin, path)})
    unique = []
    seen = set()
    candidates.extend(seed_route_candidates(origin))
    for label, path in route_map.items():
        candidates.append({"text": label, "href": urljoin(origin, path)})
    for item in candidates:
        href = normalize_url(item["href"])
        if not href or href in seen:
            continue
        if any(word in urlparse(href).path.lower() for word in ["logout", "delete", "remove", "payment"]):
            continue
        seen.add(href)
        unique.append({"text": item.get("text", ""), "href": href})
    return unique


async def run_system(playwright, inventory: dict, system: dict, out_dir: Path) -> dict:
    website = (system.get("websites") or [{}])[0]
    entry_url = website.get("url") or inventory.get("source", {}).get("url")
    credentials = system.get("admin_credentials") or {}
    username = credentials.get("username")
    password = resolve_env_placeholder(f"${{{credentials.get('password_env')}}}") if credentials.get("password_env") else ""
    login_url = credentials.get("login_url") or urljoin(entry_url, "/login")
    secrets = [password] if password else []

    browser = await playwright.chromium.launch(headless=True)
    page = await browser.new_page(viewport={"width": 1440, "height": 1100})
    console_messages: list[dict] = []
    request_failures: list[dict] = []
    abnormal_responses: list[dict] = []
    auth_success_seen = False
    page.on(
        "console",
        lambda msg: console_messages.append(
            {
                "type": msg.type,
                "text": scrub_sensitive_text(msg.text, secrets),
                "location": msg.location,
                "time": datetime.now(timezone.utc).isoformat(),
            }
        ),
    )
    page.on(
        "requestfailed",
        lambda request: request_failures.append(
            {
                "url": scrub_sensitive_text(request.url, secrets),
                "method": request.method,
                "failure": scrub_sensitive_text(request.failure, secrets),
                "time": datetime.now(timezone.utc).isoformat(),
            }
        ),
    )

    async def on_response(response):
        nonlocal auth_success_seen
        if 200 <= response.status < 300 and any(token in response.url.lower() for token in ["/auth/login", "/login", "/api/auth"]):
            auth_success_seen = True
        if response.status >= 400:
            abnormal_responses.append(
                {
                    "url": scrub_sensitive_text(response.url, secrets),
                    "status": response.status,
                    "status_text": response.status_text,
                    "time": datetime.now(timezone.utc).isoformat(),
                }
            )

    page.on("response", on_response)

    visited = []
    shots = []
    findings = []
    idx = 1
    login_status = "skipped"
    login_note = "未提供管理员凭证。"
    try:
        entry = await collect_page(page, out_dir, "entry-before-login", entry_url, secrets=secrets)
        visited.append({k: v for k, v in entry.items() if k != "links"})
        shots.append(entry["screenshot"])

        if username and password:
            await page.goto(login_url, wait_until="networkidle", timeout=30000)
            shots.append(await safe_screenshot(page, out_dir, "login-trigger-opened"))
            await fill_first_available(
                page,
                [
                    "input[type='text']",
                    "input:not([type])",
                    "input[type='email']",
                    "input[type='tel']",
                    "input[name*='user' i]",
                    "input[name*='account' i]",
                    "input[name*='phone' i]",
                    "input[placeholder*='用户']",
                    "input[placeholder*='手机']",
                    "input[placeholder*='账号']",
                    "input[placeholder*='用户名']",
                ],
                username,
            )
            await fill_first_available(page, ["input[type='password']", "input[placeholder*='密码']"], password)
            await click_first_available(
                page,
                ["button:has-text('登录')", "button[type='submit']", "[role=button]:has-text('登录')", "text=登录"],
            )
            await page.wait_for_load_state("networkidle", timeout=30000)
            await page.wait_for_timeout(1200)
            login_status = "success" if await login_success_signal(page, username, auth_success_seen) else "unknown"
            login_note = f"登录后页面：{await page.title()}"
            after = await collect_page(page, out_dir, "after-login", page.url, secrets=secrets)
            visited.append({k: v for k, v in after.items() if k != "links"})
            shots.append(after["screenshot"])
            if login_status != "success":
                findings.append(
                    finding(
                        idx,
                        system=system,
                        target=page.url,
                        title="自动化登录态信号未确认",
                        severity="low",
                        priority="P4",
                        evidence="提交登录表单后，巡检代理未捕获账号标识、后台落地页、退出登录入口等稳定登录态信号；该项反映自动化识别边界，不等同于人工登录失败。",
                        recommendation="若人工登录已验证正常，本项应视为自动化巡检能力边界；后续可优化登录态识别规则，或用人工截图/服务端登录日志补充证据。",
                        business_impact="不证明网站登录故障，只降低本轮自动化深度浏览结论的可信度；人工登录正常时不应作为网站健康扣分项。",
                        confidence="automation-boundary",
                        evidence_files=shots[-2:],
                    )
                )
                idx += 1
            candidate_links = await collect_same_origin_links(page, entry_url)
        else:
            candidate_links = entry["links"]

        unique_urls = []
        for item in candidate_links:
            href = item.get("href", "")
            if not href or not same_origin(href, entry_url):
                continue
            parsed = urlparse(href)
            if any(word in parsed.path.lower() for word in ["logout", "delete", "remove", "payment"]):
                continue
            normalized = normalize_url(parsed._replace(fragment="").geturl())
            if normalized not in unique_urls and normalized.rstrip("/") != normalize_url(page.url):
                unique_urls.append(normalized)
            if len(unique_urls) >= 25:
                break

        for page_idx, target in enumerate(unique_urls, 1):
            try:
                item = await collect_page(page, out_dir, f"page-{page_idx}", target, secrets=secrets)
                visited.append({k: v for k, v in item.items() if k != "links"})
                shots.append(item["screenshot"])
                if item.get("rendered_status") == "in_app_404":
                    path = urlparse(target).path
                    severity = "low" if route_requires_parameters(path) else "medium"
                    findings.append(
                        finding(
                            idx,
                            system=system,
                            target=target,
                            title="前端路由返回站内 404 页面",
                            category="front-route-404",
                            severity=severity,
                            priority="P3" if severity == "low" else "P2",
                            evidence=f"rendered_status=in_app_404; actual={item['url']}",
                            recommendation="确认该入口是否应对当前账号开放；若是页脚或导航公开入口，应修复前端路由或隐藏无效入口。",
                            confidence="review-needed",
                            evidence_files=[item["screenshot"]],
                        )
                    )
                    idx += 1
                if "/login" in urlparse(item["url"]).path and urlparse(target).path not in {"", "/", "/login"}:
                    redirect_severity = "low" if login_status != "success" else "medium"
                    redirect_priority = "P4" if login_status != "success" else "P2"
                    redirect_confidence = "automation-boundary" if login_status != "success" else "review-needed"
                    redirect_impact = (
                        "发生在自动化登录态未确认之后，更可能反映巡检代理未保持有效会话或缺少角色权限基准；不能单独证明目标页面不可用。"
                        if login_status != "success"
                        else "可能影响受保护业务入口访问，需要确认该入口在当前账号权限下是否应直接可达。"
                    )
                    redirect_recommendation = (
                        "先用人工已确认登录态复测该入口，并对照角色权限预期表；若人工访问正常，应将本项归类为自动化会话边界。"
                        if login_status != "success"
                        else "确认登录态是否写入成功，以及该页面是否需要额外角色权限。"
                    )
                    findings.append(
                        finding(
                            idx,
                            system=system,
                            target=target,
                            title="受保护页面重定向至登录页",
                            severity=redirect_severity,
                            priority=redirect_priority,
                            evidence=f"automation_login_status={login_status}; target={target}, actual={item['url']}",
                            recommendation=redirect_recommendation,
                            business_impact=redirect_impact,
                            confidence=redirect_confidence,
                            evidence_files=[item["screenshot"]],
                        )
                    )
                    idx += 1
            except Exception as exc:  # noqa: BLE001
                findings.append(
                    finding(
                        idx,
                        system=system,
                        target=target,
                        title="登录后页面访问失败",
                        severity="medium",
                        priority="P2",
                        evidence=str(exc),
                        recommendation="确认该入口是否需要额外权限、后端服务是否可用，或前端路由是否发生异常。",
                        evidence_files=shots[:3],
                    )
                )
                idx += 1

        for item in request_failures:
            findings.append(
                finding(
                    idx,
                    system=system,
                    target=item.get("url", ""),
                    title="浏览器资源请求失败",
                    severity="medium",
                    priority="P2",
                    evidence=f"{item.get('method')} {item.get('failure')}",
                    recommendation="结合服务器日志、前端构建产物和后端接口状态进一步核查。",
                    evidence_files=shots[:3],
                )
            )
            idx += 1
        for item in abnormal_responses:
            if item.get("status") == 401 and "auth" in str(item.get("url", "")):
                severity, priority = "low", "P3"
            else:
                severity, priority = "medium", "P2"
            findings.append(
                finding(
                    idx,
                    system=system,
                    target=item.get("url", ""),
                    title="浏览器捕获到异常 HTTP 响应",
                    severity=severity,
                    priority=priority,
                    evidence=f"HTTP {item.get('status')} {item.get('status_text')}",
                    recommendation="确认该状态码是否为业务预期，若影响用户路径则定位对应接口。",
                    evidence_files=shots[:3],
                )
            )
            idx += 1

        status = "warning" if findings else "healthy"
        metrics = performance_metrics(visited)
        return {
            "report_type": "browser-inspection",
            "generated_at": now_iso(),
            "status": status,
            "score": 100 if not findings else max(0, 100 - len(findings) * 5),
            "summary": f"浏览器实测访问 {len(visited)} 个页面，记录 {len(findings)} 条发现；性能快照显示平均打开时间 {metrics.get('avg_open_time_ms') if metrics.get('avg_open_time_ms') is not None else '未采集'} ms。",
            "systems": [
                {
                    "system_id": system.get("id"),
                    "system_name": system.get("name"),
                    "status": status,
                    "visited_pages": len(visited),
                    "findings": len(findings),
                }
            ],
            "login": {"status": login_status, "note": login_note},
            "visited_pages": visited,
            "console_messages": console_messages,
            "request_failures": request_failures,
            "abnormal_responses": abnormal_responses,
            "screenshots": shots,
            "findings": findings,
            "metrics": metrics,
        }
    except Exception as exc:  # noqa: BLE001
        shot = None
        try:
            shot = await safe_screenshot(page, out_dir, "deep-browser-error")
        except Exception:  # noqa: BLE001
            pass
        findings.append(
            finding(
                idx,
                system=system,
                target=page.url or entry_url,
                title="浏览器深度巡检执行中断",
                severity="medium",
                priority="P2",
                evidence=str(exc),
                recommendation="检查登录表单识别、页面加载状态和浏览器自动化运行环境后重新巡检。",
                evidence_files=[shot] if shot else shots[:3],
            )
        )
        return {
            "report_type": "browser-inspection",
            "generated_at": now_iso(),
            "status": "warning",
            "score": max(0, 100 - len(findings) * 5),
            "summary": f"浏览器深度巡检执行中断，已访问 {len(visited)} 个页面；性能快照按已采集页面保留。",
            "systems": [
                {
                    "system_id": system.get("id"),
                    "system_name": system.get("name"),
                    "status": "warning",
                    "visited_pages": len(visited),
                    "findings": len(findings),
                }
            ],
            "login": {"status": login_status, "note": login_note},
            "visited_pages": visited,
            "console_messages": console_messages,
            "request_failures": request_failures,
            "abnormal_responses": abnormal_responses,
            "screenshots": shots + ([shot] if shot else []),
            "findings": findings,
            "metrics": performance_metrics(visited),
        }
    finally:
        await browser.close()


async def check_async(inventory: dict, out_dir: Path) -> dict:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        system = (inventory.get("systems") or [{}])[0]
        return await run_system(playwright, inventory, system, out_dir)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deep read-only browser inspection with optional administrator login.")
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out_dir = ensure_dir(args.out)
    inventory = read_json(args.inventory)
    sensitive_values = []
    for system in inventory.get("systems", []) or []:
        credentials = system.get("admin_credentials") or {}
        if credentials.get("password_env"):
            value = resolve_env_placeholder(f"${{{credentials.get('password_env')}}}")
            if value:
                sensitive_values.append(value)
    report = asyncio.run(check_async(inventory, out_dir))
    output = out_dir / "browser-inspection-report.json"
    write_json(output, report, explicit_sensitive_values=sensitive_values)
    print(output)


if __name__ == "__main__":
    main()
