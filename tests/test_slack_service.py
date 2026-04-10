from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import URLError

from gigoptimizer.config import GigOptimizerConfig
from gigoptimizer.services.dashboard_service import DashboardService
from gigoptimizer.services.settings_service import SettingsService
from gigoptimizer.services.slack_service import SlackService


class SlackServiceTests(unittest.TestCase):
    def test_comparison_complete_message_uses_structured_blocks(self) -> None:
        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "SLACK_WEBHOOK_URL": "https://hooks.slack.test/services/example",
                },
                clear=False,
            ):
                config = GigOptimizerConfig.from_env()
                settings = SettingsService(config)
                settings.update_settings({"slack": {"enabled": True}})
                service = SlackService(settings)

                captured: dict[str, object] = {}

                class MockResponse:
                    status = 200

                    def __enter__(self):
                        return self

                    def __exit__(self, exc_type, exc, tb):
                        return False

                def fake_urlopen(request, timeout=10):
                    captured["timeout"] = timeout
                    captured["payload"] = json.loads(request.data.decode("utf-8"))
                    return MockResponse()

                with patch("gigoptimizer.services.slack_service.urlopen", side_effect=fake_urlopen):
                    result = service.send_slack_message(
                        "comparison_complete",
                        {
                            "gig_url": "https://www.fiverr.com/example/my-gig",
                            "optimization_score": 92,
                            "recommended_title": "I will optimize WordPress speed and improve PageSpeed Insights",
                            "top_action": "Update the gig title to the recommended search-match version.",
                            "top_action_expected_gain": 14,
                            "competitor_count": 12,
                            "primary_search_term": "wordpress speed",
                            "top_ranked_gig": {
                                "rank_position": 1,
                                "title": "I will do wordpress speed optimization for google pagespeed insight",
                                "why_on_page_one": ["The title matches the searched phrase directly."],
                            },
                            "first_page_top_10": [
                                {
                                    "rank_position": 1,
                                    "title": "I will do wordpress speed optimization for google pagespeed insight",
                                    "starting_price": 30,
                                    "rating": 4.9,
                                    "reviews_count": 1000,
                                },
                                {
                                    "rank_position": 2,
                                    "title": "I will increase wordpress speed optimization for gtmetrix",
                                    "starting_price": 60,
                                    "rating": 5.0,
                                    "reviews_count": 804,
                                },
                            ],
                            "one_by_one_recommendations": [
                                {
                                    "rank_position": 1,
                                    "primary_recommendation": "Work the exact search phrase into your title.",
                                    "expected_gain": 16,
                                    "priority": "high",
                                },
                                {
                                    "rank_position": 2,
                                    "primary_recommendation": "Add a stronger proof block near the top.",
                                    "expected_gain": 12,
                                    "priority": "medium",
                                },
                            ],
                        },
                    )

        self.assertTrue(result.ok)
        self.assertEqual(captured["timeout"], 10)
        payload = captured["payload"]
        self.assertEqual(payload["blocks"][0]["text"]["text"], "Comparison Complete")
        self.assertIn("Optimization Score", json.dumps(payload))
        self.assertIn("PageSpeed Insights", json.dumps(payload))
        self.assertIn("Top 10 gigs on Fiverr page one", json.dumps(payload))
        self.assertIn("What to change against each top-10 gig", json.dumps(payload))

    def test_slack_failure_returns_result_without_crashing(self) -> None:
        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "SLACK_WEBHOOK_URL": "https://hooks.slack.test/services/example",
                },
                clear=False,
            ):
                config = GigOptimizerConfig.from_env()
                settings = SettingsService(config)
                settings.update_settings({"slack": {"enabled": True}})
                service = SlackService(settings, max_attempts=2, retry_delays=(0.0, 0.0))

                with patch("gigoptimizer.services.slack_service.urlopen", side_effect=URLError("network down")):
                    result = service.send_slack_message(
                        "system_error",
                        {
                            "error_message": "boom",
                            "job_id": "job-123",
                            "stack_trace": "line 1",
                        },
                    )

        self.assertFalse(result.ok)
        self.assertIn("network down", result.detail)


class DashboardMemoryTests(unittest.TestCase):
    def test_manual_compare_records_history_and_prioritized_actions_even_if_slack_fails(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

        class BrokenSlackService:
            def send_slack_message(self, event_type, payload):  # noqa: ANN001
                raise RuntimeError("slack unavailable")

        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "REPORTS_DIR": str(temp_root / "reports"),
                    "DASHBOARD_STATE_PATH": str(temp_root / "data" / "dashboard_state.json"),
                    "METRICS_HISTORY_PATH": str(temp_root / "data" / "metrics_history.json"),
                    "AGENT_HEALTH_PATH": str(temp_root / "data" / "agent_health.json"),
                    "APPROVAL_QUEUE_DB_PATH": str(temp_root / "data" / "approval_queue.db"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "DEFAULT_SNAPSHOT_PATH": str(example_snapshot),
                },
                clear=False,
            ):
                config = GigOptimizerConfig.from_env()
                settings = SettingsService(config)
                service = DashboardService(
                    config=config,
                    settings_service=settings,
                    slack_service=BrokenSlackService(),
                )
                state = service.compare_manual_market_input(
                    gig_url="",
                    competitor_input=(
                        "I will fix wordpress speed | 45 | 4.9 | 120 | 2 days | https://www.fiverr.com/example/1\n"
                        "I will improve pagespeed insights score | 55 | 5.0 | 84 | 1 day | https://www.fiverr.com/example/2"
                    ),
                    search_terms=["wordpress speed"],
                )
                gig_id = service._gig_identifier()  # noqa: SLF001
                history = service.repository.list_comparison_history(gig_id=gig_id, limit=5)

        blueprint = state["gig_comparison"]["implementation_blueprint"]
        comparison = state["gig_comparison"]
        self.assertTrue(history)
        self.assertTrue(blueprint["prioritized_actions"])
        self.assertIn("expected_gain", blueprint["top_action"])
        self.assertTrue(blueprint["do_this_first"])
        self.assertTrue(comparison["first_page_top_10"])
        self.assertTrue(comparison["one_by_one_recommendations"])


if __name__ == "__main__":
    unittest.main()
