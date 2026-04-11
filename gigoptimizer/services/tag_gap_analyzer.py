"""SEO Tag Gap Analyzer.

Compares a seller's gig tags against page-one competitor tags and returns
three actionable buckets:

  missing  — tags competitors use that you do not (opportunity)
  unique   — tags only you use (differentiation signal)
  shared   — tags the majority of top sellers share (must-haves)

Also surfaces power_tags: highest-frequency competitor tags scored by
frequency x specificity, and a coverage_score (0-100).
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any

from ..models import GigSnapshot, MarketplaceGig


@dataclass(slots=True)
class TagGapReport:
    my_tags: list[str]
    missing_tags: list[str]
    unique_tags: list[str]
    shared_tags: list[str]
    power_tags: list[str]
    coverage_score: int
    recommendations: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TagGapAnalyzer:
    SHARED_THRESHOLD = 0.5
    MIN_POWER_TAG_CHARS = 5

    def analyze(
        self,
        snapshot: GigSnapshot,
        competitor_gigs: list[MarketplaceGig] | None = None,
    ) -> TagGapReport:
        my_tags_raw = list(snapshot.tags or [])
        my_lower = {t.lower().strip() for t in my_tags_raw if t.strip()}

        all_comp_tags: list[list[str]] = []
        if competitor_gigs:
            all_comp_tags = [
                [t.lower().strip() for t in (g.tags or []) if t.strip()]
                for g in competitor_gigs
            ]
        elif snapshot.competitors:
            all_comp_tags = [
                [t.lower().strip() for t in (c.tags or []) if t.strip()]
                for c in snapshot.competitors
            ]

        if not all_comp_tags:
            return TagGapReport(
                my_tags=my_tags_raw, missing_tags=[], unique_tags=my_tags_raw,
                shared_tags=[], power_tags=[], coverage_score=50,
                recommendations=[
                    "Run a competitor scan first to generate tag gap data.",
                    "Use the Competitor Analysis tool and re-run this report.",
                ],
            )

        n = len(all_comp_tags)
        freq: Counter[str] = Counter()
        for tags in all_comp_tags:
            for t in set(tags):
                freq[t] += 1

        threshold = max(1, int(n * self.SHARED_THRESHOLD))
        shared = sorted([t for t, c in freq.items() if c >= threshold], key=lambda t: -freq[t])
        missing = [t for t in shared if t not in my_lower]
        unique = sorted(my_lower - set(freq.keys()))
        power = sorted(
            [t for t in freq if len(t) >= self.MIN_POWER_TAG_CHARS],
            key=lambda t: -(freq[t] * 10 + (1 if len(t) > 10 else 0)),
        )[:10]

        coverage = int((sum(1 for t in shared if t in my_lower) / len(shared)) * 100) if shared else 80

        recs: list[str] = []
        if coverage < 40:
            recs.append(f"Critical: your tags cover only {coverage}% of must-have terms. Update urgently.")
        elif coverage < 70:
            recs.append(f"Tag coverage {coverage}% — adding missing shared tags will directly improve search placement.")
        else:
            recs.append(f"Strong tag coverage at {coverage}%. Focus on adding high-frequency power tags you are still missing.")

        if missing:
            top3 = ", ".join(f'"{t}"' for t in missing[:3])
            recs.append(f"Add these high-priority missing tags: {top3}. They appear on most page-one gigs.")

        if len(my_lower) < 5:
            recs.append(f"You are using only {len(my_lower)}/5 available tag slots. Fill all 5.")

        if unique and coverage >= 60:
            recs.append(f"Your unique tag(s) {list(unique)[:2]} are differentiation signals — keep if buyers search for them.")
        elif unique:
            recs.append(f"Your unique tag(s) {list(unique)[:2]} don't appear among competitors — verify search volume or swap.")

        top_power_missing = [t for t in power[:5] if t not in my_lower]
        if top_power_missing:
            recs.append(f"Top power tags you are missing: {top_power_missing[:3]}. High frequency + specificity = strong ranking signal.")

        return TagGapReport(
            my_tags=my_tags_raw, missing_tags=missing[:10], unique_tags=list(unique)[:5],
            shared_tags=shared[:10], power_tags=power[:10],
            coverage_score=coverage, recommendations=recs,
        )
