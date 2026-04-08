from __future__ import annotations

from ..models import GigSnapshot, NichePulseReport, PersonaInsight


FAQ_BLUEPRINTS = [
    "Can you improve both mobile and desktop PageSpeed Insights scores?",
    "Do you work on WooCommerce, Elementor, or plugin-heavy WordPress sites?",
    "Will you fix Core Web Vitals issues like LCP and CLS?",
    "What access do you need before starting the optimization?",
    "Do you include a before-and-after speed report after delivery?",
    "Can you guarantee a specific PageSpeed score?",
]


class GigContentOptimizerAgent:
    def optimize(
        self,
        snapshot: GigSnapshot,
        niche_pulse: NichePulseReport,
        personas: list[PersonaInsight],
    ) -> dict[str, list[str]]:
        top_persona = personas[0].persona if personas else "Small Business Owner"
        keyword_anchor = niche_pulse.competitor_gaps[0] if niche_pulse.competitor_gaps else "core web vitals"
        secondary_keyword = niche_pulse.trending_queries[1] if len(niche_pulse.trending_queries) > 1 else "gtmetrix"
        title_variants = [
            "I will fix WordPress page speed and Core Web Vitals",
            f"I will optimize WordPress speed, {keyword_anchor}, and GTmetrix results",
            "I will audit and optimize WordPress performance for faster load times",
            "I will speed up your WordPress site and improve PageSpeed Insights",
            f"I will improve WordPress {secondary_keyword} results with a manual speed audit",
        ]
        if top_persona == "WooCommerce Store Owner":
            title_variants[3] = "I will speed up your WooCommerce store and improve PageSpeed Insights"
        if top_persona == "Developer/Agency":
            title_variants[4] = "I will deliver a white-label WordPress speed audit and fixes"

        description_recommendations = self._description_recommendations(snapshot, top_persona)
        faq_recommendations = self._faq_recommendations(snapshot)
        tag_recommendations = [
            tag
            for tag in niche_pulse.keyword_updates
            if tag.lower() not in {item.lower() for item in snapshot.tags}
        ][:5]

        return {
            "title_variants": self._dedupe(title_variants)[:5],
            "description_recommendations": description_recommendations[:5],
            "faq_recommendations": faq_recommendations[:5],
            "tag_recommendations": tag_recommendations,
        }

    def _description_recommendations(self, snapshot: GigSnapshot, top_persona: str) -> list[str]:
        description = snapshot.description.lower()
        recommendations: list[str] = []

        if not any(term in description for term in ["pagespeed", "gtmetrix", "core web vitals", "lcp", "cls"]):
            recommendations.append("Name the specific metrics and tools you improve so buyers can map your service to their problem instantly.")
        if not any(term in description for term in ["sales", "seo", "ranking", "lead", "conversion", "visitor"]):
            recommendations.append("Open the description with the cost of a slow site before you explain the workflow.")
        if not any(term in description for term in ["report", "audit", "deliver", "before", "after"]):
            recommendations.append("Add a deliverables section that promises an audit, implementation scope, and a before-and-after summary.")
        if not any(term in description for term in ["access", "login", "hosting", "scope", "not included"]):
            recommendations.append("Set scope and access expectations early so serious buyers can self-qualify.")

        persona_specific = {
            "WooCommerce Store Owner": "Move checkout, cart, and product-page language higher because store owners buy revenue recovery, not just scores.",
            "Developer/Agency": "Add white-label and handoff language so agencies can trust you with client work.",
            "Blogger/Content Creator": "Connect speed work directly to rankings, reader retention, and ad performance.",
            "Startup Founder": "Emphasize launch readiness, speed of delivery, and professionalism under deadline.",
        }
        if top_persona in persona_specific:
            recommendations.append(persona_specific[top_persona])

        return self._dedupe(recommendations)

    def _faq_recommendations(self, snapshot: GigSnapshot) -> list[str]:
        existing = " ".join(item.question.lower() for item in snapshot.faq)
        return [question for question in FAQ_BLUEPRINTS if question.lower() not in existing]

    def _dedupe(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for item in items:
            key = item.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            ordered.append(item)
        return ordered
