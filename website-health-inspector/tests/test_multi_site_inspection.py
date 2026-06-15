from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from run_multi_site_inspection import (  # noqa: E402
    SiteRunResult,
    build_batch_summary,
    build_overall_report,
    copy_tree,
    load_site_entries_from_excel,
    parse_args,
    render_batch_index,
    resolved_path,
    reviewed_site_result,
    split_inventory_by_website,
)


class MultiSiteInspectionTests(unittest.TestCase):
    def write_workbook(self, workbook: Workbook) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        path = Path(temp_dir.name) / "sites.xlsx"
        workbook.save(path)
        return path

    def test_load_simple_excel_accepts_aliases_and_preserves_missing_url_rows(self) -> None:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "网站列表"
        sheet.append(["网站名称", "URL", "负责人", "优先级", "备注", "期望状态码", "超时时间"])
        sheet.append(["门户站", "example.edu.cn", "信息中心", "high", "首页", 200, 7000])
        sheet.append(["缺地址站", "", "教务处", "medium", "待补充", 200, 5000])

        entries = load_site_entries_from_excel(self.write_workbook(workbook))

        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].name, "门户站")
        self.assertEqual(entries[0].url, "https://example.edu.cn")
        self.assertEqual(entries[0].owner, "信息中心")
        self.assertEqual(entries[0].priority, "high")
        self.assertEqual(entries[0].expected_status, 200)
        self.assertEqual(entries[0].timeout_ms, 7000)
        self.assertIsNone(entries[0].error)
        self.assertEqual(entries[1].name, "缺地址站")
        self.assertEqual(entries[1].error, "URL 为空")

    def test_split_standard_inventory_by_website_creates_one_inventory_per_page(self) -> None:
        inventory = {
            "generated_at": "2026-05-10T12:00:00+08:00",
            "source": {"type": "excel", "path": "inventory.xlsx"},
            "global": {"allow_mutation": False, "max_parallel": 5},
            "systems": [
                {
                    "id": "school",
                    "name": "学校门户群",
                    "priority": "critical",
                    "owner": "信息中心",
                    "environment": "prod",
                    "remark": "标准清单",
                    "websites": [
                        {"page_id": "home", "name": "主页", "url": "https://a.example.edu.cn"},
                        {"page_id": "news", "name": "新闻", "url": "https://b.example.edu.cn"},
                    ],
                    "admin_flows": [{"flow_id": "readonly"}],
                    "hosts": [{"host_id": "web-1"}],
                    "services": [{"service_id": "health"}],
                }
            ],
        }

        pairs = split_inventory_by_website(inventory)

        self.assertEqual(len(pairs), 2)
        first_entry, first_inventory = pairs[0]
        self.assertEqual(first_entry.name, "学校门户群 - 主页")
        self.assertEqual(first_entry.owner, "信息中心")
        self.assertEqual(first_inventory["systems"][0]["websites"], [inventory["systems"][0]["websites"][0]])
        self.assertEqual(first_inventory["systems"][0]["admin_flows"], [{"flow_id": "readonly"}])
        self.assertEqual(first_inventory["systems"][0]["hosts"], [{"host_id": "web-1"}])

    def test_build_overall_report_aggregates_successes_and_failures(self) -> None:
        results = [
            SiteRunResult(
                index=1,
                slug="001-portal",
                name="门户站",
                url="https://portal.example.edu.cn",
                owner="信息中心",
                run_dir=Path("runs/sites/001-portal"),
                delivery_entry=Path("runs/sites/001-portal/delivery/final-report.html"),
                status="healthy",
                score=96,
                findings_count=0,
                report={
                    "priority_findings": [],
                    "systems": [{"system_id": "portal", "system_name": "门户站", "status": "healthy", "findings": 0}],
                },
            ),
            SiteRunResult(
                index=2,
                slug="002-news",
                name="新闻网",
                url="https://news.example.edu.cn",
                owner="宣传部",
                run_dir=Path("runs/sites/002-news"),
                delivery_entry=Path("runs/sites/002-news/delivery/final-report.html"),
                status="warning",
                score=82,
                findings_count=1,
                report={
                    "priority_findings": [
                        {
                            "id": "content-001",
                            "system_id": "news",
                            "system_name": "新闻网",
                            "severity": "medium",
                            "priority": "P2",
                            "title": "页面内容过短",
                            "business_impact": "页面可能未完整渲染。",
                            "technical_evidence": "body_length=20",
                            "target": "https://news.example.edu.cn",
                            "recommendation": "复核页面发布状态。",
                            "evidence_files": ["page.png"],
                        }
                    ],
                    "systems": [{"system_id": "news", "system_name": "新闻网", "status": "warning", "findings": 1}],
                },
            ),
            SiteRunResult(
                index=3,
                slug="003-missing",
                name="缺地址站",
                url="",
                owner="教务处",
                run_dir=Path("runs/sites/003-missing"),
                delivery_entry=None,
                status="unknown",
                score=0,
                findings_count=1,
                error="URL 为空",
                report=None,
            ),
        ]

        overall = build_overall_report(results)

        self.assertEqual(overall["summary"]["total_systems"], 3)
        self.assertEqual(overall["summary"]["healthy"], 1)
        self.assertEqual(overall["summary"]["warning"], 1)
        self.assertEqual(overall["summary"]["unknown"], 1)
        self.assertEqual(overall["overall_status"], "unknown")
        self.assertEqual(len(overall["priority_findings"]), 2)
        self.assertEqual(overall["priority_findings"][0]["system_name"], "缺地址站")
        self.assertEqual(overall["priority_findings"][1]["evidence_files"], [])
        self.assertEqual(overall["report_kind"], "multi-site-overall")
        self.assertEqual(overall["batch_metrics"]["site_count"], 3)
        self.assertEqual(overall["batch_metrics"]["quality_failed"], 1)
        self.assertEqual(overall["batch_metrics"]["lowest_score"], 0)
        self.assertEqual(overall["batch_metrics"]["average_score"], 59)
        self.assertEqual(overall["batch_metrics"]["status_distribution"], overall["summary"])
        self.assertEqual(overall["site_results"][1]["report"], "sites/002-news/delivery/final-report.html")
        self.assertEqual(overall["site_results"][2]["error"], "URL 为空")
        self.assertEqual(overall["priority_sites"][0]["slug"], "003-missing")
        self.assertEqual(overall["priority_sites"][1]["slug"], "002-news")
        self.assertEqual(overall["common_issue_families"][0]["title"], "站点巡检未完成")
        self.assertEqual(overall["common_issue_families"][0]["site_count"], 1)

        summary = build_batch_summary(results, Path("runs/batch"), Path("runs/batch/delivery-batch"))
        self.assertEqual(summary["counts"]["total"], 3)
        self.assertEqual(summary["counts"]["failed"], 1)
        self.assertEqual(summary["sites"][1]["report"], "sites/002-news/delivery/final-report.html")

    def test_render_batch_index_uses_relative_report_links(self) -> None:
        results = [
            SiteRunResult(
                index=1,
                slug="001-portal",
                name="门户站",
                url="https://portal.example.edu.cn",
                owner="信息中心",
                run_dir=Path("runs/sites/001-portal"),
                delivery_entry=Path("runs/sites/001-portal/delivery/final-report.html"),
                status="healthy",
                score=96,
                findings_count=0,
            )
        ]

        html = render_batch_index(results, overall_href="overall/final-report.html")

        self.assertIn('href="overall/final-report.html"', html)
        self.assertIn('href="sites/001-portal/delivery/final-report.html"', html)
        self.assertIn("门户站", html)
        self.assertIn("https://portal.example.edu.cn", html)

    def test_multi_site_review_reconciles_100_warning_site_to_healthy(self) -> None:
        result = SiteRunResult(
            index=1,
            slug="001-admin",
            name="管理平台",
            url="https://admin.example.edu.cn",
            owner="信息中心",
            run_dir=Path("runs/sites/001-admin"),
            delivery_entry=Path("runs/sites/001-admin/delivery/final-report.html"),
            status="warning",
            score=100,
            findings_count=1,
            report={
                "overall_status": "warning",
                "score": 100,
                "priority_findings": [
                    {
                        "id": "login-boundary",
                        "system_id": "admin",
                        "system_name": "管理平台",
                        "severity": "low",
                        "priority": "P4",
                        "title": "自动化登录态信号未确认",
                        "category": "admin-login-unconfirmed",
                        "confidence": "automation-boundary",
                        "target": "https://admin.example.edu.cn",
                    }
                ],
            },
            quality_status="failed",
        )

        reviewed = reviewed_site_result(result)
        overall = build_overall_report([reviewed])

        self.assertEqual(reviewed.status, "healthy")
        self.assertEqual(overall["summary"]["healthy"], 1)
        self.assertEqual(overall["summary"]["warning"], 0)
        self.assertEqual(overall["priority_sites"][0]["reason"], "质量审计状态为 failed")
        self.assertEqual(overall["priority_sites"][0]["status"], "healthy")

    def test_multi_site_does_not_default_to_skipping_ai_guide(self) -> None:
        old_argv = sys.argv
        sys.argv = ["run_multi_site_inspection.py", "--excel", "sites.xlsx", "--out", "runs/batch"]
        try:
            args = parse_args()
        finally:
            sys.argv = old_argv

        self.assertEqual(args.guide_mode, "auto")
        self.assertFalse(args.skip_ai_guide_image)

    def test_resolved_path_makes_child_process_inputs_absolute(self) -> None:
        path = resolved_path(Path("runs") / "batch")

        self.assertTrue(path.is_absolute())
        self.assertTrue(str(path).endswith(str(Path("runs") / "batch")))

    def test_copy_tree_handles_deep_delivery_paths(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        source = root / "source"
        deep_dir = source / ("nested-" + "a" * 30) / ("screenshots-" + "b" * 30)
        deep_dir.mkdir(parents=True)
        deep_file = deep_dir / ("screenshot-" + "c" * 80 + ".png")
        deep_file.write_bytes(b"fake image")
        target = root / "target"

        copy_tree(source, target)

        copied = next(target.rglob("*.png"))
        self.assertEqual(copied.read_bytes(), b"fake image")


if __name__ == "__main__":
    unittest.main()
