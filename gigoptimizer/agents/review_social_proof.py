from __future__ import annotations

import re

from ..models import GigSnapshot


class ReviewSocialProofAgent:
    def analyze(self, snapshot: GigSnapshot) -> dict[str, object]:
        actions: list[str] = []
        phrases: list[str] = []

        for review in snapshot.reviews:
            text = review.text.strip()
            lowered = text.lower()
            if not text:
                continue
            if re.search(r"\b\d{2,3}\s*(?:to|->|-)\s*\d{2,3}\b", lowered):
                phrases.append(text)
                actions.append("Surface quantified before-and-after wins near the top of the description and in gig images.")
            if "pagespeed" in lowered or "gtmetrix" in lowered:
                actions.append("Reuse tool-specific review language in your bullets so search intent and proof align.")
            if any(term in lowered for term in ["core web vitals", "lcp", "cls"]):
                actions.append("Turn Core Web Vitals phrases from reviews into proof bullets for technical buyers.")
            if any(term in lowered for term in ["checkout", "sales", "revenue"]):
                actions.append("Promote revenue-oriented review language to attract WooCommerce buyers.")

        if not actions:
            actions.append("Collect more outcome-focused reviews that mention scores, Core Web Vitals, or business impact.")

        follow_up_template = (
            "Hi {buyer_name}, I hope the speed improvements are feeling solid on your site. "
            "If everything looks good on your side, I would really appreciate an honest review mentioning the results you noticed most. "
            "If anything still needs attention, send me the details and I will help."
        )

        return {
            "actions": self._dedupe(actions)[:5],
            "proof_phrases": phrases[:3],
            "follow_up_template": follow_up_template,
        }

    def _dedupe(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for item in items:
            key = item.strip().lower()
            if key and key not in seen:
                seen.add(key)
                ordered.append(item)
        return ordered
