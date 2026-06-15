from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from health_common import ensure_dir, read_json, write_json


COLORS = {
    "healthy": "#2f6b4f",
    "warning": "#b7791f",
    "critical": "#a33a2b",
    "unknown": "#6b7280",
}
LABELS = {"healthy": "整体正常", "warning": "需要关注", "critical": "存在严重风险", "unknown": "覆盖不足"}


def font(size: int, bold: bool = False):
    candidates = [
        "C:/Windows/Fonts/simhei.ttf" if bold else "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simkai.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def wrap_text(draw, text: str, fnt, max_width: int) -> list[str]:
    lines = []
    current = ""
    for char in text:
        test = current + char
        if draw.textbbox((0, 0), test, font=fnt)[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def draw_summary(report: dict, output: Path) -> Path:
    image = Image.new("RGB", (1600, 900), "#f7f1e8")
    draw = ImageDraw.Draw(image)
    title_font = font(76, True)
    h_font = font(34, True)
    body_font = font(32)
    small_font = font(24)
    status = report.get("overall_status", "unknown")
    score = report.get("score", 0)
    findings = report.get("priority_findings", [])[:3]

    draw.text((104, 86), "管理平台网站健康巡检", fill="#1b365d", font=small_font)
    draw.text((104, 128), "网站健康巡检摘要", fill="#27231d", font=title_font)
    badge_color = COLORS.get(status, COLORS["unknown"])
    draw.rounded_rectangle((104, 246, 360, 300), radius=6, fill=badge_color)
    draw.text((126, 255), LABELS.get(status, "状态未知"), fill="#ffffff", font=h_font)
    draw.text((390, 242), f"{score} / 100", fill="#1b365d", font=font(54, True))

    summary = report.get("executive_summary", "")
    y = 348
    for line in wrap_text(draw, summary, body_font, 1280)[:4]:
        draw.text((104, y), line, fill="#27231d", font=body_font)
        y += 50

    x = 104
    for finding in findings:
        draw.line((x, 610, x + 410, 610), fill="#1b365d", width=4)
        title = finding.get("title", "未命名问题")
        for i, line in enumerate(wrap_text(draw, title, font(28, True), 390)[:3]):
            draw.text((x, 634 + i * 40), line, fill="#27231d", font=font(28, True))
        x += 450

    draw.text((104, 820), f"生成时间：{report.get('generated_at', '')}", fill="#776f64", font=small_font)
    ensure_dir(output.parent)
    image.save(output)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate executive summary PNG.")
    parser.add_argument("--report", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    output = Path(args.out) / "executive-summary.png"
    draw_summary(read_json(args.report), output)
    print(output)


if __name__ == "__main__":
    main()
