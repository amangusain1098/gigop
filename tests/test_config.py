from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from gigoptimizer.config import GigOptimizerConfig
from gigoptimizer.connectors.fiverr_scraper import FiverrSellerConnector


class ConfigValidationTests(unittest.TestCase):
    def test_validate_credentials_reports_missing_values_clearly(self) -> None:
        with patch.dict(
            os.environ,
            {
                "SEMRUSH_API_KEY": "",
                "FIVERR_ANALYTICS_URL": "",
                "FIVERR_EMAIL": "",
                "FIVERR_PASSWORD": "",
            },
            clear=False,
        ):
            config = GigOptimizerConfig.from_env()
            statuses = config.validate_credentials()

        status_map = {item.connector: item for item in statuses}
        self.assertEqual(status_map["semrush"].status, "skipped")
        self.assertIn("SEMRUSH_API_KEY not set", status_map["semrush"].detail)
        self.assertEqual(status_map["fiverr"].status, "skipped")
        self.assertIn("FIVERR_ANALYTICS_URL not set", status_map["fiverr"].detail)

    def test_validate_credentials_accepts_storage_state_for_fiverr(self) -> None:
        with TemporaryDirectory() as tmp:
            storage_state = Path(tmp) / "state.json"
            storage_state.write_text("{}", encoding="utf-8")
            with patch.dict(
                os.environ,
                {
                    "FIVERR_ANALYTICS_URL": "https://www.fiverr.com/users/me/gigs",
                    "FIVERR_STORAGE_STATE_PATH": str(storage_state),
                    "FIVERR_EMAIL": "",
                    "FIVERR_PASSWORD": "",
                },
                clear=False,
            ):
                config = GigOptimizerConfig.from_env()
                statuses = config.validate_credentials()

        status_map = {item.connector: item for item in statuses}
        self.assertEqual(status_map["fiverr"].status, "active")
        self.assertIn("saved storage state", status_map["fiverr"].detail)

    def test_fiverr_debug_selector_skips_without_analytics_url(self) -> None:
        connector = FiverrSellerConnector(GigOptimizerConfig())
        status = connector.debug_selectors()

        self.assertEqual(status.status, "skipped")
        self.assertIn("FIVERR_ANALYTICS_URL", status.detail)


if __name__ == "__main__":
    unittest.main()
