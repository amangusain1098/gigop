from __future__ import annotations

from ..models import ConversionAudit, GigSnapshot


class CROAgent:
    def audit(self, snapshot: GigSnapshot) -> ConversionAudit:
        analytics = snapshot.analytics
        ctr = round((analytics.clicks / analytics.impressions) * 100, 2) if analytics.impressions else None
        click_to_order = round((analytics.orders / analytics.clicks) * 100, 2) if analytics.clicks else None

        findings: list[str] = []
        actions: list[str] = []

        if ctr is None:
            findings.append("No impression data is available yet, so top-of-funnel discovery cannot be benchmarked.")
            actions.append("Start tracking weekly impressions and clicks to learn whether the bottleneck is visibility or conversion.")
        elif ctr < 2.5:
            findings.append(f"Your impression-to-click rate is {ctr}%, which points to a weak search-result promise.")
            actions.append("Refresh the title, thumbnail, and top tags before touching pricing or package structure.")
        elif ctr < 4:
            findings.append(f"Your impression-to-click rate is {ctr}%, which is workable but still leaves room for sharper positioning.")
            actions.append("Test a more outcome-driven title that names WordPress speed, Core Web Vitals, or WooCommerce impact explicitly.")
        else:
            findings.append(f"Your impression-to-click rate is {ctr}%, so discovery is healthy and deeper funnel issues matter more.")

        if click_to_order is None:
            findings.append("There are not enough clicks yet to diagnose order conversion with confidence.")
        elif click_to_order < 8:
            findings.append(f"Your click-to-order rate is {click_to_order}%, which suggests the offer is not closing the promise.")
            actions.append("Improve proof, package clarity, and scope framing inside the description and FAQs.")
        else:
            findings.append(f"Your click-to-order rate is {click_to_order}%, which means the offer is converting once buyers click.")

        if analytics.average_response_time_hours is not None and analytics.average_response_time_hours > 3:
            findings.append(
                f"Your average response time is {analytics.average_response_time_hours} hours, which can cost high-intent buyers."
            )
            actions.append("Use saved replies or inbox triage blocks to keep response time under three hours.")

        if analytics.package_mix:
            dominant_tier = max(analytics.package_mix, key=analytics.package_mix.get)
            findings.append(f"Your strongest current package mix appears to favor the {dominant_tier} tier.")

        return ConversionAudit(
            impression_to_click_rate=ctr,
            click_to_order_rate=click_to_order,
            findings=findings[:5],
            actions=actions[:5],
        )
