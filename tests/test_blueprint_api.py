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


if __name__ == "__main__":
    unittest.main()
