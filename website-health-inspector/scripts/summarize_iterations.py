from __future__ import annotations

import argparse
import json
from pathlib import Path


def read_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def summarize(runs_root: Path, start: int, end: int) -> str:
    rows = []
    for index in range(start, end + 1):
        run_dir = runs_root / f"iteration-{index:02d}"
        report_path = run_dir / "final-report.json"
        if not report_path.exists():
            rows.append((index, run_dir, "missing", "N/A", 0, 0, "未生成报告"))
            continue
        report = read_json(report_path)
        browser = next((m for m in report.get("module_reports", []) if m.get("report_type") == "browser-inspection"), {})
        login = (browser.get("login") or {}).get("status", "none")
        visited = len(browser.get("visited_pages", []))
        rows.append(
            (
                index,
                run_dir,
                report.get("overall_status", "unknown"),
                report.get("score", "N/A"),
                visited,
                len(report.get("priority_findings", [])),
                login,
            )
        )

    lines = [
        f"# 第 {start:02d}-{end:02d} 轮巡检迭代汇总",
        "",
        "| 轮次 | 状态 | 评分 | 浏览器页面 | 发现数 | 登录状态 | 报告 |",
        "|---:|---|---:|---:|---:|---|---|",
    ]
    for index, run_dir, status, score, visited, findings, login in rows:
        lines.append(f"| {index:02d} | {status} | {score} | {visited} | {findings} | {login} | `{run_dir / 'final-report.html'}` |")

    scores = [int(row[3]) for row in rows if isinstance(row[3], int)]
    if scores:
        lines.extend(
            [
                "",
                "## 趋势判断",
                "",
                f"- 评分范围：{min(scores)} 到 {max(scores)}。",
                f"- 最新评分：{scores[-1]}。",
                "- 如果评分稳定但登录状态仍为 unknown，应优先复核登录自动化信号与真实账号权限。",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize iterative website health inspection runs.")
    parser.add_argument("--runs-root", default="website-health-inspector/runs")
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(summarize(Path(args.runs_root), args.start, args.end), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
