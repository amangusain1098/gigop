from __future__ import annotations

# Assistant module test suite.
import json
import unittest

from gigoptimizer.assistant import (
    AIAssistant,
    DeterministicLLMClient,
    LLMClient,
    LLMMessage,
    LLMResponse,
    ScoringRubric,
    build_default_client,
    render_prompt,
)
from gigoptimizer.assistant.prompts import (
    ALL_PROMPTS,
    CONTENT_REFINER_PROMPT,
    FIVERR_SEO_EXPERT_PROMPT,
    GIG_OPTIMIZER_SYSTEM_PROMPT,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------
class FakeClient:
    """LLMClient test double that returns a canned response and records the
    call so tests can assert prompts were threaded through correctly."""

    name = "fake"

    def __init__(self, canned_text: str, model: str = "fake-model-1") -> None:
        self.canned_text = canned_text
        self.model = model
        self.calls: list[dict] = []

    def complete(self, messages, *, temperature=0.4, max_tokens=1024):  # type: ignore[override]
        self.calls.append(
            {
                "messages": [(m.role, m.content) for m in messages],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return LLMResponse(
            text=self.canned_text,
            model=self.model,
            provider=self.name,
            prompt_tokens=10,
            completion_tokens=20,
            latency_ms=42,
        )


FOUR_PART_CANNED = """Analysis:
- Seller is missing Core Web Vitals language in the first 120 chars of the title.
- Top performers lead with the outcome and name PageSpeed Insights directly.

Problems:
- Title has no power word or outcome metric.
- Description buries deliverables after the about-me block.
- Tags miss two high-intent long tail terms.
- No proof block (before/after PageSpeed scores).

Optimized Version:
Title: I will optimize WordPress speed and Core Web Vitals for a 90+ PageSpeed score
Description: Hook -> problem -> deliverables -> proof -> CTA. I will audit your site, fix LCP and CLS, and deliver a before-and-after report. Message me today to order now.
Tags: wordpress speed, core web vitals, pagespeed insights, gtmetrix, lcp fix
FAQ: Can you fix both LCP and CLS? Do you work on WooCommerce? Will you deliver a report?
Packages: Basic Audit, Standard Fix, Premium Scale

Action Steps:
1. Rewrite the title with the outcome metric and PageSpeed keyword.
2. Move deliverables to the top of the description.
3. Add a before/after PageSpeed proof block with screenshots.
4. Replace weak tags with 5 long-tail intent terms.
5. Add Basic/Standard/Premium packages with a 24h delivery flag.
"""


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------
class PromptTemplateTests(unittest.TestCase):
    def test_all_prompts_registered(self) -> None:
        for key in ("system", "architect", "refiner", "fiverr_seo", "chain_of_thought", "self_audit"):
            self.assertIn(key, ALL_PROMPTS)
            self.assertTrue(ALL_PROMPTS[key].strip())

    def test_render_prompt_rejects_missing_key(self) -> None:
        with self.assertRaises(KeyError):
            render_prompt(FIVERR_SEO_EXPERT_PROMPT, current_gig="x")  # missing competitor_gigs

    def test_render_prompt_rejects_unused_key(self) -> None:
        with self.assertRaises(KeyError):
            render_prompt(
                CONTENT_REFINER_PROMPT,
                target_keywords="x",
                audience="y",
                original_output="z",
                extra="should not be here",
            )

    def test_render_prompt_happy_path(self) -> None:
        rendered = render_prompt(
            CONTENT_REFINER_PROMPT,
            target_keywords="wordpress speed, core web vitals",
            audience="freelancers",
            original_output="This is the old output.",
        )
        self.assertIn("wordpress speed, core web vitals", rendered)
        self.assertIn("This is the old output.", rendered)

    def test_system_prompt_contains_product_name_and_rules(self) -> None:
        self.assertIn("GigOptimizer AI", GIG_OPTIMIZER_SYSTEM_PROMPT)
        self.assertIn("Action Steps", GIG_OPTIMIZER_SYSTEM_PROMPT)


# ---------------------------------------------------------------------------
# Scoring rubric
# ---------------------------------------------------------------------------
class ScoringRubricTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rubric = ScoringRubric()

    def test_complete_gig_scores_high(self) -> None:
        breakdown = self.rubric.score_gig(
            title="I will optimize WordPress speed and Core Web Vitals for 90+ PageSpeed",
            description=(
                "I will audit your site and deliver a before/after PageSpeed and GTmetrix report. "
                "You get Core Web Vitals fixes (LCP, CLS), image optimization, caching, unlimited "
                "revisions, and a conversion review. Message me today to order now with a "
                "24 hours turnaround."
                * 2
            ),
            tags=["wordpress speed", "core web vitals", "pagespeed", "gtmetrix", "lcp fix"],
            has_faq=True,
            has_packages=True,
            has_proof_block=True,
            target_keywords=["wordpress speed"],
        )
        self.assertGreaterEqual(breakdown.total, 80)
        self.assertEqual(breakdown.tag_score, 15)
        self.assertEqual(breakdown.conversion_score, 20)

    def test_empty_gig_scores_low(self) -> None:
        breakdown = self.rubric.score_gig(
            title="",
            description="",
            tags=[],
            has_faq=False,
            has_packages=False,
            has_proof_block=False,
        )
        self.assertLessEqual(breakdown.total, 10)
        self.assertTrue(breakdown.notes)

    def test_score_text_rewards_structure(self) -> None:
        low = self.rubric.score_text("short blurb")
        high = self.rubric.score_text(FOUR_PART_CANNED, target_keywords=["core web vitals"])
        self.assertGreater(high, low)
        self.assertGreaterEqual(high, 60)


# ---------------------------------------------------------------------------
# Deterministic / fallback client
# ---------------------------------------------------------------------------
class DeterministicClientTests(unittest.TestCase):
    def test_returns_four_part_structure(self) -> None:
        client = DeterministicLLMClient()
        response = client.complete([LLMMessage(role="user", content="optimize my gig")])
        self.assertIsInstance(response, LLMResponse)
        lowered = response.text.lower()
        for section in ("analysis", "problems", "optimized version", "action steps"):
            self.assertIn(section, lowered)

    def test_build_default_client_with_unknown_provider_returns_deterministic(self) -> None:
        client = build_default_client(provider="nope", env={})
        self.assertIsInstance(client, DeterministicLLMClient)

    def test_build_default_client_is_llmclient(self) -> None:
        client = build_default_client(provider="deterministic", env={})
        self.assertIsInstance(client, LLMClient)


# ---------------------------------------------------------------------------
# Assistant end-to-end
# ---------------------------------------------------------------------------
class AIAssistantTests(unittest.TestCase):
    def test_ask_uses_system_prompt(self) -> None:
        fake = FakeClient(FOUR_PART_CANNED)
        assistant = AIAssistant(client=fake)
        envelope = assistant.ask("How do I improve my Fiverr gig CTR?")
        self.assertEqual(envelope.feature, "ask")
        self.assertEqual(envelope.provider, "fake")
        self.assertFalse(envelope.fallback_used)
        self.assertIsNotNone(envelope.score)
        # First message should be the system prompt.
        system_role, system_content = fake.calls[0]["messages"][0]
        self.assertEqual(system_role, "system")
        self.assertIn("GigOptimizer AI", system_content)

    def test_ask_with_context_uses_chain_of_thought(self) -> None:
        fake = FakeClient(FOUR_PART_CANNED)
        assistant = AIAssistant(client=fake)
        assistant.ask("Why is my CTR low?", context="impressions=1000 clicks=12")
        user_role, user_content = fake.calls[0]["messages"][-1]
        self.assertEqual(user_role, "user")
        self.assertIn("step-by-step", user_content.lower())
        self.assertIn("impressions=1000 clicks=12", user_content)

    def test_ask_rejects_empty_question(self) -> None:
        assistant = AIAssistant(client=FakeClient(""))
        with self.assertRaises(ValueError):
            assistant.ask("   ")

    def test_optimize_gig_parses_all_fields(self) -> None:
        fake = FakeClient(FOUR_PART_CANNED)
        assistant = AIAssistant(client=fake)
        envelope, result = assistant.optimize_gig(
            current_gig={
                "title": "I will optimize your WordPress site",
                "description": "old desc",
                "tags": ["wordpress", "seo"],
            },
            competitor_gigs=[{"title": "I will fix core web vitals"}],
            target_keywords=["wordpress speed"],
        )
        self.assertEqual(envelope.feature, "optimize_gig")
        self.assertTrue(result.optimized_title)
        self.assertIn("PageSpeed", result.optimized_title)
        self.assertEqual(len(result.optimized_tags), 5)
        self.assertEqual(len(result.package_names), 3)
        self.assertGreaterEqual(result.score, 50)
        self.assertIn("score_breakdown", envelope.structured)
        # The competitor blob should have been threaded into the prompt.
        user_prompt = fake.calls[0]["messages"][-1][1]
        self.assertIn("core web vitals", user_prompt)

    def test_audit_website_requires_url_or_copy(self) -> None:
        assistant = AIAssistant(client=FakeClient(FOUR_PART_CANNED))
        with self.assertRaises(ValueError):
            assistant.audit_website()

    def test_audit_website_returns_structured_result(self) -> None:
        fake = FakeClient(FOUR_PART_CANNED)
        assistant = AIAssistant(client=fake)
        envelope, result = assistant.audit_website(
            url="https://example.com",
            target_keywords=["core web vitals", "pagespeed"],
        )
        self.assertEqual(envelope.feature, "audit_website")
        self.assertTrue(result.priority_fixes)
        self.assertTrue(result.core_web_vitals_notes)

    def test_generate_content_produces_posts(self) -> None:
        canned = (
            "Analysis:\n- topic is trending\n"
            "Problems:\n- generic hooks\n"
            "Optimized Version:\n"
            "Post 1: Hook about WordPress speed + CTA.\n\n"
            "Post 2: Hook about Core Web Vitals + CTA.\n\n"
            "Post 3: Hook about PageSpeed wins + CTA.\n"
            "Hashtags: wordpress, seo, coreWebVitals\n"
            "Hook: stop losing traffic to slow pages\n"
            "Action Steps:\n"
            "1. DM today to book an audit\n"
            "2. Comment 'SPEED' to grab the checklist\n"
            "3. Tag a friend who needs this\n"
        )
        fake = FakeClient(canned)
        assistant = AIAssistant(client=fake)
        envelope, result = assistant.generate_content(
            topic="WordPress speed optimization",
            platform="twitter",
            count=3,
        )
        self.assertEqual(envelope.feature, "generate_content")
        self.assertEqual(result.platform, "twitter")
        self.assertEqual(len(result.posts), 3)
        self.assertTrue(result.hashtags)
        self.assertTrue(result.cta_suggestions)

    def test_improve_output_adds_keywords_and_triggers(self) -> None:
        refined = (
            "Stop losing conversions today. Proven WordPress speed fixes "
            "that land you Core Web Vitals wins and guaranteed PageSpeed "
            "score improvements. Message me now."
        )
        fake = FakeClient(refined)
        assistant = AIAssistant(client=fake)
        envelope, result = assistant.improve_output(
            original_output="I help WordPress sites load faster.",
            target_keywords=["core web vitals", "pagespeed"],
        )
        self.assertEqual(envelope.feature, "improve_output")
        self.assertIn("core web vitals", result.improved_output.lower())
        self.assertTrue(result.psychological_triggers_used)
        self.assertTrue(any("score" in change for change in result.changes_made))

    def test_architect_design_returns_blueprint(self) -> None:
        canned = (
            "Input processing:\n"
            "- Normalize the Fiverr gig JSON and the website URL.\n"
            "- Strip PII before caching.\n"
            "Analysis logic:\n"
            "- Run niche pulse + persona + CRO agents in parallel.\n"
            "- Cache expensive connector calls for 24h.\n"
            "Output structure:\n"
            "- Return the four-part format with a JSON sidecar.\n"
            "Scoring system:\n"
            "- 0-100 rubric with title, description, tags, proof, conversion weights.\n"
            "User experience:\n"
            "- Guided onboarding with a before/after diff.\n"
            "Monetization:\n"
            "- Free tier: 3 audits/mo. Pro: $29/mo.\n"
        )
        assistant = AIAssistant(client=FakeClient(canned))
        envelope, blueprint = assistant.architect_design(product_context="Freelancer SaaS")
        self.assertEqual(envelope.feature, "architect_design")
        self.assertTrue(blueprint.input_processing)
        self.assertTrue(blueprint.analysis_logic)
        self.assertTrue(blueprint.output_structure)
        self.assertTrue(blueprint.scoring_system)
        self.assertTrue(blueprint.ux_flow)
        self.assertTrue(blueprint.monetization_notes)

    def test_self_audit_parses_sections(self) -> None:
        canned = (
            "Weak features:\n"
            "- No team workspaces.\n"
            "- Manual competitor import.\n"
            "Missing monetization:\n"
            "- No usage-based pricing for audits.\n"
            "Poor user experience:\n"
            "- Onboarding skips keyword setup.\n"
            "Feature improvements:\n"
            "- Add a one-click compare view.\n"
            "Pricing strategy:\n"
            "- Free (3 audits), Pro ($29), Agency ($99).\n"
            "Growth hacks:\n"
            "- Public gig score widget for buyers.\n"
        )
        assistant = AIAssistant(client=FakeClient(canned))
        envelope, result = assistant.self_audit(
            product_snapshot={"name": "GigOptimizer AI", "features": ["audit"]}
        )
        self.assertEqual(envelope.feature, "self_audit")
        self.assertTrue(result.weak_features)
        self.assertTrue(result.monetization_gaps)
        self.assertTrue(result.ux_issues)
        self.assertTrue(result.feature_improvements)
        self.assertTrue(result.pricing_strategy)
        self.assertTrue(result.growth_hacks)

    def test_fallback_client_kicks_in_when_primary_raises(self) -> None:
        from gigoptimizer.assistant.client import LLMUnavailableError

        class ExplodingClient:
            name = "boom"
            model = "boom-1"

            def complete(self, messages, *, temperature=0.4, max_tokens=1024):
                raise LLMUnavailableError("network down")

        assistant = AIAssistant(client=ExplodingClient())
        envelope = assistant.ask("hello?")
        self.assertTrue(envelope.fallback_used)
        self.assertEqual(envelope.provider, "deterministic")
        self.assertTrue(envelope.warnings)

    def test_envelope_to_dict_is_json_serializable(self) -> None:
        assistant = AIAssistant(client=FakeClient(FOUR_PART_CANNED))
        envelope = assistant.ask("hi")
        payload = envelope.to_dict()
        # Must survive a round trip through json.
        round_tripped = json.loads(json.dumps(payload))
        self.assertEqual(round_tripped["feature"], "ask")
        self.assertEqual(round_tripped["feature"], "ask")
        self.assertEqual(round_tripped["provider"], "fake")


if __name__ == "__main__":
    unittest.main()
