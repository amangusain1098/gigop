from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from .agents import (
    BuyerIntelligenceAgent,
    CompetitiveAnalysisAgent,
    CROAgent,
    ExternalTrafficAgent,
    GigContentOptimizerAgent,
    PersonaSegmentationAgent,
    PricingIntelligenceAgent,
    ReviewSocialProofAgent,
)
from .config import GigOptimizerConfig
from .connectors import (
    FiverrMarketplaceConnector,
    FiverrSellerConnector,
    GoogleTrendsConnector,
    SemrushConnector,
    SerpApiSearchConnector,
)
from .models import CompetitorGig, GigAnalytics, GigSnapshot, LiveResearchBundle, OptimizationReport


class GigOptimizerOrchestrator:
    def __init__(
        self,
        *,
        config: GigOptimizerConfig | None = None,
        google_trends: GoogleTrendsConnector | None = None,
        semrush: SemrushConnector | None = None,
        serpapi: SerpApiSearchConnector | None = None,
        fiverr: FiverrSellerConnector | None = None,
        marketplace: FiverrMarketplaceConnector | None = None,
    ) -> None:
        self.config = config or GigOptimizerConfig.from_env()
        self.buyer_intelligence = BuyerIntelligenceAgent()
        self.competitive_analysis = CompetitiveAnalysisAgent()
        self.content_optimizer = GigContentOptimizerAgent()
        self.persona_segmentation = PersonaSegmentationAgent()
        self.cro = CROAgent()
        self.pricing = PricingIntelligenceAgent()
        self.review_social_proof = ReviewSocialProofAgent()
        self.external_traffic = ExternalTrafficAgent()
        self.google_trends = google_trends or GoogleTrendsConnector(self.config)
        self.semrush = semrush or SemrushConnector(self.config)
        self.serpapi = serpapi or SerpApiSearchConnector(self.config)
        self.fiverr = fiverr or FiverrSellerConnector(self.config)
        self.marketplace = marketplace or FiverrMarketplaceConnector(self.config)

    def optimize(self, snapshot: GigSnapshot, *, use_live_connectors: bool = False) -> OptimizationReport:
        effective_snapshot, live_research = self.prepare_run(
            snapshot,
            use_live_connectors=use_live_connectors,
        )
        return self.optimize_prepared(effective_snapshot, live_research)

    def optimize_prepared(
        self,
        effective_snapshot: GigSnapshot,
        live_research: LiveResearchBundle,
        *,
        progress_callback=None,
    ) -> OptimizationReport:
        self._notify_progress(progress_callback, "Buyer Intelligence", 1, 7)
        niche_pulse = self.buyer_intelligence.analyze(
            effective_snapshot,
            live_signals=live_research.keyword_signals,
            connector_status=live_research.connector_status,
        )
        self._notify_progress(progress_callback, "Persona Segmentation", 2, 7)
        personas = self.persona_segmentation.analyze(effective_snapshot)
        self._notify_progress(progress_callback, "Gig Content Optimizer", 3, 7)
        content = self.content_optimizer.optimize(effective_snapshot, niche_pulse, personas)
        self._notify_progress(progress_callback, "CRO", 4, 7)
        conversion_audit = self.cro.audit(effective_snapshot)
        self._notify_progress(progress_callback, "Pricing Intelligence", 5, 7)
        pricing_recommendations = self.pricing.recommend(effective_snapshot)
        self._notify_progress(progress_callback, "Review & Social Proof", 6, 7)
        review_analysis = self.review_social_proof.analyze(effective_snapshot)
        self._notify_progress(progress_callback, "External Traffic", 7, 7)
        external_traffic_actions = self.external_traffic.plan(niche_pulse, personas)
        competitive_gap_analysis = self.competitive_analysis.analyze(
            effective_snapshot,
            live_research.marketplace_gigs,
        )
        weekly_action_plan = self._weekly_action_plan(
            niche_pulse=niche_pulse,
            content=content,
            conversion_actions=conversion_audit.actions,
            pricing_recommendations=pricing_recommendations,
            review_actions=review_analysis["actions"],
            competitive_actions=(competitive_gap_analysis.what_to_implement if competitive_gap_analysis else []),
        )
        score = self._score(effective_snapshot, niche_pulse, conversion_audit, review_analysis["actions"])

        caution_notes = [
            "This project is an optimization planner, not a stealth scraper. Add live connectors only when they fit platform rules and your risk tolerance.",
            "Use review follow-ups to request honest feedback, not only positive reviews.",
            "External traffic tactics should stay value-first and community-safe to avoid account risk.",
        ]

        return OptimizationReport(
            optimization_score=score,
            niche_pulse=niche_pulse,
            persona_insights=personas,
            title_variants=content["title_variants"],
            description_recommendations=content["description_recommendations"],
            faq_recommendations=content["faq_recommendations"],
            tag_recommendations=content["tag_recommendations"],
            conversion_audit=conversion_audit,
            pricing_recommendations=pricing_recommendations,
            review_actions=review_analysis["actions"],
            review_follow_up_template=str(review_analysis["follow_up_template"]),
            external_traffic_actions=external_traffic_actions,
            weekly_action_plan=weekly_action_plan,
            caution_notes=caution_notes,
            competitive_gap_analysis=competitive_gap_analysis,
            connector_status=live_research.connector_status,
        )

    def _notify_progress(self, callback, agent_name: str, step: int, total_steps: int) -> None:
        if callback is None:
            return
        callback(
            {
                "agent_name": agent_name,
                "step": step,
                "total_steps": total_steps,
                "progress": round((step / total_steps) * 100, 2),
            }
        )

    def optimize_file(self, path: str | Path, *, use_live_connectors: bool = False) -> OptimizationReport:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return self.optimize(GigSnapshot.from_dict(payload), use_live_connectors=use_live_connectors)

    def prepare_run(
        self,
        snapshot: GigSnapshot,
        *,
        use_live_connectors: bool = False,
        include_marketplace: bool = False,
        marketplace_search_terms: list[str] | None = None,
        marketplace_observer=None,
    ) -> tuple[GigSnapshot, LiveResearchBundle]:
        live_research = (
            self._collect_live_research(
                snapshot,
                include_marketplace=include_marketplace,
                marketplace_search_terms=marketplace_search_terms,
                marketplace_observer=marketplace_observer,
            )
            if use_live_connectors
            else LiveResearchBundle()
        )
        effective_snapshot = self._apply_live_metrics(snapshot, live_research.seller_metrics)
        effective_snapshot = self._apply_live_marketplace_competitors(effective_snapshot, live_research.marketplace_gigs)
        return effective_snapshot, live_research

    def _collect_live_research(
        self,
        snapshot: GigSnapshot,
        *,
        include_marketplace: bool = False,
        marketplace_search_terms: list[str] | None = None,
        marketplace_observer=None,
    ) -> LiveResearchBundle:
        keyword_seeds = self._seed_keywords(snapshot)
        keyword_signals = []
        connector_status = []

        trends_signals, trends_status = self.google_trends.fetch_keyword_signals(keyword_seeds)
        keyword_signals.extend(trends_signals)
        connector_status.append(trends_status)

        semrush_signals, semrush_status = self.semrush.fetch_keyword_signals(keyword_seeds)
        keyword_signals.extend(semrush_signals)
        connector_status.append(semrush_status)

        seller_metrics, fiverr_status = self.fiverr.fetch_seller_metrics()
        connector_status.append(fiverr_status)

        marketplace_gigs = []
        if include_marketplace:
            marketplace_terms = marketplace_search_terms or keyword_seeds[:3]
            marketplace_gigs, marketplace_status = self.marketplace.fetch_competitor_gigs(
                marketplace_terms,
                observer=marketplace_observer,
            )
            connector_status.append(marketplace_status)

        return LiveResearchBundle(
            keyword_signals=self._merge_keyword_signals(keyword_signals),
            seller_metrics=seller_metrics,
            marketplace_gigs=marketplace_gigs,
            connector_status=connector_status,
        )

    def _seed_keywords(self, snapshot: GigSnapshot) -> list[str]:
        candidates = [
            snapshot.niche,
            snapshot.title,
            *snapshot.tags,
            "core web vitals",
            "pagespeed insights",
            "gtmetrix",
        ]
        seeds: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            value = candidate.strip().lower()
            if not value or value in seen:
                continue
            seen.add(value)
            seeds.append(candidate.strip())
        return seeds[:8]

    def _merge_keyword_signals(self, signals):
        merged = {}
        for signal in signals:
            key = (signal.keyword.lower(), signal.source)
            current = merged.get(key)
            if current is None:
                merged[key] = signal
                continue
            if signal.trend_score is not None and (
                current.trend_score is None or signal.trend_score > current.trend_score
            ):
                current.trend_score = signal.trend_score
            if signal.search_volume is not None and (
                current.search_volume is None or signal.search_volume > current.search_volume
            ):
                current.search_volume = signal.search_volume
            if signal.keyword_difficulty is not None and current.keyword_difficulty is None:
                current.keyword_difficulty = signal.keyword_difficulty
            if signal.cpc is not None and current.cpc is None:
                current.cpc = signal.cpc
            if signal.competition is not None and current.competition is None:
                current.competition = signal.competition
            current.rising = current.rising or signal.rising
        return sorted(
            merged.values(),
            key=lambda item: (
                item.rising,
                item.search_volume or 0,
                item.trend_score or 0,
            ),
            reverse=True,
        )

    def _apply_live_metrics(
        self,
        snapshot: GigSnapshot,
        live_metrics: GigAnalytics | None,
    ) -> GigSnapshot:
        if live_metrics is None:
            return snapshot
        merged_analytics = GigAnalytics(
            impressions=live_metrics.impressions or snapshot.analytics.impressions,
            clicks=live_metrics.clicks or snapshot.analytics.clicks,
            orders=live_metrics.orders or snapshot.analytics.orders,
            saves=live_metrics.saves or snapshot.analytics.saves,
            average_response_time_hours=(
                live_metrics.average_response_time_hours
                if live_metrics.average_response_time_hours is not None
                else snapshot.analytics.average_response_time_hours
            ),
            package_mix=snapshot.analytics.package_mix,
        )
        return replace(snapshot, analytics=merged_analytics)

    def _apply_live_marketplace_competitors(
        self,
        snapshot: GigSnapshot,
        marketplace_gigs,
    ) -> GigSnapshot:
        if not marketplace_gigs:
            return snapshot
        live_competitors = [
            CompetitorGig(
                title=gig.title,
                starting_price=gig.starting_price,
                tags=[],
                rating=gig.rating,
                reviews_count=gig.reviews_count,
                description_excerpt=gig.snippet,
            )
            for gig in marketplace_gigs
        ]
        merged: list[CompetitorGig] = []
        seen: set[str] = set()
        for competitor in [*snapshot.competitors, *live_competitors]:
            key = competitor.title.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(competitor)
        return replace(snapshot, competitors=merged)

    def _weekly_action_plan(
        self,
        *,
        niche_pulse,
        content: dict[str, list[str]],
        conversion_actions: list[str],
        pricing_recommendations: list[str],
        review_actions: list[str],
        competitive_actions: list[str],
    ) -> list[str]:
        plan: list[str] = []
        if niche_pulse.competitor_gaps:
            plan.append(
                f"Update the title or tags so at least one gap term like '{niche_pulse.competitor_gaps[0]}' appears in the visible promise."
            )
        if content["description_recommendations"]:
            plan.append(content["description_recommendations"][0])
        if conversion_actions:
            plan.append(conversion_actions[0])
        if pricing_recommendations:
            plan.append(pricing_recommendations[0])
        if review_actions:
            plan.append(review_actions[0])
        if competitive_actions:
            plan.append(competitive_actions[0])
        return plan[:5]

    def _score(self, snapshot: GigSnapshot, niche_pulse, conversion_audit, review_actions: list[str]) -> int:
        title = snapshot.title.lower()
        description = snapshot.description.lower()
        score = 20

        if "wordpress" in title:
            score += 10
        if any(term in title for term in ["speed", "pagespeed", "performance", "core web vitals"]):
            score += 10
        if len(snapshot.tags) >= 4:
            score += 10
        elif snapshot.tags:
            score += 6
        if not niche_pulse.competitor_gaps:
            score += 10
        elif len(niche_pulse.competitor_gaps) <= 2:
            score += 6
        if any(term in description for term in ["pagespeed", "gtmetrix", "core web vitals", "lcp", "cls"]):
            score += 8
        if any(term in description for term in ["sales", "seo", "ranking", "lead", "conversion"]):
            score += 8
        if snapshot.packages:
            score += 8
        if snapshot.reviews and review_actions:
            score += 6
        if conversion_audit.impression_to_click_rate is not None:
            score += 8 if conversion_audit.impression_to_click_rate >= 3 else 4
        if conversion_audit.click_to_order_rate is not None:
            score += 8 if conversion_audit.click_to_order_rate >= 8 else 4

        return max(0, min(100, score))
