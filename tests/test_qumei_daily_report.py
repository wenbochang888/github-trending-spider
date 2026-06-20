# -*- coding: utf-8 -*-

import unittest

from qumei_daily_report import build_report


class QumeiDailyReportTest(unittest.TestCase):
    def test_build_report_from_frontier_items(self):
        payload = {
            "generated_at": "2026-06-20T08:00:00",
            "item_count": 3,
            "items": [
                {
                    "source": "GitHub Trending Daily",
                    "title": "example/agent-skills",
                    "original_summary": "Production-grade agent skills and MCP tools.",
                    "meta": {"priority_score": 100},
                },
                {
                    "source": "TLDR AI",
                    "title": "Securing the future of AI agents",
                    "original_summary": "Agent security, privacy, and control roadmap.",
                    "meta": {"priority_score": 90},
                },
                {
                    "source": "OpenAI",
                    "title": "New usage analytics and updated spend controls for enterprises",
                    "original_summary": "Usage analytics, spend controls, and enterprise cost governance.",
                    "meta": {"priority_score": 80},
                },
            ],
        }
        report = build_report(payload, {"frontier": "可用", "token": "未配置"}, "2026年6月20日")

        self.assertIn("曲美产品部 AI晨报｜2026年6月20日", report)
        self.assertIn("今日重点", report)
        self.assertIn("AI Daily Frontier 摘要", report)
        self.assertIn("GitHub Token 未配置", report)
        self.assertIn("example/agent-skills", report)


if __name__ == "__main__":
    unittest.main()
