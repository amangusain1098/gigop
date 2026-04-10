"""Unified AI Assistant for GigOptimizer AI."""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Mapping

from .client import (
    DeterministicLLMClient,
    LLMClient,
    LLMMessage,
    LLMResponse,
    LLMUnavailableError,
    build_default_client,
)
from .prompts import (
    ARCHITECT_DESIGN_PROMPT,
    CHAIN_OF_THOUGHT_PROMPT,
    CONTENT_REFINER_PROMPT,
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
from .scoring import GigScoreBreakdown, ScoringRubric

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


def _parse_structured(text: str) -> StructuredAnalysis:
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


def _extract_lines(text: str, header: str):
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
        client: LLMClient | None = None,
        rubric: ScoringRubric | None = None,
        system_prompt: str = GIG_OPTIMIZER_SYSTEM_PROMPT,
        default_temperature: float = 0.4,
        default_max_tokens: int = 1024,
    ) -> None:
        self.client = client or build_default_client()
        self.fallback_client = DeterministicLLMClient()
        self.rubric = rubric or ScoringRubric()
        self.system_prompt = system_prompt
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens

    def _call(
        self,
        user_prompt: str,
        *,
        feature: str,
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
        feature: str,
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

    def ask(self, question, *, context=None, temperature=0.4):
        if not question or not question.strip():
            raise ValueError("question must not be empty")
        user_prompt = question.strip()
        if context:
            user_prompt = render_prompt(
                CHAIN_OF_THOUGHT_PROMPT,
                user_request=question.strip(),
                context=context.strip(),
            )
        response, fallback_used, warnings = self._call(
            user_prompt,
            feature="ask",
            temperature=temperature,
        )
        structured = _parse_structured(response.text)
        return self._envelope(
            "ask",
            response,
            structured.to_dict(),
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
