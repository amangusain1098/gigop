"""Scoring rubric used by the assistant to grade gigs, audits, and content.

The scoring is intentionally deterministic so the assistant can return a
reproducible number even when the LLM itself is non-deterministic. The LLM
writes the narrative; this module writes the score.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


@dataclass(slots=True)
class GigScoreBreakdown:
    total: int
    title_score: int
    description_score: int
    tag_score: int
    proof_score: int
    conversion_score: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScoringRubric:
    """Rule-based scorer that grades a gig draft from 0-100.

    The breakdown is:

        Title        25
        Description  25
        Tags         15
        Proof        15
        Conversion   20
    """

    POWER_WORDS = (
        "boost",
        "increase",
        "double",
        "proven",
        "guaranteed",
        "fast",
        "expert",
        "professional",
        "audit",
        "optimize",
        "rank",
    )

    METRIC_WORDS = (
        "pagespeed",
        "gtmetrix",
        "core web vitals",
        "lcp",
        "cls",
        "seo",
        "ranking",
        "ctr",
        "conversion",
        "roi",
        "sales",
    )

    def score_gig(
        self,
        *,
        title: str,
        description: str,
        tags: Iterable[str],
        has_faq: bool,
        has_packages: bool,
        has_proof_block: bool,
        target_keywords: Iterable[str] = (),
    ) -> GigScoreBreakdown:
        title_lc = (title or "").strip().lower()
        description_lc = (description or "").strip().lower()
        tag_list = [t.strip().lower() for t in tags if t and t.strip()]
        target_list = [k.strip().lower() for k in target_keywords if k and k.strip()]
        notes: list[str] = []

        # Title (max 25)
        title_score = 0
        if 40 <= len(title) <= 80:
            title_score += 10
        elif title:
            title_score += 5
            notes.append("Title length is outside the 40-80 char sweet spot for Fiverr search snippets.")
        if any(word in title_lc for word in self.POWER_WORDS):
            title_score += 5
        else:
            notes.append("Title has no power / action word.")
        if any(word in title_lc for word in self.METRIC_WORDS):
            title_score += 5
        if target_list and any(kw in title_lc for kw in target_list):
            title_score += 5

        # Description (max 25)
        description_score = 0
        if len(description) >= 400:
            description_score += 8
        elif description:
            description_score += 4
            notes.append("Description is shorter than 400 characters - add deliverables and proof.")
        hit_metric_terms = sum(1 for term in self.METRIC_WORDS if term in description_lc)
        description_score += min(8, hit_metric_terms * 2)
        if any(term in description_lc for term in ("deliver", "you get", "scope")):
            description_score += 4
        else:
            notes.append("Description does not name deliverables explicitly.")
        if any(term in description_lc for term in ("dm", "message", "contact", "order", "cta")):
            description_score += 5
        else:
            notes.append("Description lacks a direct CTA.")

        # Tags (max 15)
        unique_tags = {t for t in tag_list if t}
        if len(unique_tags) >= 5:
            tag_score = 15
        elif unique_tags:
            tag_score = 5 + min(10, len(unique_tags) * 2)
            notes.append(f"Only {len(unique_tags)} tags set - Fiverr allows up to 5.")
        else:
            tag_score = 0
            notes.append("No tags configured.")

        # Proof (max 15)
        proof_score = 0
        if has_proof_block:
            proof_score += 8
        else:
            notes.append("No before/after proof block found.")
        if has_faq:
            proof_score += 4
        else:
            notes.append("No FAQ present - add at least 4 objection-handling questions.")
        if any(word in description_lc for word in ("testimonial", "review", "clients", "case study")):
            proof_score += 3

        # Conversion (max 20)
        conversion_score = 0
        if has_packages:
            conversion_score += 10
        else:
            notes.append("No package tiers - add Basic / Standard / Premium.")
        if any(word in description_lc for word in ("guarantee", "refund", "revision")):
            conversion_score += 5
        if any(word in title_lc + " " + description_lc for word in ("today", "now", "24 hours", "same day")):
            conversion_score += 5

        total = title_score + description_score + tag_score + proof_score + conversion_score
        total = max(0, min(100, total))

        return GigScoreBreakdown(
            total=total,
            title_score=title_score,
            description_score=description_score,
            tag_score=tag_score,
            proof_score=proof_score,
            conversion_score=conversion_score,
            notes=notes,
        )

    def score_text(self, text: str, *, target_keywords: Iterable[str] = ()) -> int:
        """Cheap 0-100 score for a freeform piece of AI output.

        Used by the output improver as a quick "before vs after" signal.
        """

        text_lc = (text or "").lower().strip()
        if not text_lc:
            return 0
        score = 20
        if len(text_lc) >= 300:
            score += 10
        if any(header in text_lc for header in ("analysis", "problems", "optimized", "action steps")):
            score += 15
        score += min(15, sum(2 for word in self.POWER_WORDS if word in text_lc))
        score += min(15, sum(2 for word in self.METRIC_WORDS if word in text_lc))
        for kw in target_keywords:
            if kw and kw.lower() in text_lc:
                score += 3
        if any(trigger in text_lc for trigger in ("today", "now", "limited", "proven", "guaranteed")):
            score += 5
        return max(0, min(100, score))
