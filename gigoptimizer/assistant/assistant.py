"""Unified AI Assistant for GigOptimizer AI."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field

from .client import (
    DeterministicLLMClient,
    LLMClient,
    LLMMessage,
    LLMUnavailableError,
    build_default_client,
)
from .prompts import (
    ARCHITECT_DESIGN_PROMPT,
    CHAIN_OF_THOUGHT_PROMPT,
    CONTENT_REFINER_PROMPT,
    CONVERSATIONAL_PROMPT,
    CONVERSATIONAL_SYSTEM_PROMPT,
    FIVERR_SEO_EXPERT_PROMPT,
    GIG_OPTIMIZER_SYSTEM_PROMPT,
    SAAS_SELF_AUDIT_PROMPT,
    render_prompt,
)
from .schemas import (
    ArchitectBlueprint,
    ContentGenerationResult,
    FiverrGigOptimizationResult,
    OutputImprovementResult,
    SaaSSelfAuditResult,
    StructuredAnalysis,
    WebsiteAuditResult,
)
from .scoring import ScoringRubric

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AssistantResponse:
    feature: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    latency_ms: int
    raw_text: str
    structured: dict
    score: int | None = None
    fallback_used: bool = False
    warnings: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# Intent classification for the copilot chatbot
# ---------------------------------------------------------------------------
_GREETINGS = {
    "hi", "hii", "hiii", "hiiii", "hello", "helo", "hey", "heya", "hola",
    "yo", "sup", "howdy", "greetings", "good morning", "good afternoon",
    "good evening", "morning", "evening", "gm", "ga", "ge",
}
_THANKS = {
    "thanks", "thank you", "ty", "thx", "thankyou", "appreciate it",
    "cheers", "much appreciated",
}
_HOW_ARE_YOU = {
    "how are you", "how is it going", "hows it going", "how are things",
    "whats up", "how do you do", "how are u", "how r u",
}
_IDENTITY = {
    "who are you", "what are you", "tell me about yourself",
    "introduce yourself", "your name", "what is your name", "whats your name",
    "who is this", "are you a bot", "are you an ai", "are you human",
}
_CAPABILITY = {
    "what do you do", "what can you do", "what can you help with",
    "what can i ask you", "how can you help", "what do you help with",
    "what are you for", "what are you good at", "help me", "how does this work",
    "what is this", "what is gigoptimizer",
}

_CONVERSATIONAL_INTENTS = {"greeting", "thanks", "how_are_you", "identity", "capability",
                          "pricing_question", "comparison"}

_PRICING_QUESTION = {
    "how much does this cost", "what is the price", "how much do you charge",
    "what are your rates", "whats the cost", "how much is it",
    "what is your pricing", "do you offer a discount", "is there a free plan",
    "what does it cost", "cost", "price", "pricing", "how much",
    "what is the fee", "what are the fees", "subscription cost",
}
_COMPARISON = {
    "vs", "versus", "compare", "compared to", "difference between",
    "which is better", "what is the difference", "whats the difference",
    "compare fiverr vs upwork", "fiverr or upwork",
}


def _classify_intent(user_text):
    """Classify a raw user message as conversational or task.

    Returns one of: greeting, thanks, how_are_you, identity,
    capability, empty, or task.
    """
    text = (user_text or "").strip().lower()
    if not text:
        return "empty"

    stripped = text.rstrip("?!.,;: ")
    # Also strip apostrophes/single quotes from the working copy so "what's"
    # matches "whats" without having to enumerate both variants.
    canon = stripped.replace("'", "").replace("\u2019", "")
    words = canon.split()
    word_count = len(words)

    # Anything longer than 8 words is almost always an actual task.
    if word_count > 8:
        return "task"

    if canon in _GREETINGS:
        return "greeting"
    if word_count <= 3 and any(canon == g or canon.startswith(g + " ") for g in _GREETINGS):
        return "greeting"

    if canon in _THANKS or any(canon == t or canon.startswith(t + " ") for t in _THANKS):
        return "thanks"

    if canon in _HOW_ARE_YOU or any(canon.startswith(h) for h in _HOW_ARE_YOU):
        return "how_are_you"

    if canon in _IDENTITY or any(canon.startswith(i) for i in _IDENTITY):
        return "identity"

    if canon in _CAPABILITY or any(canon.startswith(c) for c in _CAPABILITY):
        return "capability"

    if canon in _PRICING_QUESTION or any(canon.startswith(p) for p in _PRICING_QUESTION):
        return "pricing_question"

    # Comparison: look for "vs", "versus", "compare" anywhere in short messages
    if word_count <= 8 and any(kw in words for kw in ("vs", "versus", "compare", "compared")):
        return "comparison"
    if canon in _COMPARISON or any(canon.startswith(c) for c in _COMPARISON):
        return "comparison"

    return "task"


_SECTION_ORDER = ("analysis", "problems", "optimized_version", "action_steps")
_SECTION_HEADERS = {
    "analysis": ("analysis", "1. analysis"),
    "problems": ("problems", "2. problems", "issues"),
    "optimized_version": (
        "optimized version",
        "3. optimized version",
        "optimized",
        "rewrite",
    ),
    "action_steps": (
        "action steps",
        "4. action steps",
        "next steps",
        "action plan",
    ),
}


def _parse_structured(text):
    if not text or not text.strip():
        return StructuredAnalysis()

    lines = text.splitlines()
    current = "analysis"
    buckets = {key: [] for key in _SECTION_ORDER}

    for raw_line in lines:
        stripped = raw_line.strip()
        stripped_lc = stripped.lower().rstrip(":")
        if not stripped:
            if current:
                buckets[current].append("")
            continue
        matched_header = None
        for section, headers in _SECTION_HEADERS.items():
            if any(stripped_lc == h or stripped_lc.startswith(h) for h in headers):
                matched_header = section
                break
        if matched_header:
            current = matched_header
            remainder = stripped.split(":", 1)[1].strip() if ":" in stripped else ""
            if remainder:
                buckets[current].append(remainder)
            continue
        if current is None:
            current = "analysis"
        buckets[current].append(stripped)

    def _bulletize(lines_list):
        items = []
        for line in lines_list:
            if not line:
                continue
            cleaned = re.sub(r"^[\-\*\u2022\d\.\)\s]+", "", line).strip()
            if cleaned:
                items.append(cleaned)
        return items

    analysis_text = "\n".join(line for line in buckets["analysis"] if line).strip()
    problems = _bulletize(buckets["problems"])
    optimized_text = "\n".join(buckets["optimized_version"]).strip()
    action_steps = _bulletize(buckets["action_steps"])

    return StructuredAnalysis(
        analysis=analysis_text,
        problems=problems,
        optimized_version=optimized_text,
        action_steps=action_steps,
    )


def _extract_lines(text, header):
    if not text:
        return []
    lines = text.splitlines()
    collected = []
    capture = False
    for line in lines:
        stripped = line.strip()
        if not capture and stripped.lower().startswith(header.lower()):
            capture = True
            continue
        if capture:
            if not stripped:
                continue
            if re.match(r"^[A-Za-z][A-Za-z ]+:\s*$", stripped):
                break
            cleaned = re.sub(r"^[\-\*\u2022\d\.\)\s]+", "", stripped).strip()
            if cleaned:
                collected.append(cleaned)
    return collected


class AIAssistant:
    def __init__(
        self,
        *,
        client=None,
        rubric=None,
        system_prompt=GIG_OPTIMIZER_SYSTEM_PROMPT,
        default_temperature=0.4,
        default_max_tokens=1024,
        rag_index=None,
    ):
        self.client = client or build_default_client()
        self.fallback_client = DeterministicLLMClient()
        self.rubric = rubric or ScoringRubric()
        self.system_prompt = system_prompt
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens
        self.rag_index = rag_index

    def _call(
        self,
        user_prompt,
        *,
        feature,
        temperature=None,
        max_tokens=None,
        extra_system=None,
    ):
        messages = [LLMMessage(role="system", content=self.system_prompt)]
        if extra_system:
            messages.append(LLMMessage(role="system", content=extra_system))
        messages.append(LLMMessage(role="user", content=user_prompt))

        warnings = []
        fallback_used = False
        start = time.monotonic()
        try:
            response = self.client.complete(
                messages,
                temperature=temperature if temperature is not None else self.default_temperature,
                max_tokens=max_tokens or self.default_max_tokens,
            )
        except LLMUnavailableError as exc:
            logger.warning("primary LLM unavailable for %s: %s", feature, exc)
            warnings.append(f"primary LLM unavailable: {exc}")
            fallback_used = True
            response = self.fallback_client.complete(
                messages,
                temperature=temperature if temperature is not None else self.default_temperature,
                max_tokens=max_tokens or self.default_max_tokens,
            )
        except Exception as exc:
            logger.exception("LLM call failed for %s", feature)
            warnings.append(f"LLM call failed: {exc}")
            fallback_used = True
            response = self.fallback_client.complete(
                messages,
                temperature=temperature if temperature is not None else self.default_temperature,
                max_tokens=max_tokens or self.default_max_tokens,
            )
        latency_ms = int((time.monotonic() - start) * 1000)
        if response.latency_ms == 0:
            response.latency_ms = latency_ms
        return response, fallback_used, warnings

    def _envelope(
        self,
        feature,
        response,
        structured,
        *,
        score,
        fallback_used,
        warnings,
    ):
        return AssistantResponse(
            feature=feature,
            provider=response.provider,
            model=response.model,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            latency_ms=response.latency_ms,
            raw_text=response.text,
            structured=dict(structured),
            score=score,
            fallback_used=fallback_used,
            warnings=list(warnings),
        )

    def ask(self, question, *, context=None, temperature=0.6, use_rag=True):
        if not question or not question.strip():
            raise ValueError("question must not be empty")

        raw_question = question.strip()
        effective_context = context

        if not effective_context and use_rag and self.rag_index is not None:
            try:
                effective_context = self.rag_index.render_context(raw_question, k=3)
            except Exception as exc:
                logger.warning("rag retrieval failed: %s", exc)
                effective_context = None

        user_prompt = raw_question
        if effective_context:
            user_prompt = f"Using this knowledge context:\n\n{effective_context.strip()}\n\nAnswer the user:\n{raw_question}"

        response, fallback_used, warnings = self._call(
            user_prompt,
            feature="ask",
            temperature=temperature,
            max_tokens=1500,
        )
        
        return self._envelope(
            "ask",
            response,
            StructuredAnalysis().to_dict(),
            score=self.rubric.score_text(response.text),
            fallback_used=fallback_used,
            warnings=warnings,
        )

    def optimize_gig(self, *, current_gig, competitor_gigs=None, target_keywords=()):
        gig_blob = (
            current_gig
            if isinstance(current_gig, str)
            else json.dumps(dict(current_gig), indent=2, sort_keys=True, default=str)
        )
        competitor_blob = json.dumps(
            [dict(gig) for gig in (competitor_gigs or [])],
            indent=2,
            sort_keys=True,
            default=str,
        )
        user_prompt = render_prompt(
            FIVERR_SEO_EXPERT_PROMPT,
            current_gig=gig_blob,
            competitor_gigs=competitor_blob,
        )
        response, fallback_used, warnings = self._call(
            user_prompt,
            feature="optimize_gig",
            temperature=0.35,
            max_tokens=1400,
        )
        structured = _parse_structured(response.text)

        title = self._extract_first_line(structured.optimized_version, prefix="title")
        optimized_description = self._extract_block(structured.optimized_version, prefix="description")
        tags = self._extract_inline_list(structured.optimized_version, prefix="tags")
        faq_raw = _extract_lines(response.text, "FAQ")
        faq = [{"question": item, "answer": ""} for item in faq_raw]
        package_names = self._extract_inline_list(structured.optimized_version, prefix="packages")

        breakdown = self.rubric.score_gig(
            title=title or "",
            description=optimized_description or response.text,
            tags=tags,
            has_faq=bool(faq),
            has_packages=bool(package_names),
            has_proof_block="before" in response.text.lower() and "after" in response.text.lower(),
            target_keywords=target_keywords,
        )

        result = FiverrGigOptimizationResult(
            analysis=structured,
            optimized_title=title or "",
            optimized_description=optimized_description or "",
            optimized_tags=tags,
            optimized_faq=faq,
            package_names=package_names,
            score=breakdown.total,
            score_reasoning=breakdown.notes,
            raw_output=response.text,
        )
        envelope = self._envelope(
            "optimize_gig",
            response,
            {**result.to_dict(), "score_breakdown": breakdown.to_dict()},
            score=breakdown.total,
            fallback_used=fallback_used,
            warnings=warnings,
        )
        return envelope, result

    def audit_website(self, *, url=None, copy_sample=None, target_keywords=()):
        if not url and not copy_sample:
            raise ValueError("audit_website needs either a url or a copy_sample")
        payload_lines = []
        if url:
            payload_lines.append(f"URL: {url}")
        if copy_sample:
            payload_lines.append("Copy sample:\n" + copy_sample.strip())
        if target_keywords:
            payload_lines.append("Target keywords: " + ", ".join(target_keywords))
        user_prompt = (
            "Audit the website below for SEO, performance, CRO, and content quality. "
            "Return the four-part format. Name the metric, the expected lift, and how to verify.\n\n"
            + "\n\n".join(payload_lines)
        )
        response, fallback_used, warnings = self._call(
            user_prompt,
            feature="audit_website",
            temperature=0.35,
            max_tokens=1200,
        )
        structured = _parse_structured(response.text)
        priority_fixes = structured.action_steps[:5] or _extract_lines(response.text, "priority")
        seo_keywords = self._extract_inline_list(response.text, prefix="keywords") or list(target_keywords)
        cwv_notes = [
            line for line in structured.problems
            if any(term in line.lower() for term in ("lcp", "cls", "core web", "pagespeed", "tbt", "inp"))
        ]
        blockers = [
            line for line in structured.problems
            if any(term in line.lower() for term in ("cta", "form", "checkout", "signup", "conversion"))
        ]
        score = self.rubric.score_text(response.text, target_keywords=target_keywords)
        result = WebsiteAuditResult(
            analysis=structured,
            priority_fixes=priority_fixes,
            seo_keywords=seo_keywords,
            core_web_vitals_notes=cwv_notes,
            conversion_blockers=blockers,
            score=score,
            raw_output=response.text,
        )
        envelope = self._envelope(
            "audit_website",
            response,
            result.to_dict(),
            score=score,
            fallback_used=fallback_used,
            warnings=warnings,
        )
        return envelope, result

    def generate_content(self, *, topic, platform="linkedin", audience="freelancers and small business owners", count=3, tone="direct, expert-level, conversion-focused"):
        if not topic or not topic.strip():
            raise ValueError("topic must not be empty")
        user_prompt = (
            f"Generate {count} social posts for {platform}.\n"
            f"Topic: {topic.strip()}\n"
            f"Audience: {audience}\n"
            f"Tone: {tone}\n\n"
            "Return each post on its own, followed by a 'Hashtags:' line and a 'Hook:' line. "
            "End with an 'Action Steps:' list of 3 CTA variations. Use the four-part format as a wrapper."
        )
        response, fallback_used, warnings = self._call(
            user_prompt,
            feature="generate_content",
            temperature=0.6,
            max_tokens=1100,
        )
        structured = _parse_structured(response.text)
        source_block = structured.optimized_version or response.text
        # Split by paragraph OR by "Post N:" markers, whichever gives more chunks.
        para_split = [b.strip() for b in re.split(r"\n\s*\n", source_block) if b.strip()]
        post_split = re.split(r"(?im)^\s*post\s*\d+\s*[:\-]", source_block)
        post_split = [p.strip() for p in post_split if p.strip()]
        posts_raw = post_split if len(post_split) > len(para_split) else para_split
        # Drop any chunk that looks like a Hashtags/Hook footer.
        posts_raw = [p for p in posts_raw if not re.match(r"(?i)^(hashtags|hook)\s*:", p)]
        posts = [
            {"index": idx + 1, "content": block}
            for idx, block in enumerate(posts_raw[:count])
        ]
        hashtags = self._extract_inline_list(response.text, prefix="hashtags")
        hooks = _extract_lines(response.text, "hook")
        cta_suggestions = structured.action_steps or _extract_lines(response.text, "cta")

        result = ContentGenerationResult(
            platform=platform,
            posts=posts,
            hashtags=hashtags,
            hooks=hooks,
            cta_suggestions=cta_suggestions,
            raw_output=response.text,
        )
        envelope = self._envelope(
            "generate_content",
            response,
            result.to_dict(),
            score=self.rubric.score_text(response.text),
            fallback_used=fallback_used,
            warnings=warnings,
        )
        return envelope, result

    def improve_output(self, *, original_output, target_keywords=(), audience="freelancers and small business owners"):
        if not original_output or not original_output.strip():
            raise ValueError("original_output must not be empty")
        user_prompt = render_prompt(
            CONTENT_REFINER_PROMPT,
            target_keywords=", ".join(target_keywords) or "(none supplied)",
            audience=audience,
            original_output=original_output.strip(),
        )
        response, fallback_used, warnings = self._call(
            user_prompt,
            feature="improve_output",
            temperature=0.3,
            max_tokens=900,
        )
        improved = response.text.strip() or original_output
        keywords_added = [
            kw for kw in target_keywords
            if kw and kw.lower() in improved.lower() and kw.lower() not in original_output.lower()
        ]
        triggers = [
            trigger for trigger in ("today", "now", "proven", "guaranteed", "limited", "free", "exclusive")
            if trigger in improved.lower()
        ]
        changes_made = []
        before_score = self.rubric.score_text(original_output, target_keywords=target_keywords)
        after_score = self.rubric.score_text(improved, target_keywords=target_keywords)
        changes_made.append(f"score: {before_score} -> {after_score}")
        if keywords_added:
            changes_made.append(f"keywords added: {', '.join(keywords_added)}")
        if triggers:
            changes_made.append(f"triggers used: {', '.join(triggers)}")

        result = OutputImprovementResult(
            improved_output=improved,
            changes_made=changes_made,
            keywords_added=keywords_added,
            psychological_triggers_used=triggers,
        )
        envelope = self._envelope(
            "improve_output",
            response,
            result.to_dict(),
            score=after_score,
            fallback_used=fallback_used,
            warnings=warnings,
        )
        return envelope, result

    def architect_design(self, *, product_context):
        user_prompt = render_prompt(
            ARCHITECT_DESIGN_PROMPT,
            product_context=product_context.strip(),
        )
        response, fallback_used, warnings = self._call(
            user_prompt,
            feature="architect_design",
            temperature=0.3,
            max_tokens=1400,
        )
        blueprint = ArchitectBlueprint(
            input_processing=_extract_lines(response.text, "input processing") or _extract_lines(response.text, "1."),
            analysis_logic=_extract_lines(response.text, "analysis logic") or _extract_lines(response.text, "2."),
            output_structure=_extract_lines(response.text, "output structure") or _extract_lines(response.text, "3."),
            scoring_system=_extract_lines(response.text, "scoring system") or _extract_lines(response.text, "4."),
            ux_flow=_extract_lines(response.text, "user experience") or _extract_lines(response.text, "5."),
            monetization_notes=_extract_lines(response.text, "monetization") or _extract_lines(response.text, "pricing"),
            raw_output=response.text,
        )
        envelope = self._envelope(
            "architect_design",
            response,
            blueprint.to_dict(),
            score=self.rubric.score_text(response.text),
            fallback_used=fallback_used,
            warnings=warnings,
        )
        return envelope, blueprint

    def self_audit(self, *, product_snapshot):
        snapshot_blob = (
            product_snapshot
            if isinstance(product_snapshot, str)
            else json.dumps(dict(product_snapshot), indent=2, default=str)
        )
        user_prompt = render_prompt(SAAS_SELF_AUDIT_PROMPT, product_snapshot=snapshot_blob)
        response, fallback_used, warnings = self._call(
            user_prompt,
            feature="self_audit",
            temperature=0.35,
            max_tokens=1200,
        )
        result = SaaSSelfAuditResult(
            weak_features=_extract_lines(response.text, "weak features"),
            monetization_gaps=_extract_lines(response.text, "missing monetization") or _extract_lines(response.text, "monetization gaps"),
            ux_issues=_extract_lines(response.text, "poor user experience") or _extract_lines(response.text, "ux issues"),
            feature_improvements=_extract_lines(response.text, "feature improvements"),
            pricing_strategy=_extract_lines(response.text, "pricing strategy"),
            growth_hacks=_extract_lines(response.text, "growth hacks"),
            raw_output=response.text,
        )
        envelope = self._envelope(
            "self_audit",
            response,
            result.to_dict(),
            score=self.rubric.score_text(response.text),
            fallback_used=fallback_used,
            warnings=warnings,
        )
        return envelope, result

    @staticmethod
    def _extract_first_line(text, *, prefix):
        if not text:
            return ""
        prefix_lc = prefix.lower()
        for raw_line in text.splitlines():
            stripped = raw_line.strip().lstrip("-*\u2022 ")
            if stripped.lower().startswith(prefix_lc):
                value = stripped.split(":", 1)[1].strip() if ":" in stripped else stripped
                return value
        return ""

    @staticmethod
    def _extract_block(text, *, prefix):
        if not text:
            return ""
        prefix_lc = prefix.lower()
        lines = text.splitlines()
        collected = []
        capture = False
        for raw_line in lines:
            stripped = raw_line.strip()
            if not capture and stripped.lower().startswith(prefix_lc):
                capture = True
                remainder = stripped.split(":", 1)[1].strip() if ":" in stripped else ""
                if remainder:
                    collected.append(remainder)
                continue
            if capture:
                if re.match(r"^[A-Za-z][A-Za-z ]+:\s*$", stripped):
                    break
                if stripped:
                    collected.append(stripped)
        return "\n".join(collected).strip()

    @staticmethod
    def _extract_inline_list(text, *, prefix):
        if not text:
            return []
        prefix_lc = prefix.lower()
        for raw_line in text.splitlines():
            stripped = raw_line.strip().lstrip("-*\u2022 ")
            if stripped.lower().startswith(prefix_lc):
                value = stripped.split(":", 1)[1].strip() if ":" in stripped else ""
                if not value:
                    continue
                parts = re.split(r"[,;|]", value)
                return [part.strip().strip("[]\"'") for part in parts if part.strip()]
        return []

    # -----------------------------------------------------------------------
    # New Copilot Methods — Round 3
    # -----------------------------------------------------------------------

    def generate_title_variants(
        self,
        *,
        current_title: str,
        niche: str,
        competitor_titles: tuple | list = (),
        target_keywords: tuple | list = (),
    ):
        """Generate 5 scored alternative gig title variants.

        Returns :class:`~gigoptimizer.assistant.schemas.TitleVariantsResult`.
        """
        from .prompts import GIG_TITLE_VARIANTS_PROMPT
        from .schemas import TitleVariant, TitleVariantsResult

        prompt = render_prompt(
            GIG_TITLE_VARIANTS_PROMPT,
            current_title=current_title,
            niche=niche,
            competitor_titles="\n".join(f"- {t}" for t in competitor_titles) if competitor_titles else "None provided",
            target_keywords=", ".join(target_keywords) if target_keywords else "None specified",
        )
        response, fallback_used, warnings = self._call(
            prompt,
            feature="generate_title_variants",
            temperature=0.5,
            max_tokens=900,
        )
        raw = response.text

        # Parse VARIANT N: / SCORE: / REASON: blocks
        variants: list[TitleVariant] = []
        lines = raw.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            m = re.match(r"^VARIANT\s*\d+\s*:\s*(.+)$", line, re.IGNORECASE)
            if m:
                variant_text = m.group(1).strip()
                score_val = 7
                reason_val = ""
                # Look ahead for SCORE and REASON
                for j in range(i + 1, min(i + 4, len(lines))):
                    sl = lines[j].strip()
                    sm = re.match(r"^SCORE\s*:\s*(\d+)", sl, re.IGNORECASE)
                    rm = re.match(r"^REASON\s*:\s*(.+)$", sl, re.IGNORECASE)
                    if sm:
                        score_val = min(10, max(1, int(sm.group(1))))
                    if rm:
                        reason_val = rm.group(1).strip()
                variants.append(TitleVariant(variant=variant_text, score=score_val, reason=reason_val))
            i += 1

        # Fallback: split by numbered list if structured parse found nothing
        if not variants:
            for line in lines:
                line = line.strip().lstrip("0123456789.-) ")
                if line and len(line) > 10:
                    variants.append(TitleVariant(variant=line, score=7, reason=""))

        top_pick = max(variants, key=lambda v: v.score).variant if variants else current_title

        result = TitleVariantsResult(
            current_title=current_title,
            variants=variants,
            top_pick=top_pick,
            raw_output=raw,
        )
        envelope = self._envelope(
            "generate_title_variants",
            response,
            result.to_dict(),
            score=None,
            fallback_used=fallback_used,
            warnings=warnings,
        )
        return envelope, result

    def generate_faqs(
        self,
        *,
        gig_title: str,
        niche: str,
        description_excerpt: str = "",
    ):
        """Generate 6 conversion-optimised FAQ pairs for a Fiverr gig.

        Returns :class:`~gigoptimizer.assistant.schemas.FAQGenerationResult`.
        """
        from .prompts import GIG_FAQ_GENERATOR_PROMPT
        from .schemas import FAQGenerationResult, FAQPair

        prompt = render_prompt(
            GIG_FAQ_GENERATOR_PROMPT,
            gig_title=gig_title,
            niche=niche,
            description_excerpt=description_excerpt or "Not provided",
        )
        response, fallback_used, warnings = self._call(
            prompt,
            feature="generate_faqs",
            temperature=0.5,
            max_tokens=800,
        )
        raw = response.text

        pairs: list[FAQPair] = []
        lines = raw.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            q_match = re.match(r"^Q\d*[:.]\s*(.+)$", line, re.IGNORECASE)
            if not q_match:
                q_match = re.match(r"^(?:Question\s*\d*[:.]\s*)(.+)$", line, re.IGNORECASE)
            if q_match:
                question = q_match.group(1).strip().rstrip("?") + "?"
                answer = ""
                for j in range(i + 1, min(i + 5, len(lines))):
                    al = lines[j].strip()
                    a_match = re.match(r"^A\d*[:.]\s*(.+)$", al, re.IGNORECASE)
                    if not a_match:
                        a_match = re.match(r"^(?:Answer\s*\d*[:.]\s*)(.+)$", al, re.IGNORECASE)
                    if a_match:
                        answer = a_match.group(1).strip()
                        i = j
                        break
                if question and answer:
                    pairs.append(FAQPair(question=question, answer=answer))
            i += 1

        result = FAQGenerationResult(
            gig_title=gig_title,
            pairs=pairs,
            raw_output=raw,
        )
        envelope = self._envelope(
            "generate_faqs",
            response,
            result.to_dict(),
            score=None,
            fallback_used=fallback_used,
            warnings=warnings,
        )
        return envelope, result

    def generate_inquiry_reply(
        self,
        *,
        buyer_message: str,
        gig_title: str,
        seller_name: str = "",
        tone: str = "professional",
    ):
        """Generate a professional reply to a buyer inquiry.

        Returns :class:`~gigoptimizer.assistant.schemas.InquiryReplyResult`.
        """
        from .prompts import BUYER_INQUIRY_REPLY_PROMPT
        from .schemas import InquiryReplyResult

        prompt = render_prompt(
            BUYER_INQUIRY_REPLY_PROMPT,
            gig_title=gig_title,
            buyer_message=buyer_message,
            seller_name=seller_name or "the seller",
            tone=tone,
        )
        response, fallback_used, warnings = self._call(
            prompt,
            feature="generate_inquiry_reply",
            temperature=0.55,
            max_tokens=300,
        )
        raw = response.text

        # Clean any preamble the model might add
        reply_text = raw.strip()
        for prefix in ("here is", "here's", "reply:", "response:"):
            lower = reply_text.lower()
            if lower.startswith(prefix):
                reply_text = reply_text[len(prefix):].lstrip(": \n")

        word_count = len(reply_text.split())
        result = InquiryReplyResult(
            reply_text=reply_text,
            word_count=word_count,
            tone=tone,
            raw_output=raw,
        )
        envelope = self._envelope(
            "generate_inquiry_reply",
            response,
            result.to_dict(),
            score=None,
            fallback_used=fallback_used,
            warnings=warnings,
        )
        return envelope, result

    def generate_review_request(
        self,
        *,
        gig_title: str,
        buyer_name: str = "",
        delivery_context: str = "",
    ):
        """Generate a short post-delivery review request message.

        Returns :class:`~gigoptimizer.assistant.schemas.ReviewRequestResult`.
        """
        from .prompts import REVIEW_REQUEST_PROMPT
        from .schemas import ReviewRequestResult

        prompt = render_prompt(
            REVIEW_REQUEST_PROMPT,
            gig_title=gig_title,
            buyer_name=buyer_name or "there",
            delivery_context=delivery_context or "Standard delivery completed",
        )
        response, fallback_used, warnings = self._call(
            prompt,
            feature="generate_review_request",
            temperature=0.55,
            max_tokens=200,
        )
        raw = response.text

        message_text = raw.strip()
        word_count = len(message_text.split())
        result = ReviewRequestResult(
            message_text=message_text,
            word_count=word_count,
            raw_output=raw,
        )
        envelope = self._envelope(
            "generate_review_request",
            response,
            result.to_dict(),
            score=None,
            fallback_used=fallback_used,
            warnings=warnings,
        )
        return envelope, result

    def rewrite_description(
        self,
        *,
        original_description: str,
        gig_title: str,
        niche: str,
        target_keywords: tuple | list = (),
    ):
        """Rewrite a gig description using the 6-section copywriting framework.

        Returns :class:`~gigoptimizer.assistant.schemas.DescriptionRewriteResult`.
        """
        from .prompts import GIG_DESCRIPTION_REWRITER_PROMPT
        from .schemas import DescriptionRewriteResult

        prompt = render_prompt(
            GIG_DESCRIPTION_REWRITER_PROMPT,
            original_description=original_description,
            gig_title=gig_title,
            niche=niche,
            target_keywords=", ".join(target_keywords) if target_keywords else "None specified",
        )
        response, fallback_used, warnings = self._call(
            prompt,
            feature="rewrite_description",
            temperature=0.45,
            max_tokens=700,
        )
        raw = response.text

        rewritten = raw.strip()
        char_count = len(rewritten)

        # Find which target keywords appear in the rewrite
        keywords_used = [kw for kw in target_keywords if kw.lower() in rewritten.lower()]

        result = DescriptionRewriteResult(
            rewritten_description=rewritten,
            char_count=char_count,
            keywords_used=keywords_used,
            raw_output=raw,
        )
        envelope = self._envelope(
            "rewrite_description",
            response,
            result.to_dict(),
            score=None,
            fallback_used=fallback_used,
            warnings=warnings,
        )
        return envelope, result
