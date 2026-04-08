from __future__ import annotations

from statistics import mean

from ..models import GigSnapshot


class PricingIntelligenceAgent:
    def recommend(self, snapshot: GigSnapshot) -> list[str]:
        recommendations: list[str] = []
        competitor_prices = [
            gig.starting_price
            for gig in snapshot.competitors
            if gig.starting_price is not None
        ]
        average_price = mean(competitor_prices) if competitor_prices else None
        packages = snapshot.packages

        if not packages:
            return [
                "Create Basic, Standard, and Premium packages around audit, implementation, and verification so buyers can self-segment by urgency and budget."
            ]

        basic = next((pkg for pkg in packages if "basic" in pkg.name.lower()), packages[0])
        standard = next((pkg for pkg in packages if "standard" in pkg.name.lower()), packages[min(1, len(packages) - 1)])
        premium = next((pkg for pkg in packages if "premium" in pkg.name.lower()), packages[-1])

        if average_price is not None:
            if basic.price > average_price * 1.15:
                recommendations.append(
                    f"Your entry offer is above the competitor average of about ${average_price:.0f}; justify it with clearer proof or tighter deliverables."
                )
            elif basic.price < average_price * 0.8:
                recommendations.append(
                    f"Your entry offer is well below the competitor average of about ${average_price:.0f}; raise the floor or narrow scope so it still reads as expert work."
                )
            else:
                recommendations.append(
                    f"Your entry offer sits close to the competitor average of about ${average_price:.0f}; compete on clarity and proof instead of discounting further."
                )

        standard_text = " ".join(standard.highlights).lower()
        premium_text = " ".join(premium.highlights).lower()
        if not any(term in standard_text for term in ["report", "audit", "core web vitals", "verification"]):
            recommendations.append("Use the Standard package as the value anchor by bundling fixes with a before-and-after verification report.")
        if not any(term in premium_text for term in ["rush", "priority", "woocommerce", "monitoring"]):
            recommendations.append("Give Premium a stronger reason to exist, such as rush delivery, WooCommerce focus, or post-fix monitoring.")

        return recommendations[:4]
