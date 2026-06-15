from __future__ import annotations

import argparse
import re
import time
from collections import deque
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlparse

import requests

from health_common import ensure_dir, has_dangerous_word, read_json, slugify, write_json
from rendered_route_utils import extract_parameterized_routes_from_script, extract_static_routes_from_script


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.scripts: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag.lower() == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"])
        if tag.lower() == "script" and attrs_dict.get("src"):
            self.scripts.append(attrs_dict["src"])
        if tag.lower() == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data.strip()


def same_origin(a: str, b: str) -> bool:
    pa, pb = urlparse(a), urlparse(b)
    return (pa.scheme, pa.netloc) == (pb.scheme, pb.netloc)


def clean_url(base: str, href: str) -> str | None:
    if not href or href.startswith(("mailto:", "tel:", "javascript:")):
        return None
    joined, _ = urldefrag(urljoin(base, href))
    parsed = urlparse(joined)
    if parsed.scheme not in {"http", "https"}:
        return None
    return joined


def sitemap_urls(entry_url: str, timeout: float = 5.0) -> list[str]:
    parsed = urlparse(entry_url)
    sitemap = f"{parsed.scheme}://{parsed.netloc}/sitemap.xml"
    try:
        response = requests.get(sitemap, timeout=timeout)
        if response.status_code >= 400:
            return []
        return re.findall(r"<loc>\s*([^<]+)\s*</loc>", response.text, flags=re.I)
    except Exception:  # noqa: BLE001
        return []


def extract_script_sources(html_text: str, base_url: str) -> list[str]:
    parser = LinkParser()
    parser.feed(html_text[:500_000])
    seen: set[str] = set()
    scripts: list[str] = []
    for src in parser.scripts:
        joined = clean_url(base_url, src)
        if joined and same_origin(base_url, joined) and joined not in seen:
            seen.add(joined)
            scripts.append(joined)
    return scripts


def extract_spa_routes(script_text: str) -> dict[str, list[str]]:
    return {
        "static": extract_static_routes_from_script(script_text),
        "parameterized": extract_parameterized_routes_from_script(script_text),
    }


def fetch_spa_routes(page_url: str, html_text: str, timeout: float = 5.0) -> dict[str, list[str]]:
    static_routes: list[str] = []
    parameterized_routes: list[str] = []
    for script_url in extract_script_sources(html_text, page_url)[:8]:
        try:
            response = requests.get(script_url, timeout=timeout, headers={"User-Agent": "WebsiteHealthInspector/1.0"})
        except Exception:  # noqa: BLE001
            continue
        if response.status_code >= 400:
            continue
        routes = extract_spa_routes(response.text[:1_500_000])
        static_routes.extend(routes["static"])
        parameterized_routes.extend(routes["parameterized"])
    return {
        "static": list(dict.fromkeys(static_routes)),
        "parameterized": list(dict.fromkeys(parameterized_routes)),
    }


def discover(entry_url: str, *, max_depth: int = 1, max_pages: int = 20, interval_ms: int = 200) -> dict:
    seen = set()
    pages = []
    skipped = []
    queue = deque([(entry_url, 0, "entry")])

    for item in sitemap_urls(entry_url):
        if same_origin(entry_url, item):
            queue.append((item, 1, "sitemap"))

    while queue and len(pages) < max_pages:
        url, depth, source = queue.popleft()
        if url in seen:
            continue
        seen.add(url)
        if not same_origin(entry_url, url):
            skipped.append({"url": url, "reason": "cross_origin"})
            continue
        if has_dangerous_word(url):
            skipped.append({"url": url, "reason": "dangerous_keyword"})
            continue
        try:
            start = time.perf_counter()
            response = requests.get(url, timeout=8, headers={"User-Agent": "WebsiteHealthInspector/1.0"})
            latency_ms = int((time.perf_counter() - start) * 1000)
            parser = LinkParser()
            content_type = response.headers.get("content-type", "")
            if "text/html" in content_type:
                parser.feed(response.text[:500_000])
            page = {
                "url": url,
                "title": parser.title[:120],
                "status_code": response.status_code,
                "latency_ms": latency_ms,
                "depth": depth,
                "source": source,
                "selected_for_inspection": response.status_code < 500,
            }
            pages.append(page)
            if depth < max_depth and "text/html" in content_type:
                for href in parser.links:
                    child = clean_url(url, href)
                    if child and child not in seen:
                        queue.append((child, depth + 1, "link"))
                if depth == 0:
                    routes = fetch_spa_routes(url, response.text)
                    for route in routes["static"]:
                        child = clean_url(url, route)
                        if child and child not in seen:
                            queue.append((child, depth + 1, "spa-route"))
                    if routes["parameterized"]:
                        page["parameterized_routes"] = routes["parameterized"][:50]
            if interval_ms:
                time.sleep(interval_ms / 1000)
        except Exception as exc:  # noqa: BLE001
            skipped.append({"url": url, "reason": f"request_failed: {exc}"})
    return {"entry_url": entry_url, "pages": pages, "skipped": skipped}


def merge_inventory(inventory: dict, discovery: dict) -> dict:
    if not inventory.get("systems"):
        return inventory
    system = inventory["systems"][0]
    existing = {page.get("url") for page in system.get("websites", [])}
    for page in discovery.get("pages", []):
        if not page.get("selected_for_inspection") or page["url"] in existing:
            continue
        system.setdefault("websites", []).append(
            {
                "page_id": slugify(page.get("title") or page["url"], "discovered"),
                "name": page.get("title") or "发现页面",
                "url": page["url"],
                "expected_status": 200,
                "timeout_ms": 5000,
                "content_checks": {
                    "required_text": [],
                    "forbidden_text": ["404", "500", "系统维护", "系统繁忙", "服务不可用", "Internal Server Error"],
                    "min_length": 80,
                },
                "source": "discovery",
            }
        )
        existing.add(page["url"])
    return inventory


def main() -> None:
    parser = argparse.ArgumentParser(description="Controlled same-origin page discovery.")
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--merge", action="store_true")
    args = parser.parse_args()

    inventory = read_json(args.inventory)
    out_dir = ensure_dir(args.out)
    crawler = inventory.get("global", {}).get("crawler", {})
    all_discoveries = []
    for system in inventory.get("systems", []):
        for page in system.get("websites", [])[:1]:
            all_discoveries.append(
                discover(
                    page["url"],
                    max_depth=int(crawler.get("max_depth", 1)),
                    max_pages=int(crawler.get("max_pages", 20)),
                    interval_ms=int(crawler.get("request_interval_ms", 200)),
                )
            )
            if args.merge:
                inventory = merge_inventory(inventory, all_discoveries[-1])
    result = {"discoveries": all_discoveries}
    write_json(Path(out_dir) / "discovered-pages.json", result)
    if args.merge:
        write_json(args.inventory, inventory)
    print(Path(out_dir) / "discovered-pages.json")


if __name__ == "__main__":
    main()
