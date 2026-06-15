from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import audit_report_quality  # noqa: E402
import check_deep_browser  # noqa: E402
import render_report  # noqa: E402


class PerformanceMonitoringTests(unittest.TestCase):
    def test_summarizes_browser_page_performance(self) -> None:
        visited = [
            {"performance": {"open_time_ms": 1200, "ttfb_ms": 120, "url": "https://example.test/"}},
            {"performance": {"open_time_ms": 3600, "ttfb_ms": 240, "url": "https://example.test/admin"}},
            {"performance": {"open_time_ms": None, "ttfb_ms": None, "url": "https://example.test/missing"}},
        ]

        metrics = check_deep_browser.performance_metrics(visited)

        self.assertEqual(metrics["checked_pages"], 3)
        self.assertEqual(metrics["avg_open_time_ms"], 2400)
        self.assertEqual(metrics["max_open_time_ms"], 3600)
        self.assertEqual(metrics["slow_pages"], 1)
        self.assertEqual(metrics["avg_ttfb_ms"], 180)
        self.assertEqual(metrics["max_ttfb_ms"], 240)

    def test_render_report_includes_performance_snapshot_and_markdown(self) -> None:
        report = {
            "generated_at": "2026-05-10T12:00:00+08:00",
            "overall_status": "healthy",
            "score": 96,
            "executive_summary": "本次巡检整体可用。",
            "summary": {"total_systems": 1, "healthy": 1, "warning": 0, "critical": 0, "unknown": 0},
            "systems": [],
            "priority_findings": [],
            "module_reports": [
                {
                    "report_type": "browser-inspection",
                    "status": "healthy",
                    "score": 100,
                    "summary": "浏览器巡检完成。",
                    "systems": [],
                    "login": {"status": "success", "note": "登录成功"},
                    "metrics": {
                        "checked_pages": 2,
                        "avg_open_time_ms": 2100,
                        "max_open_time_ms": 4200,
                        "slow_pages": 1,
                        "avg_ttfb_ms": 180,
                        "max_ttfb_ms": 260,
                    },
                    "visited_pages": [
                        {
                            "label": "entry-before-login",
                            "url": "https://example.test/",
                            "title": "首页",
                            "screenshot": "entry-before-login.png",
                            "performance": {"open_time_ms": 900, "ttfb_ms": 100},
                        },
                        {
                            "label": "after-login",
                            "url": "https://example.test/admin",
                            "title": "后台",
                            "screenshot": "after-login.png",
                            "performance": {"open_time_ms": 4200, "ttfb_ms": 260},
                        },
                    ],
                    "screenshots": [],
                    "request_failures": [],
                    "abnormal_responses": [],
                    "findings": [],
                }
            ],
            "artifacts": {},
        }

        html = render_report.render_body(report, None, None, None, {"status": "html_guide_selected"})
        markdown = render_report.render_markdown(report)

        self.assertIn("性能快照", html)
        self.assertIn("平均打开时间", html)
        self.assertIn("最慢页面", html)
        self.assertIn("4200 ms", html)
        self.assertIn("性能快照", markdown)
        self.assertIn("平均打开时间：2100 ms", markdown)

    def test_multi_site_overall_report_uses_batch_governance_layout(self) -> None:
        report = {
            "report_kind": "multi-site-overall",
            "generated_at": "2026-05-10T12:00:00+08:00",
            "overall_status": "warning",
            "score": 79,
            "executive_summary": "本次批量巡检覆盖 3 个网站，建议优先处理告警站点。",
            "summary": {"total_systems": 3, "healthy": 1, "warning": 1, "critical": 0, "unknown": 1},
            "systems": [],
            "site_results": [
                {
                    "index": 1,
                    "slug": "001-portal",
                    "name": "门户站",
                    "url": "https://portal.example.edu.cn",
                    "owner": "信息中心",
                    "status": "healthy",
                    "score": 96,
                    "findings": 0,
                    "quality_status": "passed",
                    "error": "",
                    "report": "sites/001-portal/delivery/final-report.html",
                },
                {
                    "index": 2,
                    "slug": "002-news",
                    "name": "新闻站",
                    "url": "https://news.example.edu.cn",
                    "owner": "宣传部",
                    "status": "warning",
                    "score": 82,
                    "findings": 1,
                    "quality_status": "passed",
                    "error": "",
                    "report": "sites/002-news/delivery/final-report.html",
                },
                {
                    "index": 3,
                    "slug": "003-missing",
                    "name": "缺地址站",
                    "url": "",
                    "owner": "教务处",
                    "status": "unknown",
                    "score": 0,
                    "findings": 1,
                    "quality_status": "failed",
                    "error": "URL 为空",
                    "report": "",
                },
            ],
            "batch_metrics": {
                "site_count": 3,
                "average_score": 59,
                "lowest_score": 0,
                "failed": 1,
                "quality_failed": 1,
                "status_distribution": {"total_systems": 3, "healthy": 1, "warning": 1, "critical": 0, "unknown": 1},
            },
            "priority_sites": [
                {
                    "index": 3,
                    "slug": "003-missing",
                    "name": "缺地址站",
                    "owner": "教务处",
                    "status": "unknown",
                    "score": 0,
                    "findings": 1,
                    "quality_status": "failed",
                    "reason": "URL 为空",
                    "report": "",
                }
            ],
            "common_issue_families": [
                {
                    "title": "站点巡检未完成",
                    "classification": "批次覆盖缺口",
                    "site_count": 1,
                    "finding_count": 1,
                    "severity": "medium",
                    "priority": "P2",
                    "owners": ["教务处"],
                    "sites": ["缺地址站"],
                    "next_action": "补齐 URL 后重新巡检。",
                }
            ],
            "priority_findings": [],
            "module_reports": [],
            "artifacts": {},
        }

        html = render_report.render_body(report, None, None, None, {"status": "html_guide_selected"})
        markdown = render_report.render_markdown(report)

        self.assertIn("批次总览与管理结论", html)
        self.assertIn("站点健康分布", html)
        self.assertIn("共性风险与问题族", html)
        self.assertIn("全量站点矩阵", html)
        self.assertIn('href="sites/002-news/delivery/final-report.html"', html)
        self.assertNotIn("管理员浏览器实测", html)
        self.assertIn("# 门户站、新闻站、缺地址站健康巡检总体报告", markdown)
        self.assertNotIn("# 多站点网站健康巡检总体报告", markdown)
        self.assertIn("## 全量站点矩阵", markdown)

    def test_quality_audit_requires_browser_performance_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            report = {
                "score": 90,
                "overall_status": "healthy",
                "priority_findings": [],
                "module_reports": [
                    {
                        "report_type": "browser-inspection",
                        "metrics": {"checked_pages": 1, "avg_open_time_ms": 1000, "max_open_time_ms": 1000, "slow_pages": 0},
                        "visited_pages": [{"performance": {"open_time_ms": 1000}}],
                        "screenshots": [],
                    }
                ],
            }
            (run_dir / "final-report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
            (run_dir / "final-report.html").write_text(
                '<section class="guide-cover"></section><nav class="report-nav"></nav>'
                '<details class="fold-section"></details><style>:root{--paper:#fff}</style>'
                "性能快照 平均打开时间",
                encoding="utf-8",
            )
            (run_dir / "final-report.md").write_text("性能快照", encoding="utf-8")

            structured = audit_report_quality.audit_structured(run_dir, 1)

            self.assertTrue(structured["checks"]["browser_performance_metrics_present"])
            self.assertTrue(structured["checks"]["performance_snapshot_present"])


if __name__ == "__main__":
    unittest.main()
