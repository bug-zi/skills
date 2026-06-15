#!/usr/bin/env python3
"""Reject damaged delivery text before the skill is installed."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEXT_EXTENSIONS = {".md", ".py", ".yaml", ".yml"}
EXCLUDED_DIRS = {".git", ".pytest_cache", "__pycache__", ".doops", "reports"}


def chars(*codepoints: int) -> str:
    return "".join(chr(codepoint) for codepoint in codepoints)


BAD_TEXT_MARKERS = (
    chr(0xFFFD),
    chars(0x951F, 0x65A4, 0x62F7),
    chars(0x00C3),
    chars(0x00C2),
    chars(0x00E2, 0x20AC),
    chars(0x00E6, 0x00B5),
    chars(0x00E9, 0x0178),
)


def default_paths() -> list[Path]:
    paths = [
        ROOT / "SKILL.md",
        ROOT / "agents" / "openai.yaml",
    ]
    for folder, pattern in (
        (ROOT / "references", "*.md"),
        (ROOT / "scripts", "*.py"),
        (ROOT / "tests", "*.py"),
    ):
        if folder.is_dir():
            paths.extend(sorted(folder.glob(pattern)))
    return paths


def iter_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        path = path.expanduser()
        if path.is_file():
            files.append(path)
            continue
        if not path.is_dir():
            files.append(path)
            continue
        for candidate in path.rglob("*"):
            if any(part in EXCLUDED_DIRS for part in candidate.parts):
                continue
            if candidate.is_file() and candidate.suffix.lower() in TEXT_EXTENSIONS:
                files.append(candidate)
    return sorted(dict.fromkeys(files))


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def console_safe(value: object) -> str:
    text = str(value)
    encoding = sys.stdout.encoding or "utf-8"
    return text.encode(encoding, "backslashreplace").decode(encoding, "replace")


def scan_file(path: Path) -> list[tuple[Path, int, str]]:
    if not path.is_file():
        return [(path, 0, "missing-file")]
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return [(path, 0, "invalid-utf-8")]
    hits: list[tuple[Path, int, str]] = []
    for marker in BAD_TEXT_MARKERS:
        start = 0
        while marker:
            index = text.find(marker, start)
            if index == -1:
                break
            hits.append((path, line_number(text, index), marker))
            start = index + len(marker)
    for match in re.finditer(r"\?{2,}", text):
        hits.append((path, line_number(text, match.start()), match.group(0)))
    return hits


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check skill text for mojibake and placeholder markers.")
    parser.add_argument("--path", action="append", help="File or directory to scan. May be repeated.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = [Path(item) for item in args.path] if args.path else default_paths()
    files = iter_files(paths)
    hits: list[tuple[Path, int, str]] = []
    for path in files:
        hits.extend(scan_file(path))
    if hits:
        print("Text integrity failed:")
        for path, line, marker in hits:
            display = path if path.is_absolute() else path.resolve()
            print(f"- {console_safe(display)}:{line}: {console_safe(marker)}")
        return 1
    print(f"Text integrity passed: {len(files)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
