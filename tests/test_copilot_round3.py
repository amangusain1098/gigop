"""Tests for Round 3 copilot additions.

Covers:
- _classify_intent(): new pricing_question and comparison intents
- All existing intent buckets (regression guard)
- TitleVariantsResult, FAQGenerationResult, InquiryReplyResult,
  ReviewRequestResult, DescriptionRewriteResult schemas
- The 5 new AIAssistant methods using DeterministicLLMClient
"""
from __future__ import annotations

import importlib
import sys
import types
import unittest
from pathlib import Path

# ---------------------------------------------------------------------------
# Minimal loader that bypasses fastapi/sqlalchemy in sandbox
# ---------------------------------------------------------------------------

def _direct(rel_path: str, mod_name: str):
    """Import a module by file path without the fastapi dependency chain."""
    abs_path = Path(__file__).parent.parent / rel_path
    src = abs_path.read_text(encoding="utf-8")

    # Patch out relative imports that pull in fastapi etc.
    # Only kill lines that import from sibling modules NOT needed here.
    filtered = []
    for line in src.splitlines():
        filtered.append(line)
    src = "\n".join(filtered)

    mod = types.ModuleType(mod_name)
    mod.__file__ = str(abs_path)
    mod.__package__ = mod_name.rsplit(".", 1)[0] if "." in mod_name else ""
    mod.__name__ = mod_name
    sys.modules[mod_name] = mod
    exec(compile(src, str(abs_path), "exec"), mod.__dict__)
    return mod


# ---------------------------------------------------------------------------
# Load the modules we need
# ---------------------------------------------------------------------------

def _load_classify_intent():
    """Return the _classify_intent function from assistant.py using _direct."""
    # We need: client, prompts, schemas, scoring — load stubs or real ones.
    # Easiest: import the real gigoptimizer package if it's on sys.path.
    repo = Path(__file__).parent.parent
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))

    # Pre-register lightweight stubs for heavy deps so the exec() succeeds.
    for dep in ("fastapi", "fastapi.responses", "fastapi.routing",
                "sqlalchemy", "sqlalchemy.orm", "httpx", "uvicorn"):
        if dep not in sys.modules:
            sys.modules[dep] = types.ModuleType(dep)

    # Load the sub-modules that assistant.py imports from its package.
    pkg = "gigoptimizer.assistant"

    def _load_sub(fname, name):
        p = repo / "gigoptimizer" / "assistant" / fname
        m = types.ModuleType(f"{pkg}.{name}")
        m.__file__ = str(p)
        m.__package__ = pkg
        m.__name__ = f"{pkg}.{name}"
        sys.modules[f"{pkg}.{name}"] = m
        exec(compile(p.read_text("utf-8"), str(p), "exec"), m.__dict__)
        return m

    # Order matters: schemas has no deps; client has no deps; scoring depends on nothing heavy.
    _load_sub("schemas.py", "schemas")
    client_mod = _load_sub("client.py", "client")
    _load_sub("scoring.py", "scoring")
    prompts_mod = _load_sub("prompts.py", "prompts")

    # Now load assistant.py
    asst_path = repo / "gigoptimizer" / "assistant" / "assistant.py"
    asst_src = asst_path.read_text("utf-8")

    asst_mod = types.ModuleType(f"{pkg}.assistant")
    asst_mod.__file__ = str(asst_path)
    asst_mod.__package__ = pkg
    asst_mod.__name__ = f"{pkg}.assistant"
    sys.modules[f"{pkg}.assistant"] = asst_mod

    exec(compile(asst_src, str(asst_path), "exec"), asst_mod.__dict__)
    return asst_mod


_asst_mod = None


def _get_asst_mod():
    global _asst_mod
    if _asst_mod is None:
        _asst_mod = _load_classify_intent()
    return _asst_mod


# ===========================================================================
# 1. Intent classification tests
# ===========================================================================

class TestClassifyIntent(unittest.TestCase):

    def setUp(self):
        self.classify = _get_asst_mod()._classify_intent

    # --- greetings ---
    def test_greeting_hi(self):
        self.assertEqual(self.classify("hi"), "greeting")

    def test_greeting_hello(self):
        self.assertEqual(self.classify("hello"), "greeting")

    def test_greeting_hey(self):
        self.assertEqual(self.classify("hey"), "greeting")

    def test_greeting_good_morning(self):
        self.assertEqual(self.classify("good morning"), "greeting")

    def test_greeting_hola(self):
        self.assertEqual(self.classify("hola"), "greeting")

    # --- thanks ---
    def test_thanks_thanks(self):
        self.assertEqual(self.classify("thanks"), "thanks")

    def test_thanks_thank_you(self):
        self.assertEqual(self.classify("thank you"), "thanks")

    def test_thanks_ty(self):
        self.assertEqual(self.classify("ty"), "thanks")

    def test_thanks_thx(self):
        self.assertEqual(self.classify("thx"), "thanks")

    def test_thanks_cheers(self):
        self.assertEqual(self.classify("cheers"), "thanks")

    # --- how_are_you ---
    def test_how_are_you(self):
        self.assertEqual(self.classify("how are you"), "how_are_you")

    def test_hows_it_going(self):
        self.assertEqual(self.classify("hows it going"), "how_are_you")

    def test_whats_up(self):
        self.assertEqual(self.classify("whats up"), "how_are_you")

    # --- identity ---
    def test_identity_who_are_you(self):
        self.assertEqual(self.classify("who are you"), "identity")

    def test_identity_are_you_a_bot(self):
        self.assertEqual(self.classify("are you a bot"), "identity")

    def test_identity_what_is_your_name(self):
        self.assertEqual(self.classify("what is your name"), "identity")

    # --- capability ---
    def test_capability_what_can_you_do(self):
        self.assertEqual(self.classify("what can you do"), "capability")

    def test_capability_help_me(self):
        self.assertEqual(self.classify("help me"), "capability")

    def test_capability_how_does_this_work(self):
        self.assertEqual(self.classify("how does this work"), "capability")

    # --- pricing_question (new) ---
    def test_pricing_how_much(self):
        self.assertEqual(self.classify("how much"), "pricing_question")

    def test_pricing_what_is_the_price(self):
        self.assertEqual(self.classify("what is the price"), "pricing_question")

    def test_pricing_cost(self):
        self.assertEqual(self.classify("cost"), "pricing_question")

    def test_pricing_is_there_a_free_plan(self):
        self.assertEqual(self.classify("is there a free plan"), "pricing_question")

    # --- comparison (new) ---
    def test_comparison_vs(self):
        self.assertEqual(self.classify("fiverr vs upwork"), "comparison")

    def test_comparison_compare(self):
        self.assertEqual(self.classify("compare fiverr vs upwork"), "comparison")

    def test_comparison_versus(self):
        self.assertEqual(self.classify("fiverr versus upwork"), "comparison")

    # --- task (must NOT match conversational) ---
    def test_task_optimize_gig(self):
        self.assertEqual(self.classify("optimize my logo gig title"), "task")

    def test_task_keywords(self):
        self.assertEqual(self.classify("what keywords rank best for video editing"), "task")

    def test_task_analyze_competitors(self):
        self.assertEqual(self.classify("analyze my fiverr competitors"), "task")

    def test_task_seo_tags(self):
        self.assertEqual(self.classify("write seo tags for my gig"), "task")

    # --- edge cases ---
    def test_empty_string(self):
        self.assertEqual(self.classify(""), "empty")

    def test_none_like_empty(self):
        self.assertEqual(self.classify("   "), "empty")

    def test_long_sentence_is_task(self):
        long = "I want to know how I can optimize my fiverr gig for the logo design niche"
        self.assertEqual(self.classify(long), "task")


# ===========================================================================
# 2. Schema unit tests (no LLM needed)
# ===========================================================================

class TestNewSchemas(unittest.TestCase):

    def setUp(self):
        mod = _get_asst_mod()
        # schemas live in the schemas sub-module
        import importlib
        self.schemas = sys.modules.get("gigoptimizer.assistant.schemas")

    def test_title_variant_to_dict(self):
        TitleVariant = self.schemas.TitleVariant
        v = TitleVariant(variant="I will design a minimal logo", score=8, reason="Keyword-rich")
        d = v.to_dict()
        self.assertEqual(d["variant"], "I will design a minimal logo")
        self.assertEqual(d["score"], 8)

    def test_title_variants_result_top_pick(self):
        TitleVariant = self.schemas.TitleVariant
        TitleVariantsResult = self.schemas.TitleVariantsResult
        variants = [
            TitleVariant("Title A", 6, "ok"),
            TitleVariant("Title B", 9, "great"),
            TitleVariant("Title C", 7, "good"),
        ]
        result = TitleVariantsResult(
            current_title="Old title",
            variants=variants,
            top_pick="Title B",
        )
        self.assertEqual(result.top_pick, "Title B")
        d = result.to_dict()
        self.assertIn("variants", d)
        self.assertEqual(len(d["variants"]), 3)

    def test_faq_pair_to_dict(self):
        FAQPair = self.schemas.FAQPair
        p = FAQPair(question="Do you offer revisions?", answer="Yes, 3 free revisions included.")
        d = p.to_dict()
        self.assertIn("question", d)
        self.assertIn("answer", d)

    def test_faq_generation_result_to_dict(self):
        FAQPair = self.schemas.FAQPair
        FAQGenerationResult = self.schemas.FAQGenerationResult
        result = FAQGenerationResult(
            gig_title="Logo Design",
            pairs=[FAQPair("Q?", "A.")],
        )
        d = result.to_dict()
        self.assertEqual(d["gig_title"], "Logo Design")
        self.assertEqual(len(d["pairs"]), 1)

    def test_inquiry_reply_result(self):
        InquiryReplyResult = self.schemas.InquiryReplyResult
        r = InquiryReplyResult(reply_text="Hello there\!", word_count=2, tone="professional")
        self.assertEqual(r.word_count, 2)
        d = r.to_dict()
        self.assertIn("tone", d)

    def test_review_request_result(self):
        ReviewRequestResult = self.schemas.ReviewRequestResult
        r = ReviewRequestResult(message_text="Thanks for ordering\!", word_count=3)
        self.assertEqual(r.word_count, 3)

    def test_description_rewrite_result(self):
        DescriptionRewriteResult = self.schemas.DescriptionRewriteResult
        r = DescriptionRewriteResult(
            rewritten_description="New description with seo keywords.",
            char_count=36,
            keywords_used=["seo"],
        )
        self.assertIn("seo", r.keywords_used)


# ===========================================================================
# 3. New assistant method tests (DeterministicLLMClient)
# ===========================================================================

class TestNewAssistantMethods(unittest.TestCase):

    def setUp(self):
        mod = _get_asst_mod()
        AIAssistant = mod.AIAssistant
        client_module = sys.modules["gigoptimizer.assistant.client"]

        CANNED_TITLE = (
            "VARIANT 1: I will design a professional minimal logo for your brand\n"
            "SCORE: 9\n"
            "REASON: High search volume keywords, buyer-focused language.\n\n"
            "VARIANT 2: I will create a unique modern logo design with unlimited revisions\n"
            "SCORE: 8\n"
            "REASON: Includes revision guarantee converts well.\n\n"
            "VARIANT 3: I will craft a clean minimalist logo in 24 hours\n"
            "SCORE: 7\n"
            "REASON: Speed angle appeals to urgent buyers.\n\n"
            "VARIANT 4: I will design a custom logo for your startup or small business\n"
            "SCORE: 7\n"
            "REASON: Niche targeting increases click-through.\n\n"
            "VARIANT 5: I will redesign your logo into a modern vector masterpiece\n"
            "SCORE: 6\n"
            "REASON: Redesign angle captures existing brand owners.\n"
        )
        CANNED_FAQ = (
            "Q1: What file formats will I receive?\n"
            "A1: You will receive PNG, SVG, PDF, and AI files.\n\n"
            "Q2: How many revisions are included?\n"
            "A2: Three free revisions are included in every package.\n\n"
            "Q3: Do you need my existing brand assets?\n"
            "A3: Not required, but helpful if you have them.\n\n"
            "Q4: Can you match my existing brand colors?\n"
            "A4: Absolutely, just share your brand color codes.\n\n"
            "Q5: What is the delivery time?\n"
            "A5: Standard delivery is 3 business days.\n\n"
            "Q6: Is there a satisfaction guarantee?\n"
            "A6: Yes I will keep revising until you are happy.\n"
        )
        CANNED_INQUIRY = (
            "Hi\! Thanks for reaching out about my logo design service. "
            "I would love to help you create the perfect logo for your brand. "
            "Could you share your brand name, preferred colors, and style? "
            "I will get started right away once I have those details."
        )
        CANNED_REVIEW = (
            "Hi\! I just delivered your logo files. I hope you love them\! "
            "If you are happy with the results, an honest review would mean the world to me. "
            "It helps other buyers find my service. Thank you so much\!"
        )
        CANNED_DESC = (
            "Struggling to stand out on Fiverr? Your logo is the first thing buyers notice.\n\n"
            "Many sellers waste clicks on generic gig pages that fail to convert. "
            "With 5 years of brand design experience and 200+ five-star reviews, "
            "I deliver logos that tell your story at a glance.\n\n"
            "What you get: custom vector logo, unlimited revisions, commercial license.\n\n"
            "Order now or message me to build your brand today."
        )

        _responses = {
            "generate_title_variants": CANNED_TITLE,
            "generate_faqs": CANNED_FAQ,
            "generate_inquiry_reply": CANNED_INQUIRY,
            "generate_review_request": CANNED_REVIEW,
            "rewrite_description": CANNED_DESC,
        }

        LLMResponse = client_module.LLMResponse

        class CannedClient:
            name = "canned"
            model = "canned-v1"

            def complete(self, messages, *, temperature=0.4, max_tokens=1024, **kw):
                # Route by inspecting the last user message content
                user_text = ""
                for m in reversed(messages):
                    if getattr(m, "role", None) == "user":
                        user_text = (m.content or "").lower()
                        break
                if "variant" in user_text or "title variants" in user_text or "5 alternative" in user_text:
                    key = "generate_title_variants"
                elif "faq" in user_text or "q1:" in user_text or "q&a" in user_text or "frequently asked" in user_text:
                    key = "generate_faqs"
                elif "buyer message" in user_text or "inquiry" in user_text or "buyer_message" in user_text:
                    key = "generate_inquiry_reply"
                elif "review" in user_text and "request" in user_text:
                    key = "generate_review_request"
                elif "rewrite" in user_text or "original description" in user_text:
                    key = "rewrite_description"
                else:
                    key = "generate_title_variants"  # safe fallback
                return LLMResponse(
                    text=_responses[key],
                    model="canned-v1",
                    provider="canned",
                    latency_ms=1,
                )

        self.assistant = AIAssistant(client=CannedClient())

    # --- generate_title_variants ---
    def test_title_variants_returns_envelope(self):
        env, result = self.assistant.generate_title_variants(
            current_title="I will design a logo",
            niche="logo design",
            target_keywords=["minimal logo", "professional logo"],
        )
        self.assertEqual(env.feature, "generate_title_variants")

    def test_title_variants_parses_variants(self):
        env, result = self.assistant.generate_title_variants(
            current_title="I will design a logo",
            niche="logo design",
        )
        result = result
        self.assertGreater(len(result.variants), 0)

    def test_title_variants_top_pick_is_highest_score(self):
        env, result = self.assistant.generate_title_variants(
            current_title="I will design a logo",
            niche="logo design",
        )
        result = result
        top_score = max(v.score for v in result.variants)
        top_variant = next(v for v in result.variants if v.score == top_score)
        self.assertEqual(result.top_pick, top_variant.variant)

    def test_title_variants_result_to_dict(self):
        env, result = self.assistant.generate_title_variants(
            current_title="I will design a logo",
            niche="logo design",
        )
        d = result.to_dict()
        self.assertIn("variants", d)
        self.assertIn("top_pick", d)

    # --- generate_faqs ---
    def test_generate_faqs_returns_envelope(self):
        env, result = self.assistant.generate_faqs(
            gig_title="Professional Logo Design",
            niche="logo design",
        )
        self.assertEqual(env.feature, "generate_faqs")

    def test_generate_faqs_parses_pairs(self):
        env, result = self.assistant.generate_faqs(
            gig_title="Professional Logo Design",
            niche="logo design",
        )
        result = result
        self.assertGreater(len(result.pairs), 0)

    def test_generate_faqs_questions_end_with_question_mark(self):
        env, result = self.assistant.generate_faqs(
            gig_title="Professional Logo Design",
            niche="logo design",
        )
        for pair in result.pairs:
            self.assertTrue(pair.question.endswith("?"),
                            "Question does not end with ?: " + repr(pair.question))

    def test_generate_faqs_to_dict(self):
        env, result = self.assistant.generate_faqs(
            gig_title="Professional Logo Design",
            niche="logo design",
        )
        d = result.to_dict()
        self.assertIn("pairs", d)

    # --- generate_inquiry_reply ---
    def test_inquiry_reply_returns_envelope(self):
        env, result = self.assistant.generate_inquiry_reply(
            buyer_message="Hi, can you design a logo for my bakery?",
            gig_title="Professional Logo Design",
        )
        self.assertEqual(env.feature, "generate_inquiry_reply")

    def test_inquiry_reply_has_text(self):
        env, result = self.assistant.generate_inquiry_reply(
            buyer_message="Hi, can you design a logo for my bakery?",
            gig_title="Professional Logo Design",
            seller_name="Alex",
            tone="friendly",
        )
        self.assertGreater(len(result.reply_text), 10)

    def test_inquiry_reply_word_count(self):
        env, result = self.assistant.generate_inquiry_reply(
            buyer_message="Hi, can you design a logo for my bakery?",
            gig_title="Professional Logo Design",
        )
        result = result
        self.assertEqual(result.word_count, len(result.reply_text.split()))

    # --- generate_review_request ---
    def test_review_request_returns_envelope(self):
        env, result = self.assistant.generate_review_request(
            gig_title="Professional Logo Design",
            buyer_name="Sarah",
        )
        self.assertEqual(env.feature, "generate_review_request")

    def test_review_request_has_message(self):
        env, result = self.assistant.generate_review_request(
            gig_title="Professional Logo Design",
        )
        self.assertGreater(len(result.message_text), 10)

    def test_review_request_word_count(self):
        env, result = self.assistant.generate_review_request(
            gig_title="Professional Logo Design",
            buyer_name="Sarah",
            delivery_context="Delivered 3 logo variants",
        )
        result = result
        self.assertEqual(result.word_count, len(result.message_text.split()))

    # --- rewrite_description ---
    def test_rewrite_description_returns_envelope(self):
        env, result = self.assistant.rewrite_description(
            original_description="I will design a logo for you.",
            gig_title="Professional Logo Design",
            niche="logo design",
        )
        self.assertEqual(env.feature, "rewrite_description")

    def test_rewrite_description_has_content(self):
        env, result = self.assistant.rewrite_description(
            original_description="I will design a logo for you.",
            gig_title="Professional Logo Design",
            niche="logo design",
            target_keywords=["logo", "brand", "vector"],
        )
        self.assertGreater(result.char_count, 50)

    def test_rewrite_description_tracks_keywords(self):
        env, result = self.assistant.rewrite_description(
            original_description="I will design a logo for you.",
            gig_title="Professional Logo Design",
            niche="logo design",
            target_keywords=["logo", "brand", "vector"],
        )
        # "logo" appears in canned response — should be found
        self.assertIn("logo", result.keywords_used)

    def test_rewrite_description_to_dict(self):
        env, result = self.assistant.rewrite_description(
            original_description="I will design a logo for you.",
            gig_title="Professional Logo Design",
            niche="logo design",
        )
        d = result.to_dict()
        self.assertIn("rewritten_description", d)
        self.assertIn("char_count", d)
        self.assertIn("keywords_used", d)


if __name__ == "__main__":
    unittest.main(verbosity=2)
