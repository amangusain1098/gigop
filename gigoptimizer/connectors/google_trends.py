from __future__ import annotations

from ..config import GigOptimizerConfig
from ..models import ConnectorStatus, KeywordSignal


class GoogleTrendsConnector:
    name = "google_trends"

    def __init__(self, config: GigOptimizerConfig) -> None:
        self.config = config

    def fetch_keyword_signals(self, keywords: list[str]) -> tuple[list[KeywordSignal], ConnectorStatus]:
        try:
            from pytrends.request import TrendReq
        except ImportError:
            return [], ConnectorStatus(
                connector=self.name,
                status="skipped",
                detail="Install the optional 'live' dependencies to enable Google Trends enrichment.",
            )

        seed_terms = self._dedupe(keywords)[: self.config.google_trends_max_queries]
        if not seed_terms:
            return [], ConnectorStatus(
                connector=self.name,
                status="skipped",
                detail="No seed keywords were available for Google Trends lookup.",
            )

        try:
            trends = TrendReq(hl=self.config.google_trends_hl, tz=self.config.google_trends_tz)
            trends.build_payload(
                seed_terms,
                cat=0,
                timeframe=self.config.google_trends_timeframe,
                geo=self.config.google_trends_geo,
                gprop="",
            )
            signals: list[KeywordSignal] = []
            interest = trends.interest_over_time()
            if not interest.empty:
                latest = interest.iloc[-1]
                for keyword in seed_terms:
                    value = latest.get(keyword)
                    if value is None:
                        continue
                    signals.append(
                        KeywordSignal(
                            keyword=keyword,
                            source=self.name,
                            trend_score=float(value),
                            rising=float(value) >= 60,
                        )
                    )

            related_queries = trends.related_queries()
            for keyword in seed_terms:
                related = related_queries.get(keyword) or {}
                for frame_name, rising in (("rising", True), ("top", False)):
                    frame = related.get(frame_name)
                    if frame is None or getattr(frame, "empty", True):
                        continue
                    for _, row in frame.head(3).iterrows():
                        query = str(row.get("query", "")).strip()
                        value = row.get("value")
                        if not query:
                            continue
                        signals.append(
                            KeywordSignal(
                                keyword=query,
                                source=self.name,
                                trend_score=float(value) if value not in (None, "") else None,
                                rising=rising,
                            )
                        )

            signals = self._merge_signals(signals)
            return signals[:10], ConnectorStatus(
                connector=self.name,
                status="ok",
                detail=f"Collected {len(signals[:10])} keyword signals from Google Trends.",
            )
        except Exception as exc:
            return [], ConnectorStatus(
                connector=self.name,
                status="error",
                detail=f"Google Trends lookup failed: {exc}",
            )

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            key = value.strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            ordered.append(value.strip())
        return ordered

    def _merge_signals(self, signals: list[KeywordSignal]) -> list[KeywordSignal]:
        merged: dict[tuple[str, str], KeywordSignal] = {}
        for signal in signals:
            key = (signal.keyword.lower(), signal.source)
            existing = merged.get(key)
            if existing is None:
                merged[key] = signal
                continue
            if signal.trend_score is not None and (
                existing.trend_score is None or signal.trend_score > existing.trend_score
            ):
                existing.trend_score = signal.trend_score
            existing.rising = existing.rising or signal.rising
        return sorted(
            merged.values(),
            key=lambda item: ((item.trend_score or 0), item.rising),
            reverse=True,
        )
