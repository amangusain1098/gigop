from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient


class VerificationTests(unittest.TestCase):
    def test_verify_reports_success_for_local_instance(self) -> None:
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
                    "APP_ADMIN_PASSWORD": "",
                    "APP_ADMIN_PASSWORD_HASH": "",
                    "APP_SESSION_SECRET": "",
                },
                clear=False,
            ):
                from gigoptimizer.api.main import create_app
                from gigoptimizer.verify import verify

                app = create_app()
                with TestClient(app) as client:
                    output_path = temp_root / "artifacts" / "verification.json"
                    exit_code = verify(
                        base_url="http://testserver",
                        username=None,
                        password=None,
                        output_path=output_path,
                        client=client,
                    )

                self.assertEqual(exit_code, 0)
                self.assertTrue(output_path.exists())
                payload = output_path.read_text(encoding="utf-8")
                self.assertIn('"ok": true', payload)


if __name__ == "__main__":
    unittest.main()
