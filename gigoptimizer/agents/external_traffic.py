from __future__ import annotations

from ..models import NichePulseReport, PersonaInsight


class ExternalTrafficAgent:
    def plan(self, niche_pulse: NichePulseReport, personas: list[PersonaInsight]) -> list[str]:
        top_persona = personas[0].persona if personas else "Small Business Owner"
        top_keyword = niche_pulse.trending_queries[0] if niche_pulse.trending_queries else "wordpress speed optimization"

        actions = [
            f"Publish one monthly case study around '{top_keyword}' showing the bottleneck, fix, and measurable outcome.",
            "Turn one recurring buyer pain point into a short educational post for communities that allow helpful self-promotion.",
            "Create a lightweight checklist, score-breakdown graphic, or plugin-triage post that points readers back to your service.",
            "Track which traffic sources bring actual inquiries or orders so ranking experiments stay grounded in conversions, not vanity clicks.",
        ]

        if top_persona == "WooCommerce Store Owner":
            actions[1] = "Share checkout and product-page performance lessons in store-owner communities where value-first links are allowed."
        elif top_persona == "Developer/Agency":
            actions[0] = "Publish a white-label-friendly speed optimization case study focused on audit quality, implementation, and handoff."

        return actions
