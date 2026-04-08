from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

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

    def test_local_chat_answers_generic_rank_question_from_live_context(self) -> None:
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
                    message="Why is the top gig ranking first on Fiverr right now?",
                    context={
                        "primary_search_term": "wordpress speed optimization",
                        "top_ranked_gig": {
                            "title": "I will do wordpress speed optimization for google pagespeed insight",
                            "why_on_page_one": [
                                "Fiverr is currently surfacing this gig first for the primary search term on page one.",
                                "The title matches the searched phrase directly.",
                            ],
                        },
                        "one_by_one_recommendations": [
                            {
                                "rank_position": 1,
                                "primary_recommendation": "Use the exact search phrase in your title and first line.",
                                "what_to_change": [
                                    "Use the exact search phrase in your title and first line.",
                                    "Add stronger proof and deliverables near the top.",
                                ],
                            }
                        ],
                    },
                )

        self.assertEqual(response["status"], "fallback")
        self.assertIn("ranking", response["reply"].lower())
        self.assertTrue(response["suggestions"])

    def test_local_chat_uses_current_number_one_for_compare_question(self) -> None:
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
                    message="Compare my gig with #1 and tell me exactly what to change first.",
                    context={
                        "top_ranked_gig": {
                            "title": "I will do wordpress speed optimization for google pagespeed insight",
                        },
                        "one_by_one_recommendations": [
                            {
                                "rank_position": 1,
                                "primary_recommendation": "Use the exact search phrase in your title and first line.",
                                "what_to_change": [
                                    "Use the exact search phrase in your title and first line.",
                                    "Add stronger proof and deliverables near the top.",
                                ],
                            },
                            {
                                "rank_position": 2,
                                "primary_recommendation": "Add more trust badges.",
                                "what_to_change": ["Add more trust badges."],
                            },
                        ],
                        "do_this_first": ["Use the exact search phrase in your title and first line."],
                    },
                )

        self.assertIn("#1 gig", response["reply"].lower())
        self.assertIn("wordpress speed optimization", response["reply"].lower())
        self.assertTrue(response["suggestions"])

    def test_local_chat_answers_from_uploaded_knowledge(self) -> None:
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
                    message="What does my uploaded dataset say about GTmetrix?",
                    context={
                        "knowledge_documents": [
                            {"filename": "notes.md", "preview": "Use GTmetrix and PageSpeed Insights in the hero copy."}
                        ],
                        "retrieved_knowledge": [
                            {
                                "filename": "notes.md",
                                "snippet": "Use GTmetrix and PageSpeed Insights in the hero copy.",
                            }
                        ],
                    },
                )

        self.assertIn("uploaded knowledge", response["reply"].lower())
        self.assertTrue(response["suggestions"])

    def test_local_chat_uses_uploaded_knowledge_for_title_rewrite_question(self) -> None:
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
                    message="Rewrite my title for better search demand.",
                    context={
                        "recommended_title": "I will optimize WordPress speed and improve PageSpeed Insights",
                        "retrieved_knowledge": [
                            {
                                "filename": "market-notes.txt",
                                "snippet": "Put PageSpeed Insights and GTmetrix in the first line because buyers search those exact tool names.",
                            }
                        ],
                    },
                )

        self.assertIn("strongest current title option", response["reply"].lower())
        self.assertIn("market-notes.txt", response["reply"])
        self.assertIn("pagespeed insights", response["reply"].lower())

    def test_n8n_overview_uses_webhook_response(self) -> None:
        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "AI_PROVIDER": "n8n",
                    "AI_MODEL": "webhook",
                    "AI_API_BASE_URL": "https://n8n.example/webhook/gigoptimizer-assistant",
                },
                clear=False,
            ):
                config = GigOptimizerConfig.from_env()
                settings = SettingsService(config)
                settings.update_settings(
                    {
                        "ai": {
                            "enabled": True,
                            "provider": "n8n",
                            "model": "webhook",
                            "api_base_url": "https://n8n.example/webhook/gigoptimizer-assistant",
                        }
                    }
                )
                service = AIOverviewService(settings)

                mock_response = MagicMock()
                mock_response.read.return_value = (
                    b'{"summary":"Watch the pricing gap first.","next_steps":["Lower the entry package.","Lead with WordPress speed.","Add proof."]}'
                )
                mock_response.__enter__.return_value = mock_response
                mock_response.__exit__.return_value = False

                with patch("gigoptimizer.services.ai_overview_service.urlopen", return_value=mock_response):
                    overview = service.generate_overview(
                        report={
                            "optimization_score": 91,
                            "weekly_action_plan": ["Refresh the title."],
                        }
                    )

        self.assertEqual(overview["status"], "ok")
        self.assertEqual(overview["provider"], "n8n")
        self.assertEqual(overview["summary"], "Watch the pricing gap first.")
        self.assertTrue(overview["next_steps"])

    def test_n8n_chat_falls_back_to_grounded_local_answer_when_reply_is_generic(self) -> None:
        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "AI_PROVIDER": "n8n",
                    "AI_MODEL": "webhook",
                    "AI_API_BASE_URL": "https://n8n.example/webhook/gigoptimizer-assistant",
                },
                clear=False,
            ):
                config = GigOptimizerConfig.from_env()
                settings = SettingsService(config)
                settings.update_settings(
                    {
                        "ai": {
                            "enabled": True,
                            "provider": "n8n",
                            "model": "webhook",
                            "api_base_url": "https://n8n.example/webhook/gigoptimizer-assistant",
                        }
                    }
                )
                service = AIOverviewService(settings)

                mock_response = MagicMock()
                mock_response.read.return_value = (
                    b'{"reply":"Competitors show more visible review volume than your current proof set, which can lift trust and click-through.","suggestions":[]}'
                )
                mock_response.__enter__.return_value = mock_response
                mock_response.__exit__.return_value = False

                with patch("gigoptimizer.services.ai_overview_service.urlopen", return_value=mock_response):
                    chat = service.chat(
                        message="Why is the top gig ranking first on Fiverr right now?",
                        context={
                            "primary_search_term": "wordpress speed optimization",
                            "top_ranked_gig": {
                                "title": "I will do wordpress speed optimization for google pagespeed insight",
                                "why_on_page_one": [
                                    "Fiverr is currently surfacing this gig first for the primary search term on page one."
                                ],
                            },
                            "one_by_one_recommendations": [
                                {
                                    "rank_position": 1,
                                    "primary_recommendation": "Use the exact search phrase in your title and first line.",
                                    "what_to_change": [
                                        "Use the exact search phrase in your title and first line."
                                    ],
                                }
                            ],
                        },
                    )

        self.assertEqual(chat["provider"], "n8n+grounded")
        self.assertIn("ranking", chat["reply"].lower())
        self.assertTrue(chat["suggestions"])

    def test_public_settings_marks_n8n_webhook_as_configured(self) -> None:
        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                },
                clear=False,
            ):
                config = GigOptimizerConfig.from_env()
                settings = SettingsService(config)
                settings.update_settings(
                    {
                        "ai": {
                            "enabled": True,
                            "provider": "n8n",
                            "model": "webhook",
                            "api_base_url": "https://n8n.example/webhook/gigoptimizer-assistant",
                        }
                    }
                )
                public_settings = settings.get_public_settings()

        self.assertTrue(public_settings["ai"]["configured"])
        self.assertEqual(public_settings["ai"]["provider"], "n8n")

    def test_local_chat_handles_greeting_with_live_context(self) -> None:
        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "AI_PROVIDER": "n8n",
                },
                clear=False,
            ):
                config = GigOptimizerConfig.from_env()
                settings = SettingsService(config)
                settings.update_settings({"ai": {"enabled": True, "provider": "n8n", "api_base_url": ""}})
                service = AIOverviewService(settings)
                response = service.chat(
                    message="hello",
                    context={
                        "copilot_learning": {
                            "latest_topics": ["mdn-blog-http-caching.txt", "cloudflare-blog-firewall-rules.txt"],
                        },
                        "recommended_title": "I will optimize WordPress speed",
                    },
                )

        self.assertEqual(response["status"], "fallback")
        self.assertIn("watching your live gig data", response["reply"].lower())
        self.assertTrue(response["suggestions"])

    def test_local_chat_handles_firewall_code_prompt(self) -> None:
        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "AI_PROVIDER": "n8n",
                },
                clear=False,
            ):
                config = GigOptimizerConfig.from_env()
                settings = SettingsService(config)
                settings.update_settings({"ai": {"enabled": True, "provider": "n8n", "api_base_url": ""}})
                service = AIOverviewService(settings)
                response = service.chat(
                    message="code this firewall for my VPS",
                    context={
                        "retrieved_knowledge": [
                            {"filename": "cloudflare-firewall.txt", "snippet": "Keep only SSH, HTTP, and HTTPS exposed."}
                        ]
                    },
                )

        self.assertEqual(response["status"], "fallback")
        self.assertIn("ufw", response["reply"].lower())
        self.assertIn("allow 443/tcp", response["reply"].lower())
        self.assertTrue(response["suggestions"])

    def test_n8n_configured_still_uses_grounded_local_for_greeting_and_firewall(self) -> None:
        with TemporaryDirectory() as tmp:
            temp_root = Path(tmp)
            with patch.dict(
                os.environ,
                {
                    "DATA_DIR": str(temp_root / "data"),
                    "INTEGRATION_SETTINGS_PATH": str(temp_root / "data" / "integrations.json"),
                    "AI_PROVIDER": "n8n",
                    "AI_MODEL": "webhook",
                    "AI_API_BASE_URL": "https://n8n.example/webhook/gigoptimizer-assistant",
                },
                clear=False,
            ):
                config = GigOptimizerConfig.from_env()
                settings = SettingsService(config)
                settings.update_settings(
                    {
                        "ai": {
                            "enabled": True,
                            "provider": "n8n",
                            "model": "webhook",
                            "api_base_url": "https://n8n.example/webhook/gigoptimizer-assistant",
                        }
                    }
                )
                service = AIOverviewService(settings)

                with patch("gigoptimizer.services.ai_overview_service.urlopen") as mocked_urlopen:
                    greeting = service.chat(
                        message="hello there",
                        context={"copilot_learning": {"latest_topics": ["mdn-blog-http-caching.txt"]}},
                    )
                    firewall = service.chat(
                        message="write a firewall script for my ubuntu fastapi server",
                        context={},
                    )

        mocked_urlopen.assert_not_called()
        self.assertEqual(greeting["status"], "fallback")
        self.assertIn("watching your live gig data", greeting["reply"].lower())
        self.assertEqual(firewall["status"], "fallback")
        self.assertIn("ufw", firewall["reply"].lower())


if __name__ == "__main__":
    unittest.main()
