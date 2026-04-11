"""Dataclass schemas for structured assistant responses.

The project intentionally sticks to plain ``dataclass`` rather than pydantic
to match the style of ``gigoptimizer/models.py`` and keep the install
footprint small.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class StructuredAnalysis:
    """Canonical four-part response shape enforced by the system prompt."""

    analysis: str = ""
    problems: list[str] = field(default_factory=list)
    optimized_version: str = ""
    action_steps: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FiverrGigOptimizationResult:
    analysis: StructuredAnalysis
    optimized_title: str
    optimized_description: str
    optimized_tags: list[str]
    optimized_faq: list[dict[str, str]]
    package_names: list[str]
    score: int
    score_reasoning: list[str]
    raw_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["analysis"] = self.analysis.to_dict()
        return payload


@dataclass(slots=True)
class WebsiteAuditResult:
    analysis: StructuredAnalysis
    priority_fixes: list[str]
    seo_keywords: list[str]
    core_web_vitals_notes: list[str]
    conversion_blockers: list[str]
    score: int
    raw_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["analysis"] = self.analysis.to_dict()
        return payload


@dataclass(slots=True)
class ContentGenerationResult:
    platform: str
    posts: list[dict[str, Any]]
    hashtags: list[str]
    hooks: list[str]
    cta_suggestions: list[str]
    raw_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class OutputImprovementResult:
    improved_output: str
    changes_made: list[str]
    keywords_added: list[str]
    psychological_triggers_used: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ArchitectBlueprint:
    input_processing: list[str]
    analysis_logic: list[str]
    output_structure: list[str]
    scoring_system: list[str]
    ux_flow: list[str]
    monetization_notes: list[str]
    raw_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SaaSSelfAuditResult:
    weak_features: list[str]
    monetization_gaps: list[str]
    ux_issues: list[str]
    feature_improvements: list[str]
    pricing_strategy: list[str]
    growth_hacks: list[str]
    raw_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# New Copilot Schemas — Round 3 additions
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class TitleVariant:
    """A single scored title variant."""
    variant: str
    score: int  # 1-10
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TitleVariantsResult:
    """Result from generate_title_variants()."""
    current_title: str
    variants: list[TitleVariant]
    top_pick: str
    raw_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["variants"] = [v.to_dict() if isinstance(v, TitleVariant) else v for v in self.variants]
        return payload


@dataclass(slots=True)
class FAQPair:
    """A single FAQ question/answer pair."""
    question: str
    answer: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class FAQGenerationResult:
    """Result from generate_faqs()."""
    gig_title: str
    pairs: list[FAQPair]
    raw_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["pairs"] = [p.to_dict() if isinstance(p, FAQPair) else p for p in self.pairs]
        return payload


@dataclass(slots=True)
class InquiryReplyResult:
    """Result from generate_inquiry_reply()."""
    reply_text: str
    word_count: int
    tone: str
    raw_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ReviewRequestResult:
    """Result from generate_review_request()."""
    message_text: str
    word_count: int
    raw_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DescriptionRewriteResult:
    """Result from rewrite_description()."""
    rewritten_description: str
    char_count: int
    keywords_used: list[str]
    raw_output: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
