from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    FASTAPI_AVAILABLE = True
except Exception:  # pragma: no cover
    FASTAPI_AVAILABLE = False

from gigoptimizer.assistant import AIAssistant, DeterministicLLMClient
from gigoptimizer.assistant.training import AssistantTrainer


FOUR_PART_CANNED = """Analysis:
- Current asset has room to grow on discoverability and proof.
- Top performers lead with the outcome.

Problems:
- Weak keyword density.
- Missing proof block.
- No clear CTA.

Optimized Version:
Title: I will optimize WordPress speed and Core Web Vitals for 90+ PageSpeed
Description: Hook -> problem -> deliverables -> proof -> CTA.
Tags: wordpress speed, core web vitals, pagespeed insights, gtmetrix, lcp fix
FAQ: Can you fix LCP? Do you support WooCommerce?
Packages: Basic, Standard, Premium

Action Steps:
1. Rewrite the title with the outcome metric.
2. Move deliverables to the top of the description.
3. Add a before/after proof block.
"""


def _build_client_and_app() -> tuple[TestClient, Path]:
    from gigoptimizer.assistant.api_routes import build_assistant_router

    class CannedClient:
        name = "canned"
        model = "canned-1"

        def complete(self, messages, *, temperature=0.4, max_tokens=1024):
            from gigoptimizer.assistant.client import LLMResponse

            return LLMResponse(
                text=FOUR_PART_CANNED,
                model=self.model,
                provider=self.name,
            )

    assistant = AIAssistant(client=CannedClient())
    tmp = tempfile.mkdtemp(prefix="gigopt_api_")
    trainer = AssistantTrainer(data_dir=tmp, repository=None)
    router = build_assistant_router(assistant=assistant, trainer=trainer)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app), Path(tmp)


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi not installed in this environment")
class AssistantRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client, self.tmp = _build_client_and_app()

    def test_status_endpoint_lists_features(self) -> None:
        response = self.client.get("/api/assistant/status")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["provider"], "canned")
        self.assertIn("ask", body["features"])
        self.assertTrue(body["has_trainer"])

    def test_ask_endpoint_requires_question(self) -> None:
        response = self.client.post("/api/assistant/ask", json={})
        self.assertEqual(response.status_code, 400)

    def test_ask_endpoint_returns_envelope(self) -> None:
        response = self.client.post(
            "/api/assistant/ask",
            json={"question": "How do I boost my CTR?"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["envelope"]["feature"], "ask")
        self.assertEqual(body["envelope"]["provider"], "canned")

    def test_optimize_gig_endpoint(self) -> None:
        response = self.client.post(
            "/api/assistant/optimize-gig",
            json={
                "current_gig": {
                    "title": "I will fix WordPress",
                    "description": "old desc",
                    "tags": ["wordpress"],
                },
                "competitor_gigs": [{"title": "I will fix core web vitals"}],
                "target_keywords": ["pagespeed"],
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["envelope"]["feature"], "optimize_gig")
        self.assertIn("optimized_title", body["result"])
        self.assertTrue(body["result"]["optimized_title"])

    def test_optimize_gig_rejects_non_object(self) -> None:
        response = self.client.post(
            "/api/assistant/optimize-gig",
            json={"current_gig": "not an object"},
        )
        self.assertEqual(response.status_code, 400)

    def test_audit_website_requires_url_or_copy(self) -> None:
        response = self.client.post("/api/assistant/audit-website", json={})
        self.assertEqual(response.status_code, 400)

    def test_audit_website_accepts_url(self) -> None:
        response = self.client.post(
            "/api/assistant/audit-website",
            json={"url": "https://example.com", "target_keywords": ["cls"]},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["envelope"]["feature"], "audit_website")
        self.assertIn("pagespeed", body)
        self.assertEqual(body["pagespeed"]["error"], "no_api_key")

    def test_generate_content_endpoint(self) -> None:
        canned_posts = (
            "Analysis:\n- ok\n"
            "Problems:\n- ok\n"
            "Optimized Version:\n"
            "Post 1: first hook\n\n"
            "Post 2: second hook\n\n"
            "Post 3: third hook\n"
            "Hashtags: wordpress\n"
            "Action Steps:\n1. post it\n"
        )

        class PostsClient:
            name = "posts"
            model = "posts-1"

            def complete(self, messages, *, temperature=0.4, max_tokens=1024):
                from gigoptimizer.assistant.client import LLMResponse

                return LLMResponse(text=canned_posts, model=self.model, provider=self.name)

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from gigoptimizer.assistant.api_routes import build_assistant_router

        assistant = AIAssistant(client=PostsClient())
        router = build_assistant_router(assistant=assistant, trainer=None)
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.post(
            "/api/assistant/generate-content",
            json={"topic": "WordPress speed", "platform": "twitter", "count": 3},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["result"]["platform"], "twitter")
        self.assertEqual(len(body["result"]["posts"]), 3)

    def test_generate_content_requires_topic(self) -> None:
        response = self.client.post("/api/assistant/generate-content", json={})
        self.assertEqual(response.status_code, 400)

    def test_improve_endpoint(self) -> None:
        response = self.client.post(
            "/api/assistant/improve",
            json={
                "original_output": "I help WordPress sites load faster.",
                "target_keywords": ["core web vitals"],
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["envelope"]["feature"], "improve_output")
        self.assertIn("improved_output", body["result"])

    def test_improve_rejects_empty(self) -> None:
        response = self.client.post("/api/assistant/improve", json={"original_output": ""})
        self.assertEqual(response.status_code, 400)

    def test_self_audit_endpoint(self) -> None:
        response = self.client.post(
            "/api/assistant/self-audit",
            json={"product_snapshot": {"name": "GigOptimizer AI"}},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["envelope"]["feature"], "self_audit")

    def test_train_endpoint_runs_pipeline(self) -> None:
        response = self.client.post("/api/assistant/train", json={})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("report", body)
        self.assertGreaterEqual(body["report"]["total_examples"], 3)
        self.assertTrue(body["report"]["modelfile_path"])
        self.assertTrue(Path(body["report"]["modelfile_path"]).exists())

    def test_train_endpoint_without_trainer_returns_503(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from gigoptimizer.assistant.api_routes import build_assistant_router

        assistant = AIAssistant(client=DeterministicLLMClient())
        router = build_assistant_router(assistant=assistant, trainer=None)
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)

        response = client.post("/api/assistant/train", json={})
        self.assertEqual(response.status_code, 503)


class AssistantRouterBuilderTests(unittest.TestCase):
    """Smoke tests that don't need fastapi to be importable."""

    def test_build_assistant_factory_returns_working_instance(self) -> None:
        from gigoptimizer.assistant.api_routes import build_assistant

        assistant = build_assistant(provider="deterministic")
        envelope = assistant.ask("hello")
        self.assertEqual(envelope.feature, "ask")
        self.assertEqual(envelope.provider, "deterministic")


if __name__ == "__main__":
    unittest.main()
