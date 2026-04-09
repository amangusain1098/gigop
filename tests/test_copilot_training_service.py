from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

from gigoptimizer.config import GigOptimizerConfig
from gigoptimizer.persistence import BlueprintRepository, DatabaseManager
from gigoptimizer.services.copilot_training_service import CopilotTrainingService


class CopilotTrainingServiceTests(unittest.TestCase):
    def test_export_training_bundle_creates_clean_holdout_and_feedback_summary(self) -> None:
        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "UPLOADS_DIR": str(temp_root / "data" / "uploads"),
                    "REPORTS_DIR": str(temp_root / "reports"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "DATABASE_URL": f"sqlite:///{(temp_root / 'data' / 'training.db').as_posix()}",
                },
                clear=False,
            ):
                config = GigOptimizerConfig.from_env()
                repository = BlueprintRepository(DatabaseManager(config))
                service = CopilotTrainingService(config, repository)
                gig_url = "https://www.fiverr.com/example/react-firewall"
                repository.record_assistant_message(
                    gig_id=gig_url,
                    role="user",
                    content="Write a firewall setup for my FastAPI VPS and send it to owner@example.com",
                    source="dashboard_chat",
                    metadata={"topic_tags": ["security"]},
                )
                assistant = repository.record_assistant_message(
                    gig_id=gig_url,
                    role="assistant",
                    content="Use UFW, allow OpenSSH, 80, and 443 only. Then email the checklist to owner@example.com.",
                    source="local",
                    metadata={"topic_tags": ["security", "python"]},
                )
                service.record_feedback(message_id=int(assistant["id"]), rating=1, note="Very useful firewall answer")
                status = service.export_training_bundle(gig_id=gig_url, force=True)
                latest_files = status["latest_files"]
                holdout_path = Path(str(latest_files["holdout_path"]))
                self.assertTrue(holdout_path.exists())
                payload = holdout_path.read_text(encoding="utf-8")
                self.assertIn("[redacted-email]", payload)

        self.assertEqual(status["feedback"]["positive"], 1)
        self.assertEqual(status["holdout_examples"], 1)
        self.assertEqual(status["train_examples"], 0)
        self.assertIn("security", status["recent_topics"])


class CopilotTrainingApiTests(unittest.TestCase):
    def test_feedback_and_export_routes_work(self) -> None:
        root = Path(__file__).resolve().parent.parent
        example_snapshot = root / "examples" / "wordpress_speed_snapshot.json"

        with TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "UPLOADS_DIR": str(temp_root / "data" / "uploads"),
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
                    "COPILOT_LEARNING_ENABLED": "false",
                    "COPILOT_TRAINING_ENABLED": "true",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    login = client.post(
                        "/api/auth/login",
                        json={"username": "admin", "password": "super-secret-password"},
                    )
                    csrf_token = login.json()["auth"]["csrf_token"]

                    with patch.object(
                        client.app.state.ai_overview_service,
                        "chat",
                        return_value={
                            "status": "ok",
                            "provider": "local",
                            "model": "test",
                            "reply": "Use a stronger React title and tighten the package scope.",
                            "suggestions": ["Rewrite the title."],
                        },
                    ):
                        assistant = client.post(
                            "/api/assistant/chat",
                            json={"message": "How should I improve my React gig?"},
                            headers={"X-CSRF-Token": csrf_token},
                        )

                    self.assertEqual(assistant.status_code, 200)
                    history = assistant.json()["assistant_history"]
                    assistant_message = [item for item in history if item["role"] == "assistant"][-1]

                    feedback = client.post(
                        "/api/assistant/feedback",
                        json={"message_id": assistant_message["id"], "rating": 1},
                        headers={"X-CSRF-Token": csrf_token},
                    )
                    self.assertEqual(feedback.status_code, 200)
                    self.assertEqual(feedback.json()["copilot_training"]["feedback"]["positive"], 1)

                    export = client.post(
                        "/api/copilot/training/export",
                        headers={"X-CSRF-Token": csrf_token},
                    )
                    self.assertEqual(export.status_code, 200)
                    training = export.json()["copilot_training"]
                    self.assertGreaterEqual(training["train_examples"] + training["holdout_examples"], 1)


if __name__ == "__main__":
    unittest.main()
