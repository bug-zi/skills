#!/usr/bin/env python3
"""Static anti-AI-taste scanner for frontend UI files.

This script intentionally uses only the Python standard library. It catches
common code/text fingerprints of generic AI-generated frontend work; it does
not replace visual review.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SCAN_EXTENSIONS = {
    ".html",
    ".htm",
    ".css",
    ".scss",
    ".sass",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".svelte",
    ".astro",
}

DOC_EXTENSIONS = {".md", ".mdx"}

SKIP_DIRS = {
    ".git",
    ".next",
    ".nuxt",
    ".svelte-kit",
    "node_modules",
    "dist",
    "build",
    "coverage",
    "vendor",
}


@dataclass
class Finding:
    severity: str
    file: Path
    line: int
    title: str
    detail: str


def iter_files(paths: Iterable[Path], include_docs: bool) -> Iterable[Path]:
    extensions = set(SCAN_EXTENSIONS)
    if include_docs:
        extensions.update(DOC_EXTENSIONS)
    for path in paths:
        if not path.exists():
            continue
        if path.is_file():
            if path.suffix.lower() in extensions:
                yield path
            continue
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for name in files:
                candidate = Path(root) / name
                if candidate.suffix.lower() in extensions:
                    yield candidate


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            return path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            return None
    except OSError:
        return None


def line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def add(
    findings: list[Finding],
    severity: str,
    path: Path,
    text: str,
    index: int,
    title: str,
    detail: str,
) -> None:
    findings.append(Finding(severity, path, line_number(text, index), title, detail))


def scan_file(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    lower = text.lower()

    # P0: likely layout breakage or inaccessible interaction.
    for match in re.finditer(r"\b(?:w-\[\d{3,}px\]|min-w-\[\d{3,}px\]|width:\s*\d{3,}px|min-width:\s*\d{3,}px)\b", text):
        add(
            findings,
            "FAIL",
            path,
            text,
            match.start(),
            "Fixed wide width",
            "Large fixed widths often create mobile overflow. Use responsive constraints instead.",
        )

    for match in re.finditer(r"<button\b(?:(?!aria-label|aria-labelledby|title).)*?>\s*(?:<svg\b|<i\b)", text, re.I | re.S):
        add(
            findings,
            "FAIL",
            path,
            text,
            match.start(),
            "Unlabelled icon button",
            "Icon-only buttons need aria-label, aria-labelledby, or a visible text label.",
        )

    for match in re.finditer(r"overflow-x-(?:scroll|auto)|overflow-x:\s*(?:scroll|auto)", lower):
        add(
            findings,
            "FAIL",
            path,
            text,
            match.start(),
            "Horizontal scrolling",
            "Horizontal scrolling is a P0 issue unless it is a deliberate data-table region.",
        )

    # P1: common AI taste fingerprints.
    for match in re.finditer(r"\b(?:from|via|to)-(?:purple|violet|indigo|blue)-\d{2,3}\b", text):
        add(
            findings,
            "WARN",
            path,
            text,
            match.start(),
            "Default blue-purple gradient",
            "Check whether this gradient is brand-driven or just generic AI startup styling.",
        )

    for match in re.finditer(r"\b(?:backdrop-blur|glassmorphism|bg-white/10|bg-white/20|shadow-2xl|rounded-3xl)\b", text, re.I):
        add(
            findings,
            "WARN",
            path,
            text,
            match.start(),
            "Generic glass/card styling",
            "Heavy blur, huge radius, and large shadows are common AI UI fingerprints when overused.",
        )

    for match in re.finditer(r"\b(?:orb|blob|bokeh|glow|mesh-gradient|gradient-mesh)\b", lower):
        add(
            findings,
            "WARN",
            path,
            text,
            match.start(),
            "Decorative atmosphere keyword",
            "Remove decorative orbs/glows unless they carry product or brand meaning.",
        )

    for match in re.finditer(r">\s*(?:Get started|Learn more|Start now|Explore|Discover more)\s*<", text, re.I):
        add(
            findings,
            "WARN",
            path,
            text,
            match.start(),
            "Generic CTA copy",
            "Use action-specific CTA copy when a concrete next step exists.",
        )

    for match in re.finditer(r"[\U0001F300-\U0001FAFF]", text):
        add(
            findings,
            "WARN",
            path,
            text,
            match.start(),
            "Emoji in UI source",
            "Do not use emoji as structural icons. Prefer a consistent icon family.",
        )

    for match in re.finditer(r"\b(?:uptime|global nodes?|live status|system online|weather|timezone|command palette)\b", lower):
        add(
            findings,
            "WARN",
            path,
            text,
            match.start(),
            "Decorative product signal",
            "Operational signals should be real product functions, not decorative chrome.",
        )

    for match in re.finditer(r"\b(?:metric|kpi|stat|revenue|users|growth|conversion)\b", lower):
        window = lower[match.start() : match.start() + 600]
        has_number = re.search(r"\d", window)
        has_context = re.search(r"\b(?:today|week|month|quarter|year|last\s+\d+|daily|monthly|annual|%|ms|s|usd|\$|users?|requests?|sessions?)\b", window)
        if has_number and not has_context:
            add(
                findings,
                "WARN",
                path,
                text,
                match.start(),
                "Metric may lack context",
                "Dashboard metrics need units, time ranges, or source labels.",
            )

    # File-level repeated-card heuristic.
    card_like = len(re.findall(r"\b(?:rounded-|shadow-|card|feature-card)\b", lower))
    icon_title_copy = len(re.findall(r"\b(?:icon|lucide|svg)\b", lower)) and len(re.findall(r"\b(?:title|heading|description|paragraph)\b", lower))
    if card_like >= 12 and icon_title_copy:
        findings.append(
            Finding(
                "WARN",
                path,
                1,
                "Repeated card pattern",
                "This file has many card/radius/shadow markers. Check for repeated icon-title-paragraph sections.",
            )
        )

    return findings


def format_finding(base: Path, finding: Finding) -> str:
    try:
        shown = finding.file.resolve().relative_to(base.resolve())
    except ValueError:
        shown = finding.file
    return f"[{finding.severity}] {shown}:{finding.line} {finding.title} - {finding.detail}"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Scan frontend files for common AI-taste fingerprints.")
    parser.add_argument("paths", nargs="+", help="Files or directories to scan.")
    parser.add_argument("--max-findings", type=int, default=80, help="Maximum findings to print.")
    parser.add_argument("--include-docs", action="store_true", help="Also scan .md and .mdx files.")
    args = parser.parse_args(argv)

    roots = [Path(p) for p in args.paths]
    files = sorted(set(iter_files(roots, args.include_docs)))
    findings: list[Finding] = []
    unreadable: list[Path] = []

    for file in files:
        text = read_text(file)
        if text is None:
            unreadable.append(file)
            continue
        findings.extend(scan_file(file, text))

    fail_count = sum(1 for f in findings if f.severity == "FAIL")
    warn_count = sum(1 for f in findings if f.severity == "WARN")

    status = "PASS"
    if fail_count:
        status = "FAIL"
    elif warn_count:
        status = "WARN"

    print(f"Frontend Taste Lint: {status}")
    print(f"Scanned files: {len(files)}")
    print(f"Findings: {fail_count} FAIL, {warn_count} WARN")

    if unreadable:
        print(f"Unreadable files skipped: {len(unreadable)}")

    if findings:
        print()
        for finding in findings[: args.max_findings]:
            print(format_finding(Path.cwd(), finding))
        if len(findings) > args.max_findings:
            print(f"... {len(findings) - args.max_findings} more findings omitted")

    if fail_count:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
