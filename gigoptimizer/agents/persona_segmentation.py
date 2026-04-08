from __future__ import annotations

from ..models import GigSnapshot, PersonaInsight


PERSONA_RULES = [
    {
        "persona": "Small Business Owner",
        "baseline": 0.42,
        "keywords": ["customer", "business", "lead", "bookings", "service", "calls", "local"],
        "pain_point": "A slow site is costing leads, calls, or trust.",
        "emphasis": [
            "Stress ROI, clarity, and done-for-you execution.",
            "Use simple business language before deep technical detail.",
        ],
    },
    {
        "persona": "WooCommerce Store Owner",
        "baseline": 0.38,
        "keywords": ["woocommerce", "store", "checkout", "cart", "sales", "product page", "revenue"],
        "pain_point": "Slow product and checkout flows are hurting conversions.",
        "emphasis": [
            "Lead with checkout speed, product-page performance, and revenue impact.",
            "Show familiarity with WooCommerce bottlenecks and plugin-heavy stores.",
        ],
    },
    {
        "persona": "Blogger/Content Creator",
        "baseline": 0.32,
        "keywords": ["blog", "seo", "ranking", "traffic", "google", "content", "ads"],
        "pain_point": "Core Web Vitals issues are dragging rankings and readership.",
        "emphasis": [
            "Tie performance work to rankings, traffic retention, and ad revenue.",
            "Mention Core Web Vitals in plain English.",
        ],
    },
    {
        "persona": "Developer/Agency",
        "baseline": 0.3,
        "keywords": ["agency", "developer", "client", "white label", "audit", "handoff", "report"],
        "pain_point": "The buyer needs reliable diagnostics and a clean client handoff.",
        "emphasis": [
            "Highlight white-label friendliness, reporting, and technical depth.",
            "Reduce ambiguity around scope, access, and deliverables.",
        ],
    },
    {
        "persona": "Startup Founder",
        "baseline": 0.28,
        "keywords": ["startup", "launch", "deadline", "demo", "investor", "mvp"],
        "pain_point": "The site needs to feel polished before a launch or demo.",
        "emphasis": [
            "Stress professionalism, urgency, and a predictable turnaround.",
            "Position premium work as de-risking a high-stakes moment.",
        ],
    },
]


class PersonaSegmentationAgent:
    def analyze(self, snapshot: GigSnapshot) -> list[PersonaInsight]:
        signal = " ".join(
            [
                snapshot.title,
                snapshot.description,
                *snapshot.tags,
                *snapshot.buyer_messages,
                *[review.text for review in snapshot.reviews],
            ]
        ).lower()

        insights: list[PersonaInsight] = []
        for rule in PERSONA_RULES:
            score = rule["baseline"]
            for keyword in rule["keywords"]:
                if keyword in signal:
                    score += 0.08
            insights.append(
                PersonaInsight(
                    persona=rule["persona"],
                    score=round(min(score, 1.0), 2),
                    pain_point=rule["pain_point"],
                    emphasis=rule["emphasis"],
                )
            )

        insights.sort(key=lambda item: (-item.score, item.persona))
        return insights[:3]
