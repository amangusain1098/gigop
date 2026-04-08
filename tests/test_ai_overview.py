from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from gigoptimizer.config import GigOptimizerConfig
from gigoptimizer.services.ai_overview_service import AIOverviewService
from gigoptimizer.services.settings_service import SettingsService


class AIOverviewFallbackTests(unittest.TestCase):
    def test_missing_api_key_uses_local_fallback_summary(self) -> None:
        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "AI_PROVIDER": "openai",
                    "AI_MODEL": "gpt-5.4-mini",
                    "AI_API_KEY": "",
                },
                clear=False,
            ):
                config = GigOptimizerConfig.from_env()
                settings = SettingsService(config)
                settings.update_settings({"ai": {"enabled": True, "provider": "openai", "model": "gpt-5.4-mini", "api_key": ""}})
                service = AIOverviewService(settings)
                overview = service.generate_overview(
                    report={
                        "optimization_score": 88,
                        "weekly_action_plan": ["Tighten the title around buyer-intent keywords."],
                        "competitive_gap_analysis": {
                            "why_competitors_win": ["Competitors use stronger keyword phrases in their titles."],
                            "what_to_implement": ["Add PageSpeed Insights to the first line."],
                        },
                        "conversion_audit": {
                            "actions": ["Improve response time and reposition the entry offer."],
                        },
                    }
                )

        self.assertEqual(overview["status"], "fallback")
        self.assertIn("optimization score is 88", overview["summary"].lower())
        self.assertTrue(overview["next_steps"])

    def test_local_chat_answers_from_market_context(self) -> None:
        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "AI_PROVIDER": "n8n",
                    "AI_API_KEY": "",
                },
                clear=False,
            ):
                config = GigOptimizerConfig.from_env()
                settings = SettingsService(config)
                settings.update_settings({"ai": {"enabled": True, "provider": "n8n", "api_base_url": ""}})
                service = AIOverviewService(settings)
                response = service.chat(
                    message="What title should I use?",
                    context={
                        "recommended_title": "I will optimize WordPress speed and improve PageSpeed Insights",
                        "recommended_tags": ["wordpress speed", "pagespeed insights"],
                        "why_competitors_win": ["Competitors use stronger keyword phrases in their titles."],
                        "what_to_implement": ["Add PageSpeed Insights to the first line."],
                    },
                )

        self.assertEqual(response["status"], "fallback")
        self.assertIn("strongest current title option", response["reply"].lower())
        self.assertTrue(response["suggestions"])


if __name__ == "__main__":
    unittest.main()
