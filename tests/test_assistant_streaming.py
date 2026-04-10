from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient


class AssistantStreamingTests(unittest.TestCase):
    def test_chat_returns_session_id_and_writes_conversation_memory(self) -> None:
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
                    login = client.post(
                        "/api/auth/login",
                        json={"username": "admin", "password": "super-secret-password"},
                    )
                    csrf_token = login.json()["auth"]["csrf_token"]
                    with patch.object(client.app.state.ai_assistant, "ask", side_effect=RuntimeError("force legacy")):
                        with patch.object(
                            client.app.state.ai_overview_service,
                            "chat",
                            return_value={"status": "ok", "reply": "Use a clearer keyword promise.", "suggestions": []},
                        ):
                            response = client.post(
                                "/api/assistant/chat",
                                json={"message": "Rewrite my title", "session_id": "session-abc"},
                                headers={"X-CSRF-Token": csrf_token},
                            )

                    self.assertEqual(response.status_code, 200)
                    body = response.json()
                    self.assertEqual(body["session_id"], "session-abc")
                    memory_path = temp_root / "data" / "conversations" / "session-abc.jsonl"
                    self.assertTrue(memory_path.exists())
                    content = memory_path.read_text(encoding="utf-8")
                    self.assertIn("Rewrite my title", content)
                    self.assertIn("Use a clearer keyword promise.", content)

    def test_stream_endpoint_returns_sse_chunks(self) -> None:
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
                    login = client.post(
                        "/api/auth/login",
                        json={"username": "admin", "password": "super-secret-password"},
                    )
                    csrf_token = login.json()["auth"]["csrf_token"]
                    with patch.object(client.app.state.ai_assistant, "ask", side_effect=RuntimeError("force legacy")):
                        with patch.object(
                            client.app.state.ai_overview_service,
                            "chat",
                            return_value={"status": "ok", "reply": "Streaming answer from the assistant.", "suggestions": []},
                        ):
                            with client.stream(
                                "POST",
                                "/api/assistant/stream",
                                json={"message": "hello", "session_id": "stream-abc"},
                                headers={"X-CSRF-Token": csrf_token},
                            ) as response:
                                payload = "".join(response.iter_text())

                    self.assertEqual(response.status_code, 200)
                    self.assertIn("data:", payload)
                    self.assertIn("[DONE]", payload)
                    self.assertIn("Streamin", payload)

    def test_n8n_knowledge_refresh_saves_file(self) -> None:
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
                    "N8N_WEBHOOK_SECRET": "change_me",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app

                with TestClient(create_app()) as client:
                    response = client.post(
                        "/api/webhooks/n8n",
                        json={
                            "event": "knowledge_refresh",
                            "payload": {
                                "title": "Fiverr SEO Playbook",
                                "content": "# Notes\nUse proof and keyword intent.",
                            },
                            "secret": "change_me",
                        },
                    )

                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.json(), {"status": "ok", "event": "knowledge_refresh"})
                    knowledge_files = list((temp_root / "data" / "knowledge").glob("*.md"))
                    self.assertEqual(len(knowledge_files), 1)
                    self.assertIn("Use proof and keyword intent.", knowledge_files[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
