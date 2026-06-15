from __future__ import annotations

import re
from urllib.parse import urlparse


STATIC_ROUTE_RE = re.compile(r"""(?:(?:path|route|to|href)\s*[:=]\s*|RouterLink\s+to=)['"](/[^'"?#\s<>]+)['"]""")
BARE_ROUTE_RE = re.compile(r"""['"](/(?:[A-Za-z0-9._~!$&'()*+,;=:@-]+/?){0,12})['"]""")
IN_APP_404_PATTERNS = [
    re.compile(r"(?i)\b404\b.{0,40}\b(not\s*found|page\s*not\s*found)\b"),
    re.compile(r"页面未找到|未找到页面|找不到页面|返回首页"),
]
SKIP_ROUTE_PREFIXES = ("/api/", "/assets/", "/static/", "/uploads/", "/_next/", "/vite/")


def route_requires_parameters(route: str) -> bool:
    text = str(route or "")
    return bool(re.search(r"(^|/):[A-Za-z_][A-Za-z0-9_]*", text) or re.search(r"\{[A-Za-z_][A-Za-z0-9_]*\}", text))


def normalize_route(route: str) -> str:
    text = str(route or "").strip()
    if not text.startswith("/"):
        return ""
    parsed = urlparse(text)
    path = parsed.path.rstrip("/") or "/"
    if any(path.startswith(prefix) for prefix in SKIP_ROUTE_PREFIXES):
        return ""
    if re.search(r"\.(js|css|png|jpe?g|gif|webp|svg|ico|woff2?|map)$", path, flags=re.I):
        return ""
    return path


def classify_rendered_page(path_or_url: str, body_text: str, status_code: int | None = None) -> str:
    if status_code and status_code >= 500:
        return "server_error"
    if status_code == 404:
        return "http_404"
    text = " ".join(str(body_text or "").split())
    if any(pattern.search(text) for pattern in IN_APP_404_PATTERNS):
        return "in_app_404"
    if route_requires_parameters(urlparse(path_or_url).path):
        return "parameterized_route"
    if text:
        return "rendered_ok"
    return "empty_render"


def extract_routes_from_script(script_text: str) -> list[str]:
    candidates: list[str] = []
    for pattern in [STATIC_ROUTE_RE, BARE_ROUTE_RE]:
        for match in pattern.findall(script_text or ""):
            route = normalize_route(match)
            if route:
                candidates.append(route)
    seen: set[str] = set()
    unique: list[str] = []
    for route in candidates:
        if route not in seen:
            seen.add(route)
            unique.append(route)
    if "/" in unique:
        unique = ["/", *[route for route in unique if route != "/"]]
    return unique


def extract_static_routes_from_script(script_text: str) -> list[str]:
    return [route for route in extract_routes_from_script(script_text) if not route_requires_parameters(route)]


def extract_parameterized_routes_from_script(script_text: str) -> list[str]:
    return [route for route in extract_routes_from_script(script_text) if route_requires_parameters(route)]
