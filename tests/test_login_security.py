from __future__ import annotations

import base64
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient


class LoginSecurityTests(unittest.TestCase):
    def test_failed_login_capture_is_recorded_reviewable_and_visible_in_bootstrap(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"
        png_payload = base64.b64encode(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aWQ0AAAAASUVORK5CYII="
            )
        ).decode("ascii")

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
                    "APP_AUTH_ENABLED": "true",
                    "APP_ADMIN_USERNAME": "admin",
                    "APP_ADMIN_PASSWORD": "super-secret-password",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "test-session-secret",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    for expected_count in (1, 2):
                        failed = client.post(
                            "/api/auth/login",
                            json={
                                "username": "admin",
                                "password": "wrong-password",
                                "client_id": "browser-a",
                            },
                            headers={"User-Agent": "GigOptimizerTestBrowser/1.0"},
                        )
                        self.assertEqual(failed.status_code, 401)
                        self.assertEqual(failed.json()["failed_attempts"], expected_count)
                        self.assertFalse(failed.json()["capture_required"])

                    failed = client.post(
                        "/api/auth/login",
                        json={
                            "username": "admin",
                            "password": "wrong-password",
                            "client_id": "browser-a",
                        },
                        headers={"User-Agent": "GigOptimizerTestBrowser/1.0"},
                    )
                    self.assertEqual(failed.status_code, 401)
                    self.assertEqual(failed.json()["failed_attempts"], 3)
                    self.assertTrue(failed.json()["capture_required"])
                    attempt_id = failed.json()["attempt_id"]

                    captured = client.post(
                        "/api/auth/login-attempts/capture",
                        json={
                            "attempt_id": attempt_id,
                            "client_id": "browser-a",
                            "content_type": "image/png",
                            "image_base64": png_payload,
                            "device_info": {
                                "platform": "Android",
                                "language": "en-IN",
                                "screen": "1080x2400",
                                "timezone": "Asia/Calcutta",
                                "touch_points": "5",
                            },
                        },
                        headers={"User-Agent": "GigOptimizerTestBrowser/1.0"},
                    )
                    self.assertEqual(captured.status_code, 200)
                    self.assertEqual(captured.json()["attempt"]["capture_status"], "pending_review")

                    login = client.post(
                        "/api/auth/login",
                        json={
                            "username": "admin",
                            "password": "super-secret-password",
                            "client_id": "browser-a",
                        },
                        headers={"User-Agent": "GigOptimizerTestBrowser/1.0"},
                    )
                    self.assertEqual(login.status_code, 200)
                    csrf_token = login.json()["auth"]["csrf_token"]
                    self.assertTrue(csrf_token)

                    bootstrap = client.get("/api/v2/bootstrap")
                    self.assertEqual(bootstrap.status_code, 200)
                    security = bootstrap.json()["security"]
                    self.assertEqual(security["capture_threshold"], 3)
                    self.assertTrue(security["failed_login_attempts"])
                    latest = security["failed_login_attempts"][0]
                    self.assertEqual(latest["id"], attempt_id)
                    self.assertEqual(latest["capture_status"], "pending_review")
                    self.assertTrue(latest["photo_url"])
                    self.assertIn("platform=Android", latest["user_agent"])

                    image = client.get(latest["photo_url"])
                    self.assertEqual(image.status_code, 200)
                    self.assertIn("image/", image.headers["content-type"])

                    saved = client.post(
                        f"/api/security/login-attempts/{attempt_id}/save",
                        headers={"X-CSRF-Token": csrf_token},
                    )
                    self.assertEqual(saved.status_code, 200)
                    self.assertEqual(saved.json()["attempt"]["capture_status"], "saved")

    def test_declined_consent_records_metadata_without_photo(self) -> None:
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
                    "APP_AUTH_ENABLED": "true",
                    "APP_ADMIN_USERNAME": "admin",
                    "APP_ADMIN_PASSWORD": "super-secret-password",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "test-session-secret",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    for _ in range(3):
                        failed = client.post(
                            "/api/auth/login",
                            json={
                                "username": "admin",
                                "password": "wrong-password",
                                "client_id": "browser-b",
                            },
                            headers={"User-Agent": "GigOptimizerTestBrowser/1.0"},
                        )
                    attempt_id = failed.json()["attempt_id"]

                    declined = client.post(
                        "/api/auth/login-attempts/capture",
                        json={
                            "attempt_id": attempt_id,
                            "client_id": "browser-b",
                            "capture_error": "consent_declined",
                            "device_info": {
                                "platform": "iPhone",
                                "language": "en-US",
                            },
                        },
                        headers={"User-Agent": "GigOptimizerTestBrowser/1.0"},
                    )
                    self.assertEqual(declined.status_code, 200)
                    attempt = declined.json()["attempt"]
                    self.assertEqual(attempt["capture_status"], "consent_declined")
                    self.assertFalse(attempt["photo_available"])


if __name__ == "__main__":
    unittest.main()
