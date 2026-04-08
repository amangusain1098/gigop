from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient


class ExtensionImportTests(unittest.TestCase):
    def test_extension_import_route_processes_payload_and_reuses_cache(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
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
                    "EXTENSION_ENABLED": "true",
                    "EXTENSION_API_TOKEN": "this-is-a-long-extension-token",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    with patch.object(client.app.state.dashboard_service, "_send_comparison_alert"):
                        payload = {
                            "keyword": "react",
                            "gigs": [
                                {
                                    "title": "I will build full stack website with react js",
                                    "url": "https://www.fiverr.com/example/react-1",
                                    "seller_name": "React Seller",
                                    "starting_price": 60,
                                    "rating": 4.9,
                                    "reviews_count": 120,
                                    "rank_position": 1,
                                },
                                {
                                    "title": "I will create a react frontend dashboard",
                                    "url": "https://www.fiverr.com/example/react-2",
                                    "seller_name": "Frontend Pro",
                                    "starting_price": 90,
                                    "rating": 5.0,
                                    "reviews_count": 84,
                                    "rank_position": 2,
                                },
                            ],
                            "page_url": "https://www.fiverr.com/search/gigs?query=react",
                            "source": "browser_extension",
                        }

                        response = client.post(
                            "/api/extension/import",
                            json=payload,
                            headers={"Authorization": "Bearer this-is-a-long-extension-token"},
                        )
                        self.assertEqual(response.status_code, 200)
                        result = response.json()
                        self.assertEqual(result["status"], "ok")
                        self.assertEqual(result["gig_comparison"]["primary_search_term"], "react")
                        self.assertEqual(result["gig_comparison"]["competitor_count"], 2)

                        cached = client.post(
                            "/api/extension/import",
                            json=payload,
                            headers={"Authorization": "Bearer this-is-a-long-extension-token"},
                        )
                        self.assertEqual(cached.status_code, 200)
                        self.assertEqual(cached.json()["status"], "cached")

    def test_extension_import_requires_token(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
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
                    "EXTENSION_ENABLED": "true",
                    "EXTENSION_API_TOKEN": "this-is-a-long-extension-token",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    response = client.post(
                        "/api/extension/import",
                        json={"keyword": "react", "gigs": []},
                    )
                    self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
