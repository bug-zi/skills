#!/usr/bin/env python3
"""Export ordered slide images to a single PDF."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}


def natural_sort_key(value: str) -> list[object]:
    parts = re.split(r"(\d+)", value)
    key: list[object] = []
    for part in parts:
        if part.isdigit():
            key.append(int(part))
        else:
            key.append(part.lower())
    return key


def collect_images(input_dir: Path, pattern: str) -> list[Path]:
    files = []
    for path in input_dir.glob(pattern):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path)
    return sorted(files, key=lambda path: natural_sort_key(path.name))


def load_pillow():
    try:
        from PIL import Image
    except ImportError as exc:  # pragma: no cover - runtime dependency check
        raise SystemExit(
            "Pillow is required for PDF export. Install Pillow or use an environment "
            "that already includes it."
        ) from exc
    return Image


def convert_to_rgb(image):
    if image.mode == "RGB":
        return image

    if image.mode in {"RGBA", "LA"}:
        from PIL import Image

        background = Image.new("RGB", image.size, "white")
        alpha = image.getchannel("A") if "A" in image.getbands() else None
        background.paste(image.convert("RGBA"), mask=alpha)
        return background

    return image.convert("RGB")


def export_pdf(images: list[Path], output_path: Path) -> None:
    Image = load_pillow()
    opened = []
    try:
        for path in images:
            with Image.open(path) as img:
                opened.append(convert_to_rgb(img.copy()))

        if not opened:
            raise SystemExit("No supported images were found for PDF export.")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        opened[0].save(
            output_path,
            "PDF",
            save_all=True,
            append_images=opened[1:],
            resolution=150,
        )
    finally:
        for img in opened:
            img.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export ordered slide images from a directory into one PDF.",
    )
    parser.add_argument(
        "--input-dir",
        required=True,
        help="Directory containing final slide images.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Target PDF path.",
    )
    parser.add_argument(
        "--pattern",
        default="slide-*.*",
        help="Glob pattern used to discover images. Default: slide-*.*",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    if not input_dir.exists():
        parser.error(f"Input directory does not exist: {input_dir}")
    if not input_dir.is_dir():
        parser.error(f"Input path is not a directory: {input_dir}")

    images = collect_images(input_dir, args.pattern)
    if not images:
        parser.error(
            "No matching images found. Check --input-dir and --pattern, and make sure "
            "the directory contains final slide images."
        )

    export_pdf(images, output_path)
    print(f"Exported PDF: {output_path}")
    print(f"Pages: {len(images)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
