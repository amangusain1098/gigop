from __future__ import annotations

from collections import Counter

from ..models import ConnectorStatus, GigSnapshot, KeywordSignal, NichePulseReport


KEYWORD_LIBRARY = [
    "wordpress speed optimization",
    "pagespeed insights",
    "core web vitals",
    "gtmetrix",
    "lcp fix",
    "cls fix",
    "woocommerce speed",
    "speed audit",
    "wordpress performance",
    "technical seo",
    "slow wordpress site",
]


class BuyerIntelligenceAgent:
    def analyze(
        self,
        snapshot: GigSnapshot,
        live_signals: list[KeywordSignal] | None = None,
        connector_status: list[ConnectorStatus] | None = None,
    ) -> NichePulseReport:
        current_visible = " ".join([snapshot.title, *snapshot.tags]).lower()
        broader_context = " ".join(
            [
                snapshot.title,
                snapshot.description,
                *snapshot.tags,
                *snapshot.buyer_messages,
                *[review.text for review in snapshot.reviews],
                *[gig.title for gig in snapshot.competitors],
                *[gig.description_excerpt for gig in snapshot.competitors],
                *[tag for gig in snapshot.competitors for tag in gig.tags],
            ]
        ).lower()

        scores = Counter()
        for keyword in KEYWORD_LIBRARY:
            if keyword in broader_context:
                scores[keyword] += 2
            if keyword in current_visible:
                scores[keyword] += 3
            if any(keyword in gig.title.lower() for gig in snapshot.competitors):
                scores[keyword] += 2
            if any(keyword in review.text.lower() for review in snapshot.reviews):
                scores[keyword] += 1
            if any(keyword in message.lower() for message in snapshot.buyer_messages):
                scores[keyword] += 2

        for signal in live_signals or []:
            keyword = signal.keyword.lower()
            scores[keyword] += 4
            if signal.rising:
                scores[keyword] += 3
            if signal.search_volume is not None:
                if signal.search_volume >= 5000:
                    scores[keyword] += 3
                elif signal.search_volume >= 1000:
                    scores[keyword] += 2
                elif signal.search_volume >= 100:
                    scores[keyword] += 1
            if signal.trend_score is not None and signal.trend_score >= 60:
                scores[keyword] += 2

        trending_queries = [item for item, _ in scores.most_common(5)] or KEYWORD_LIBRARY[:5]
        competitor_gaps = [
            keyword
            for keyword in trending_queries
            if keyword not in current_visible and (keyword in broader_context or any(keyword == signal.keyword.lower() for signal in live_signals or []))
        ]
        keyword_updates = self._short_tag_candidates(competitor_gaps + trending_queries)
        notes = []
        if live_signals:
            notes.append("Trending queries were enriched with live connector signals before scoring the niche pulse.")
        else:
            notes.append("This MVP scored keyword opportunities from your snapshot because no live keyword connectors were used.")
        if connector_status:
            active_sources = [item.connector for item in connector_status if item.status in {"ok", "partial"}]
            if active_sources:
                notes.append(f"Live data sources used in this run: {', '.join(active_sources)}.")
        else:
            notes.append("Add weekly exports from Fiverr analytics and competitor snapshots to turn the pulse report into a real operating loop.")

        live_keyword_signals = sorted(
            live_signals or [],
            key=lambda item: (
                item.rising,
                item.search_volume or 0,
                item.trend_score or 0,
            ),
            reverse=True,
        )[:5]
        data_sources = sorted({signal.source for signal in live_keyword_signals})

        return NichePulseReport(
            trending_queries=trending_queries,
            competitor_gaps=competitor_gaps[:5],
            keyword_updates=keyword_updates[:5],
            notes=notes,
            live_keyword_signals=live_keyword_signals,
            data_sources=data_sources,
        )

    def _short_tag_candidates(self, keywords: list[str]) -> list[str]:
        compact_map = {
            "wordpress speed optimization": "wordpress speed",
            "pagespeed insights": "pagespeed",
            "core web vitals": "core web vitals",
            "woocommerce speed": "woocommerce speed",
            "speed audit": "speed audit",
            "wordpress performance": "wordpress performance",
            "technical seo": "technical seo",
        }
        seen: set[str] = set()
        candidates: list[str] = []
        for keyword in keywords:
            tag = compact_map.get(keyword, keyword)
            if tag in seen:
                continue
            seen.add(tag)
            candidates.append(tag)
        return candidates
