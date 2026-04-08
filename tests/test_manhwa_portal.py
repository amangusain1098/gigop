from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Sample Feed</title>
    <item>
      <title>New Manhwa Chapter Drops</title>
      <link>https://example.com/manhwa/chapter-1</link>
      <guid>https://example.com/manhwa/chapter-1</guid>
      <description><![CDATA[<p>Latest manhwa chapter with a readable summary.</p>]]></description>
      <content:encoded><![CDATA[<p>Full update text for the latest manhwa chapter.</p>]]></content:encoded>
      <category>Manhwa</category>
      <pubDate>Wed, 08 Apr 2026 10:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
"""


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return


class ManhwaPortalTests(unittest.TestCase):
    def test_public_manhwa_pages_render_from_feed_sync(self) -> None:
        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "REPORTS_DIR": str(temp_root / "reports"),
                    "UPLOADS_DIR": str(temp_root / "data" / "uploads"),
                    "DASHBOARD_STATE_PATH": str(temp_root / "data" / "dashboard_state.json"),
                    "METRICS_HISTORY_PATH": str(temp_root / "data" / "metrics_history.json"),
                    "AGENT_HEALTH_PATH": str(temp_root / "data" / "agent_health.json"),
                    "APPROVAL_QUEUE_DB_PATH": str(temp_root / "data" / "approval_queue.db"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "APP_AUTH_ENABLED": "false",
                    "APP_SESSION_SECRET": "",
                    "DEFAULT_SNAPSHOT_PATH": str(Path(__file__).resolve().parent.parent / "examples" / "wordpress_speed_snapshot.json"),
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with patch("gigoptimizer.services.manhwa_service.httpx.get", return_value=_FakeResponse(SAMPLE_RSS)):
                    with TestClient(create_app()) as client:
                        home = client.get("/manhwa")
                        self.assertEqual(home.status_code, 200)
                        self.assertIn("Automated manhwa, manga, and comics tracking", home.text)
                        self.assertIn("New Manhwa Chapter Drops", home.text)
                        self.assertNotIn("/dashboard", home.text)
                        self.assertNotIn("/studio/manhwa", home.text)

                        overview = client.get("/api/manhwa/overview")
                        self.assertEqual(overview.status_code, 200)
                        payload = overview.json()["overview"]
                        self.assertGreaterEqual(payload["counts"]["all"], 1)

                        entry = payload["latest_entries"][0]
                        reader = client.get(f"/manhwa/read/{entry['slug']}")
                        self.assertEqual(reader.status_code, 200)
                        self.assertIn("Full update text", reader.text)

                        feed_xml = client.get("/manhwa/feed.xml")
                        self.assertEqual(feed_xml.status_code, 200)
                        self.assertIn("New Manhwa Chapter Drops", feed_xml.text)

                        sitemap = client.get("/manhwa/sitemap.xml")
                        self.assertEqual(sitemap.status_code, 200)
                        self.assertIn("/manhwa/read/", sitemap.text)

    def test_hidden_public_dashboard_path_returns_not_found_when_logged_out(self) -> None:
        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "REPORTS_DIR": str(temp_root / "reports"),
                    "UPLOADS_DIR": str(temp_root / "data" / "uploads"),
                    "DASHBOARD_STATE_PATH": str(temp_root / "data" / "dashboard_state.json"),
                    "METRICS_HISTORY_PATH": str(temp_root / "data" / "metrics_history.json"),
                    "AGENT_HEALTH_PATH": str(temp_root / "data" / "agent_health.json"),
                    "APPROVAL_QUEUE_DB_PATH": str(temp_root / "data" / "approval_queue.db"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "APP_AUTH_ENABLED": "true",
                    "APP_ADMIN_USERNAME": "admin",
                    "APP_ADMIN_PASSWORD": "super-secret-password",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "test-secret",
                    "DEFAULT_SNAPSHOT_PATH": str(Path(__file__).resolve().parent.parent / "examples" / "wordpress_speed_snapshot.json"),
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with patch("gigoptimizer.services.manhwa_service.httpx.get", return_value=_FakeResponse(SAMPLE_RSS)):
                    with TestClient(create_app()) as client:
                        hidden = client.get("/manhwa/dashboard")
                        self.assertEqual(hidden.status_code, 404)

    def test_manhwa_studio_sync_and_source_management_require_auth_and_run(self) -> None:
        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "REPORTS_DIR": str(temp_root / "reports"),
                    "UPLOADS_DIR": str(temp_root / "data" / "uploads"),
                    "DASHBOARD_STATE_PATH": str(temp_root / "data" / "dashboard_state.json"),
                    "METRICS_HISTORY_PATH": str(temp_root / "data" / "metrics_history.json"),
                    "AGENT_HEALTH_PATH": str(temp_root / "data" / "agent_health.json"),
                    "APPROVAL_QUEUE_DB_PATH": str(temp_root / "data" / "approval_queue.db"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "APP_AUTH_ENABLED": "true",
                    "APP_ADMIN_USERNAME": "admin",
                    "APP_ADMIN_PASSWORD": "super-secret-password",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "test-secret",
                    "DEFAULT_SNAPSHOT_PATH": str(Path(__file__).resolve().parent.parent / "examples" / "wordpress_speed_snapshot.json"),
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with patch("gigoptimizer.services.manhwa_service.httpx.get", return_value=_FakeResponse(SAMPLE_RSS)):
                    with TestClient(create_app()) as client:
                        login = client.post(
                            "/api/auth/login",
                            json={"username": "admin", "password": "super-secret-password"},
                        )
                        self.assertEqual(login.status_code, 200)
                        csrf_token = login.json()["auth"]["csrf_token"]

                        dashboard = client.get("/studio/manhwa")
                        self.assertEqual(dashboard.status_code, 200)
                        self.assertIn("Private feed ingestion and publishing control", dashboard.text)

                        sync = client.post(
                            "/api/manhwa/sync",
                            json={"force": True},
                            headers={"X-CSRF-Token": csrf_token},
                        )
                        self.assertEqual(sync.status_code, 200)
                        self.assertGreaterEqual(sync.json()["result"]["total_entries"], 1)

                        source = client.post(
                            "/api/manhwa/sources",
                            json={
                                "title": "Custom Feed",
                                "feed_url": "https://example.com/feed.xml",
                                "site_url": "https://example.com",
                                "category": "manhwa",
                                "kind": "blog",
                                "focus": "updates, recommendations",
                            },
                            headers={"X-CSRF-Token": csrf_token},
                        )
                        self.assertEqual(source.status_code, 200)
                        saved_source = source.json()["source"]
                        self.assertEqual(saved_source["title"], "Custom Feed")

                        toggled = client.post(
                            f"/api/manhwa/sources/{saved_source['slug']}/toggle",
                            json={"active": False},
                            headers={"X-CSRF-Token": csrf_token},
                        )
                        self.assertEqual(toggled.status_code, 200)
                        self.assertFalse(toggled.json()["source"]["active"])


if __name__ == "__main__":
    unittest.main()
