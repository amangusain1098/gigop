from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from gigoptimizer.models import ConnectorStatus, GigPageOverview, MarketplaceGig
from gigoptimizer.services.dashboard_service import DashboardService


class MarketplaceKeywordSwitchTests(unittest.TestCase):
    def test_explicit_mismatched_terms_do_not_fall_back_to_snapshot_competitors(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

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
                    "APP_AUTH_ENABLED": "false",
                },
                clear=False,
            ):
                service = DashboardService()
                my_gig = GigPageOverview(
                    url="https://www.fiverr.com/example/wordpress-speed",
                    title="I will fix wordpress speed and core web vitals",
                    seller_name="Example",
                    description_excerpt="WordPress speed optimization service.",
                    starting_price=45.0,
                    rating=4.9,
                    reviews_count=42,
                    tags=["wordpress speed", "core web vitals"],
                )
                with patch.object(
                    service.orchestrator.marketplace,
                    "fetch_gig_page_overview",
                    return_value=(my_gig, ConnectorStatus("fiverr_marketplace", "ok", "Loaded test gig.")),
                ), patch.object(
                    service.orchestrator.marketplace,
                    "fetch_competitor_gigs",
                    return_value=([], ConnectorStatus("fiverr_marketplace", "warning", "No live gigs found.")),
                ), patch.object(
                    service.orchestrator.serpapi,
                    "fetch_fiverr_marketplace_gigs",
                    return_value=([], ConnectorStatus("serpapi", "warning", "No SerpApi gigs found.")),
                ), patch.object(service, "_send_comparison_alert"):
                    state = service.compare_my_gig_to_market(
                        gig_url=my_gig.url,
                        search_terms=["anime logo"],
                    )

                comparison = state["gig_comparison"]
                self.assertEqual(comparison["competitor_count"], 0)
                self.assertEqual(comparison["detected_search_terms"], ["anime logo"])
                self.assertFalse(comparison["top_competitors"])
                self.assertFalse(comparison["top_search_titles"])
                self.assertIn("anime logo", comparison["message"].lower())

    def test_stale_cached_competitors_for_other_niche_are_ignored(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

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
                    "APP_AUTH_ENABLED": "false",
                },
                clear=False,
            ):
                service = DashboardService()
                service._cache_competitors(  # noqa: SLF001
                    ["anime logo"],
                    [
                        MarketplaceGig(
                            title="I will fix wordpress speed and core web vitals",
                            seller_name="Snapshot benchmark",
                            matched_term="anime logo",
                        )
                    ],
                )

                cached = service._load_cached_competitors(["anime logo"])  # noqa: SLF001
                self.assertFalse(cached)

    def test_manual_compare_for_logo_market_generates_logo_recommendations(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

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
                    "APP_AUTH_ENABLED": "false",
                },
                clear=False,
            ):
                service = DashboardService()
                with patch.object(service, "_send_comparison_alert"):
                    state = service.compare_manual_market_input(
                        gig_url="",
                        search_terms=["anime logo"],
                        competitor_input=(
                            "I will design anime logo for your brand | 35 | 4.9 | 230 | 2 days | https://www.fiverr.com/pixelkoi/design-anime-logo\n"
                            "I will create custom anime logo design | 55 | 5.0 | 410 | 3 days | https://www.fiverr.com/otakustudio/create-anime-logo-design"
                        ),
                    )

                comparison = state["gig_comparison"]
                blueprint = comparison["implementation_blueprint"]
                self.assertEqual(comparison["competitor_count"], 2)
                self.assertIn("anime logo", blueprint["recommended_title"].lower())
                self.assertNotIn("wordpress", blueprint["recommended_title"].lower())
                self.assertNotIn("wordpress", blueprint["description_full"].lower())


if __name__ == "__main__":
    unittest.main()
