from __future__ import annotations

from collections import Counter
import re
from statistics import median

from ..models import CompetitiveGapAnalysis, GigSnapshot, MarketplaceGig


COMMON_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "your",
    "you",
    "will",
    "this",
    "that",
    "from",
    "into",
    "using",
    "make",
    "create",
    "design",
    "offer",
    "service",
    "gig",
}


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
        intent_terms = self._intent_terms(snapshot, marketplace_gigs)

        scored: list[MarketplaceGig] = []
        for gig in marketplace_gigs:
            reasons: list[str] = []
            score = 0.0
            title_lower = gig.title.lower()
            title_term_hits = sum(1 for term in intent_terms if term and term in title_lower)
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
                    rank_position=gig.rank_position,
                    page_number=gig.page_number,
                    is_first_page=gig.is_first_page,
                    search_url=gig.search_url,
                    why_on_page_one=reasons[:4],
                )
            )

        scored.sort(key=lambda item: item.conversion_proxy_score, reverse=True)
        top_competitors = scored[:10]
        title_patterns = self._title_patterns(top_competitors)
        why_competitors_win = self._why_competitors_win(snapshot, top_competitors, median_price, intent_terms)
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
            matched = (gig.matched_term or "").strip().lower()
            if matched:
                phrases[matched] += 3
            for phrase in self._title_phrases(gig.title):
                phrases[phrase] += 1
        return [phrase for phrase, count in phrases.most_common(6) if count >= 2][:5]

    def _why_competitors_win(
        self,
        snapshot: GigSnapshot,
        gigs: list[MarketplaceGig],
        median_price: float | None,
        intent_terms: list[str],
    ) -> list[str]:
        reasons: list[str] = []
        my_title = snapshot.title.lower()
        minimum_hits = 2 if len(intent_terms) >= 3 else 1
        if sum(1 for term in intent_terms[:6] if term in my_title) < minimum_hits:
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
        target_phrase = title_patterns[0] if title_patterns else next(
            (gig.matched_term for gig in gigs if gig.matched_term),
            snapshot.niche,
        )
        if title_patterns:
            actions.append(f"Mirror one of the strongest live title patterns in your own first line, especially terms like '{title_patterns[0]}'.")
        if target_phrase and not any(target_phrase.lower() in item.lower() for item in [snapshot.title, *snapshot.tags]):
            actions.append(f"Add '{target_phrase}' or another exact buyer phrase to the visible title and early description copy.")
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
        if snapshot.tags:
            advantages.append("You already have a starting keyword footprint, so the next gains should come from better search alignment and clearer trust proof.")
        if not advantages:
            advantages.append("Your best advantage is that the current offer appears to close well once a qualified buyer clicks in.")
        return advantages[:4]

    def _intent_terms(self, snapshot: GigSnapshot, gigs: list[MarketplaceGig]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()

        def add(term: str) -> None:
            cleaned = re.sub(r"\s+", " ", str(term or "").strip().lower())
            if len(cleaned) < 3 or cleaned in seen:
                return
            seen.add(cleaned)
            ordered.append(cleaned)

        for gig in gigs:
            add(gig.matched_term)
        for item in [snapshot.niche, snapshot.title, *snapshot.tags]:
            for phrase in self._title_phrases(item):
                add(phrase)
        for gig in gigs[:10]:
            for phrase in self._title_phrases(gig.title):
                add(phrase)
        return ordered[:8]

    def _title_phrases(self, text: str) -> list[str]:
        tokens = [
            token
            for token in re.split(r"[^a-z0-9]+", str(text or "").lower())
            if len(token) > 2 and token not in COMMON_STOPWORDS
        ]
        phrases: list[str] = []
        for size in (2, 3):
            for index in range(len(tokens) - size + 1):
                phrase = " ".join(tokens[index : index + size]).strip()
                if phrase and phrase not in phrases:
                    phrases.append(phrase)
        return phrases[:8]
