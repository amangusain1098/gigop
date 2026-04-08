from __future__ import annotations

import unittest
import gc
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from gigoptimizer.config import GigOptimizerConfig
from gigoptimizer.queue import HITLQueue
from gigoptimizer.services.dashboard_service import DashboardService
from gigoptimizer.validators import HallucinationValidator


class Step2FoundationTests(unittest.TestCase):
    def test_validator_flags_unknown_numbers_and_absolute_claims(self) -> None:
        validator = HallucinationValidator()
        result = validator.validate(
            "Your CTR is 45% and I guarantee a 100% win.",
            allowed_numbers=[12, 8],
        )

        self.assertFalse(result.valid)
        self.assertTrue(any(issue.code == "number_mismatch" for issue in result.issues))
        self.assertTrue(any(issue.code == "absolute_claim" for issue in result.issues))
        self.assertNotIn("guarantee", result.sanitized_output.lower())

    def test_validator_accepts_known_numbers(self) -> None:
        validator = HallucinationValidator()
        result = validator.validate(
            "Your CTR is 12% and conversion is 8%.",
            allowed_numbers=[12, 8],
        )

        self.assertTrue(result.valid)
        self.assertEqual(result.confidence, 100)

    def test_hitl_queue_can_enqueue_and_update_records(self) -> None:
        with TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "approval_queue.db"
            queue = HITLQueue(db_path)
            record = queue.enqueue(
                agent_name="content_optimizer",
                action_type="title_update",
                current_value="I will speed up your WordPress website",
                proposed_value="I will fix WordPress page speed and Core Web Vitals",
                confidence_score=88,
                status="auto_approved",
            )

            records = queue.list_records()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].id, record.id)
            self.assertEqual(records[0].status, "auto_approved")

            queue.update_status(record.id, status="approved", reviewer_notes="Looks good.")
            updated = queue.list_records()[0]
            self.assertEqual(updated.status, "approved")
            self.assertEqual(updated.reviewer_notes, "Looks good.")
            del queue
            gc.collect()

    def test_clean_high_confidence_title_update_can_auto_approve(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(__file__).resolve().parent.parent
            config = GigOptimizerConfig(
                data_dir=Path(tmp) / "data",
                reports_dir=Path(tmp) / "reports",
                default_snapshot_path=root / "examples" / "wordpress_speed_snapshot.json",
                dashboard_state_path=Path(tmp) / "data" / "dashboard_state.json",
                metrics_history_path=Path(tmp) / "data" / "metrics_history.json",
                agent_health_path=Path(tmp) / "data" / "agent_health.json",
                integration_settings_path=Path(tmp) / "data" / "integrations.json",
                approval_queue_db_path=Path(tmp) / "data" / "approval_queue.db",
            )
            service = DashboardService(config=config)
            validation = SimpleNamespace(confidence=100, issues=[])

            status = service._status_for_validation(validation, action_type="title_update")  # noqa: SLF001

            self.assertEqual(status, "auto_approved")


if __name__ == "__main__":
    unittest.main()
