from __future__ import annotations

from collections import Counter
from statistics import median

from ..models import CompetitiveGapAnalysis, GigSnapshot, MarketplaceGig


HIGH_INTENT_TERMS = [
    "wordpress",
    "speed",
    "pagespeed",
    "core web vitals",
    "woocommerce",
    "gtmetrix",
    "audit",
    "performance",
]


class CompetitiveAnalysisAgent:
    def analyze(
        self,
        snapshot: GigSnapshot,
        marketplace_gigs: list[MarketplaceGig],
    ) -> CompetitiveGapAnalysis | None:
        if not marketplace_gigs:
            return None

        my_price = min((package.price for package in snapshot.packages), default=0.0)
        my_review_count = len(snapshot.reviews)
        priced = [gig.starting_price for gig in marketplace_gigs if gig.starting_price is not None]
        median_price = median(priced) if priced else None

        scored: list[MarketplaceGig] = []
        for gig in marketplace_gigs:
            reasons: list[str] = []
            score = 0.0
            title_lower = gig.title.lower()
            title_term_hits = sum(1 for term in HIGH_INTENT_TERMS if term in title_lower)
            score += title_term_hits * 8
            if title_term_hits >= 4:
                reasons.append("Their title matches multiple buyer-intent keywords directly.")
            if gig.reviews_count is not None:
                score += min(gig.reviews_count, 400) / 10
                if gig.reviews_count > max(my_review_count, 10):
                    reasons.append("They show more review volume, which increases buyer trust.")
            if gig.rating is not None:
                score += gig.rating * 6
                if gig.rating >= 4.9:
                    reasons.append("They maintain a high visible rating.")
            if gig.delivery_days is not None and gig.delivery_days <= 2:
                score += 8
                reasons.append("They promise faster delivery.")
            if gig.badges:
                score += min(len(gig.badges), 3) * 5
                reasons.append("Their profile carries visible trust badges or seller-level cues.")
            if median_price is not None and gig.starting_price is not None:
                if abs(gig.starting_price - median_price) <= max(median_price * 0.2, 5):
                    score += 10
                    reasons.append("Their entry price sits close to the current market anchor.")
                elif my_price and gig.starting_price < my_price:
                    score += 4
                    reasons.append("Their starting price looks easier to try at first glance.")
            scored.append(
                MarketplaceGig(
                    title=gig.title,
                    url=gig.url,
                    seller_name=gig.seller_name,
                    starting_price=gig.starting_price,
                    rating=gig.rating,
                    reviews_count=gig.reviews_count,
                    delivery_days=gig.delivery_days,
                    badges=gig.badges,
                    snippet=gig.snippet,
                    matched_term=gig.matched_term,
                    conversion_proxy_score=round(score, 1),
                    win_reasons=reasons[:4],
                )
            )

        scored.sort(key=lambda item: item.conversion_proxy_score, reverse=True)
        top_competitors = scored[:5]
        title_patterns = self._title_patterns(top_competitors)
        why_competitors_win = self._why_competitors_win(snapshot, top_competitors, median_price)
        what_to_implement = self._what_to_implement(snapshot, top_competitors, title_patterns, median_price)
        my_advantages = self._my_advantages(snapshot, median_price)

        return CompetitiveGapAnalysis(
            search_terms=list(dict.fromkeys([gig.matched_term for gig in scored if gig.matched_term])),
            proxy_warning="Fiverr does not expose competitors' true conversion rates publicly. This section uses visible trust, price, keyword, delivery, and review signals as conversion proxies.",
            title_patterns=title_patterns,
            top_competitors=top_competitors,
            why_competitors_win=why_competitors_win,
            what_to_implement=what_to_implement,
            my_advantages=my_advantages,
        )

    def _title_patterns(self, gigs: list[MarketplaceGig]) -> list[str]:
        phrases = Counter()
        for gig in gigs:
            title = gig.title.lower()
            for phrase in [
                "core web vitals",
                "pagespeed insights",
                "woocommerce speed",
                "wordpress speed",
                "speed optimization",
                "gtmetrix",
                "manual audit",
            ]:
                if phrase in title:
                    phrases[phrase] += 1
        return [phrase for phrase, _ in phrases.most_common(5)]

    def _why_competitors_win(
        self,
        snapshot: GigSnapshot,
        gigs: list[MarketplaceGig],
        median_price: float | None,
    ) -> list[str]:
        reasons: list[str] = []
        my_title = snapshot.title.lower()
        if sum(1 for term in HIGH_INTENT_TERMS if term in my_title) < 3:
            reasons.append("Your title is less keyword-dense than the strongest public gigs, so competitors likely win more search clicks before buyers even open your offer.")
        top_review_count = max((gig.reviews_count or 0 for gig in gigs), default=0)
        if top_review_count > len(snapshot.reviews):
            reasons.append("Competitors show more visible review volume than your current proof set, which can lift trust and click-through.")
        if median_price is not None:
            my_price = min((package.price for package in snapshot.packages), default=0.0)
            if my_price and my_price < median_price * 0.7:
                reasons.append("Your pricing sits well below the market anchor, which can make the service look less premium even when the work is strong.")
        if snapshot.analytics.clicks and snapshot.analytics.impressions:
            ctr = (snapshot.analytics.clicks / snapshot.analytics.impressions) * 100
            if ctr < 3:
                reasons.append("Your own CTR is still below a strong search benchmark, which points to discovery and positioning as the main gap rather than fulfillment quality.")
        if not reasons:
            reasons.append("The public leaders mostly win on clearer keyword targeting, stronger trust signals, and cleaner market positioning.")
        return reasons[:5]

    def _what_to_implement(
        self,
        snapshot: GigSnapshot,
        gigs: list[MarketplaceGig],
        title_patterns: list[str],
        median_price: float | None,
    ) -> list[str]:
        actions: list[str] = []
        if title_patterns:
            actions.append(f"Mirror one of the strongest live title patterns in your own first line, especially terms like '{title_patterns[0]}'.")
        if not any("pagespeed insights" in item.lower() for item in [snapshot.title, *snapshot.tags]):
            actions.append("Add 'PageSpeed Insights' or another exact buyer phrase to the visible title and early description copy.")
        if median_price is not None:
            my_price = min((package.price for package in snapshot.packages), default=0.0)
            if my_price and my_price < median_price * 0.7:
                actions.append(f"Reposition your entry package closer to the live market anchor of about ${median_price:.0f} or tighten the scope so the price still feels expert.")
        actions.append("Surface one quantified before-and-after result above the fold to close the trust gap with high-review competitors.")
        actions.append("Add a fast-turnaround or rush option if public competitors are consistently advertising short delivery windows.")
        return actions[:5]

    def _my_advantages(self, snapshot: GigSnapshot, median_price: float | None) -> list[str]:
        advantages: list[str] = []
        if snapshot.analytics.impressions and snapshot.analytics.clicks and snapshot.analytics.orders:
            click_to_order = (snapshot.analytics.orders / snapshot.analytics.clicks) * 100 if snapshot.analytics.clicks else 0
            if click_to_order >= 8:
                advantages.append("Once buyers click, your current offer already converts well, so most gains should come from stronger search positioning rather than a full offer rewrite.")
        if median_price is not None:
            my_price = min((package.price for package in snapshot.packages), default=0.0)
            if my_price and my_price <= median_price:
                advantages.append("You already have room to compete on value without racing to the bottom.")
        if any("woocommerce" in message.lower() for message in snapshot.buyer_messages):
            advantages.append("You already attract WooCommerce-flavored demand, which is one of the clearest high-intent buyer segments in this niche.")
        if not advantages:
            advantages.append("Your best advantage is that the current offer appears to close well once a qualified buyer clicks in.")
        return advantages[:4]
