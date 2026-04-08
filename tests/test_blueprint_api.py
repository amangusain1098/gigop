from __future__ import annotations

import os
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient


class BlueprintApiTests(unittest.TestCase):
    def test_blueprint_dashboard_and_bootstrap_work(self) -> None:
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
                    "DEFAULT_SNAPSHOT_PATH": str(example_snapshot),
                    "APP_AUTH_ENABLED": "false",
                    "APP_ADMIN_PASSWORD": "",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    terms = client.get("/terms-of-service")
                    self.assertEqual(terms.status_code, 200)
                    self.assertIn("Terms of service", terms.text)

                    dashboard = client.get("/dashboard")
                    self.assertEqual(dashboard.status_code, 200)
                    self.assertIn("GigOptimizer Pro Blueprint Dashboard", dashboard.text)

                    bootstrap = client.get("/api/v2/bootstrap")
                    self.assertEqual(bootstrap.status_code, 200)
                    payload = bootstrap.json()
                    self.assertIn("state", payload)
                    self.assertIn("job_runs", payload)
                    self.assertIn("health", payload)
                    self.assertIn("scraper_logs", payload)
                    self.assertIn("scraper_summary", payload)
                    self.assertIn("timeline", payload)
                    self.assertIn("comparison_diff", payload)
                    self.assertIn("extension_install", payload)

                    install_page = client.get("/extension/install")
                    self.assertEqual(install_page.status_code, 200)
                    self.assertIn("Install Fiverr Capture Extension", install_page.text)

                    extension_bundle = client.get("/downloads/fiverr-market-capture.zip")
                    self.assertEqual(extension_bundle.status_code, 200)
                    self.assertEqual(extension_bundle.headers.get("content-type"), "application/zip")

    def test_job_api_enqueues_and_completes_pipeline(self) -> None:
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
                    "DEFAULT_SNAPSHOT_PATH": str(example_snapshot),
                    "APP_AUTH_ENABLED": "false",
                    "APP_ADMIN_PASSWORD": "",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app
                from gigoptimizer.jobs.service import JobService

                with patch.object(JobService, "_start_local_thread", lambda self, run_id, runner: runner()):
                    with TestClient(create_app()) as client:
                        queued = client.post(
                            "/api/v2/jobs",
                            json={"job_type": "pipeline", "use_live_connectors": False},
                        )
                        self.assertEqual(queued.status_code, 200)
                        queued_job = queued.json()["queued_job"]
                        self.assertEqual(queued_job["run_type"], "pipeline")

                        status = queued_job
                        deadline = time.time() + 5
                        while status["status"] in {"queued", "running"} and time.time() < deadline:
                            time.sleep(0.1)
                            status = client.get(f"/api/v2/jobs/{queued_job['run_id']}").json()["job"]

                        self.assertEqual(status["status"], "completed")
                        self.assertTrue(status["result_payload"]["optimization_score"] >= 0)

    def test_history_endpoints_return_timeline_and_diff(self) -> None:
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
                    "APP_ADMIN_PASSWORD": "",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    service = client.app.state.dashboard_service
                    with patch.object(service, "_send_comparison_alert"):
                        service.compare_manual_market_input(
                            gig_url="",
                            competitor_input=(
                                "I will fix wordpress speed | 45 | 4.9 | 120 | 2 days | https://www.fiverr.com/example/1\n"
                                "I will improve core web vitals | 55 | 5.0 | 84 | 1 day | https://www.fiverr.com/example/2"
                            ),
                            search_terms=["wordpress speed"],
                        )
                        service.compare_manual_market_input(
                            gig_url="",
                            competitor_input=(
                                "I will fix wordpress speed and pagespeed insights | 35 | 4.8 | 180 | 1 day | https://www.fiverr.com/example/3\n"
                                "I will optimize wordpress lcp cls fcp | 65 | 5.0 | 64 | 2 days | https://www.fiverr.com/example/4"
                            ),
                            search_terms=["wordpress speed"],
                        )

                    timeline = client.get("/api/v2/history/timeline", params={"keyword": "wordpress speed"})
                    self.assertEqual(timeline.status_code, 200)
                    timeline_payload = timeline.json()["timeline"]
                    self.assertGreaterEqual(len(timeline_payload), 2)

                    diff = client.get("/api/v2/history/diff")
                    self.assertEqual(diff.status_code, 200)
                    diff_payload = diff.json()["diff"]
                    self.assertTrue(diff_payload["available"])
                    self.assertIn("changes", diff_payload)


if __name__ == "__main__":
    unittest.main()
