from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from gigoptimizer.config import GigOptimizerConfig
from gigoptimizer.models import ConnectorStatus
from gigoptimizer.services.dashboard_service import DashboardService
from gigoptimizer.services.settings_service import SettingsService
from gigoptimizer.utils import build_gig_key


class GigIdentityTests(unittest.TestCase):
    def test_build_gig_key_is_stable_for_fiverr_tracking_urls(self) -> None:
        base = (
            "https://www.fiverr.com/tezpage/optimize-wordpress-for-90-plus-google-pagespeed-score"
        )
        tracked = (
            f"{base}?context_referrer=tailored_homepage_perseus&source=recently_viewed_gigs"
            "&ref_ctx_id=6d968e881ea7478280d06eacc4f3cca7&context=recommendation"
            "&pckg_id=1&pos=1&context_alg=recently_viewed&seller_online=true"
            "&imp_id=c2377e3f-8db8-4fcd-9d5d-07b235cd2f77"
        )

        plain_key = build_gig_key(base)
        tracked_key = build_gig_key(tracked)

        self.assertEqual(plain_key, tracked_key)
        self.assertLessEqual(len(tracked_key), 255)
        self.assertTrue(tracked_key.startswith("fiverr:tezpage:"))

    def test_manual_compare_with_long_gig_url_records_history(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"
        tracked_url = (
            "https://www.fiverr.com/tezpage/optimize-wordpress-for-90-plus-google-pagespeed-score"
            "?context_referrer=tailored_homepage_perseus&source=recently_viewed_gigs"
            "&ref_ctx_id=6d968e881ea7478280d06eacc4f3cca7&context=recommendation"
            "&pckg_id=1&pos=1&context_alg=recently_viewed&seller_online=true"
            "&imp_id=c2377e3f-8db8-4fcd-9d5d-07b235cd2f77"
        )

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
                service = DashboardService(config=config, settings_service=settings)
                snapshot = service._load_snapshot()  # noqa: SLF001
                my_gig = service._snapshot_gig_overview(snapshot, tracked_url)  # noqa: SLF001

                with patch.object(
                    service.orchestrator.marketplace,
                    "fetch_gig_page_overview",
                    return_value=(
                        my_gig,
                        ConnectorStatus("fiverr_marketplace", "ok", "Loaded tracked Fiverr gig."),
                    ),
                ):
                    state = service.compare_manual_market_input(
                        gig_url=tracked_url,
                        competitor_input=(
                            "I will fix wordpress speed | 45 | 4.9 | 120 | 2 days | https://www.fiverr.com/example/1\n"
                            "I will improve core web vitals | 55 | 5.0 | 80 | 1 day | https://www.fiverr.com/example/2"
                        ),
                        search_terms=["wordpress speed optimization"],
                    )

                normalized_key = build_gig_key(tracked_url)
                history = service.repository.list_comparison_history(gig_id=tracked_url, limit=5)

        self.assertEqual(state["gig_comparison"]["gig_id"], normalized_key)
        self.assertTrue(history)
        self.assertEqual(history[0]["gig_id"], normalized_key)
        self.assertLessEqual(len(history[0]["gig_id"]), 255)


if __name__ == "__main__":
    unittest.main()
