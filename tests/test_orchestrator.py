from __future__ import annotations

import json
import unittest
from pathlib import Path

from gigoptimizer.config import GigOptimizerConfig
from gigoptimizer.models import GigSnapshot
from gigoptimizer.models import ConnectorStatus, GigAnalytics, KeywordSignal
from gigoptimizer.orchestrator import GigOptimizerOrchestrator


class GigOptimizerTests(unittest.TestCase):
    def setUp(self) -> None:
        example_path = Path(__file__).resolve().parent.parent / "examples" / "wordpress_speed_snapshot.json"
        self.snapshot = GigSnapshot.from_dict(json.loads(example_path.read_text(encoding="utf-8")))
        self.orchestrator = GigOptimizerOrchestrator()

    def test_generates_report_for_wordpress_speed_snapshot(self) -> None:
        report = self.orchestrator.optimize(self.snapshot)

        self.assertGreaterEqual(report.optimization_score, 1)
        self.assertEqual(report.persona_insights[0].persona, "WooCommerce Store Owner")
        self.assertGreaterEqual(len(report.title_variants), 4)
        self.assertIn("core web vitals", " ".join(report.niche_pulse.trending_queries).lower())
        self.assertAlmostEqual(report.conversion_audit.impression_to_click_rate or 0, 2.62, places=2)
        self.assertTrue(any("title" in item.lower() or "keyword" in item.lower() for item in report.weekly_action_plan))

    def test_report_serializes_to_plain_dict(self) -> None:
        report = self.orchestrator.optimize(self.snapshot)
        payload = report.to_dict()

        self.assertIn("optimization_score", payload)
        self.assertIn("persona_insights", payload)
        self.assertIn("review_follow_up_template", payload)

    def test_live_connector_signals_flow_into_the_report(self) -> None:
        class FakeGoogleTrends:
            def fetch_keyword_signals(self, keywords):
                return (
                    [
                        KeywordSignal(
                            keyword="wordpress lcp optimization",
                            source="google_trends",
                            trend_score=91.0,
                            rising=True,
                        )
                    ],
                    ConnectorStatus("google_trends", "ok", "fake trends ok"),
                )

        class FakeSemrush:
            def fetch_keyword_signals(self, keywords):
                return (
                    [
                        KeywordSignal(
                            keyword="wordpress lcp optimization",
                            source="semrush",
                            search_volume=2900,
                            keyword_difficulty=47.0,
                        )
                    ],
                    ConnectorStatus("semrush", "ok", "fake semrush ok"),
                )

        class FakeFiverr:
            def fetch_seller_metrics(self):
                return (
                    GigAnalytics(
                        impressions=2000,
                        clicks=30,
                        orders=3,
                        saves=12,
                        average_response_time_hours=1.5,
                    ),
                    ConnectorStatus("fiverr", "ok", "fake fiverr ok"),
                )

        orchestrator = GigOptimizerOrchestrator(
            config=GigOptimizerConfig(),
            google_trends=FakeGoogleTrends(),
            semrush=FakeSemrush(),
            fiverr=FakeFiverr(),
        )

        report = orchestrator.optimize(self.snapshot, use_live_connectors=True)

        self.assertEqual(len(report.connector_status), 3)
        self.assertEqual(report.connector_status[0].status, "ok")
        self.assertIn("wordpress lcp optimization", report.niche_pulse.trending_queries)
        self.assertAlmostEqual(report.conversion_audit.impression_to_click_rate or 0, 1.5, places=2)
        self.assertTrue(
            any(signal.source == "semrush" for signal in report.niche_pulse.live_keyword_signals)
        )


if __name__ == "__main__":
    unittest.main()
