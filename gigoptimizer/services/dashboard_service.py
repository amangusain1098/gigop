from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from typing import Any

from ..config import GigOptimizerConfig
from ..models import (
    AgentHealth,
    ApprovalRecord,
    ConnectorStatus,
    GigPackage,
    GigPageOverview,
    GigSnapshot,
    LiveResearchBundle,
    ReviewSnippet,
    DashboardState,
    GeneratedReportFile,
    MarketplaceGig,
    MetricHistoryPoint,
    OptimizationReport,
    ScraperActivityEntry,
    ScraperRunState,
)
from ..orchestrator import GigOptimizerOrchestrator
from ..persistence import BlueprintRepository, DatabaseManager
from ..queue import HITLQueue
from ..validators import HallucinationValidator
from .ai_overview_service import AIOverviewService
from .settings_service import SettingsService


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


AGENT_HEALTH_DEFAULTS = [
    ("Buyer Intelligence", 0.00),
    ("Gig Content Optimizer", 0.00),
    ("Persona Segmentation", 0.00),
    ("CRO", 0.00),
    ("Pricing Intelligence", 0.00),
    ("Review & Social Proof", 0.00),
    ("External Traffic", 0.00),
]


class DashboardService:
    def __init__(
        self,
        config: GigOptimizerConfig | None = None,
        *,
        settings_service: SettingsService | None = None,
        ai_overview_service: AIOverviewService | None = None,
    ) -> None:
        self.config = config or GigOptimizerConfig.from_env()
        self.settings_service = settings_service
        self._ensure_paths()
        self.database_manager = DatabaseManager(self.config)
        self.repository = BlueprintRepository(self.database_manager)
        self.orchestrator = GigOptimizerOrchestrator(config=self.config)
        self.queue = HITLQueue(self.config.approval_queue_db_path)
        self.validator = HallucinationValidator()
        self.ai_overview_service = ai_overview_service or (
            AIOverviewService(self.settings_service) if self.settings_service is not None else None
        )
        self._initialize_files()
        self._bootstrap_repository()

    def get_state(self) -> dict[str, Any]:
        state = self._load_dashboard_state()
        if state.latest_report is None:
            self.run_pipeline(use_live_connectors=False)
            state = self._load_dashboard_state()
        return {
            "snapshot_path": state.snapshot_path,
            "latest_report": state.latest_report,
            "gig_comparison": state.gig_comparison,
            "comparison_history": state.comparison_history,
            "metrics_history": [asdict(item) for item in state.metrics_history],
            "agent_health": [asdict(item) for item in state.agent_health],
            "recent_reports": [asdict(item) for item in state.recent_reports],
            "scraper_run": asdict(state.scraper_run),
            "queue": [asdict(item) for item in self.queue.list_records()],
            "connector_status": (state.latest_report or {}).get("connector_status", []),
            "setup_health": self._build_setup_health(),
        }

    def get_scraper_run_state(self) -> dict[str, Any]:
        state = self._load_dashboard_state()
        return asdict(state.scraper_run)

    def compare_my_gig_to_market(
        self,
        *,
        gig_url: str,
        search_terms: list[str] | None = None,
        scraper_event_callback=None,
        progress_callback=None,
    ) -> dict[str, Any]:
        snapshot = self._load_snapshot()
        settings_marketplace = self.settings_service.get_settings().marketplace if self.settings_service else None
        if settings_marketplace is not None:
            self._apply_marketplace_runtime_settings(settings_marketplace)

        target_url = gig_url.strip() or (
            settings_marketplace.my_gig_url if settings_marketplace is not None else ""
        )
        if not target_url:
            self._save_gig_comparison(
                {
                    "status": "warning",
                    "message": "Provide your Fiverr gig URL to compare it against the market.",
                    "gig_url": "",
                    "my_gig": None,
                    "detected_search_terms": [],
                    "top_search_titles": [],
                    "title_patterns": [],
                    "market_anchor_price": None,
                    "competitor_count": 0,
                    "what_to_implement": [],
                    "why_competitors_win": [],
                    "my_advantages": [],
                    "top_competitors": [],
                }
            )
            return self.get_state()

        self._save_gig_comparison(
            {
                "status": "running",
                "message": "Opening your gig and comparing it against the live Fiverr market.",
                "gig_url": target_url,
                "my_gig": None,
                "detected_search_terms": [],
                "top_search_titles": [],
                "title_patterns": [],
                "market_anchor_price": None,
                "competitor_count": 0,
                "what_to_implement": [],
                "why_competitors_win": [],
                "my_advantages": [],
                "top_competitors": [],
                "comparison_source": "live",
            }
        )
        self._start_scraper_run(
            [target_url],
            status="comparing_gig",
            message="Loading your Fiverr gig and scanning the surrounding market.",
        )
        if scraper_event_callback is not None:
            scraper_event_callback(self.get_scraper_run_state())

        my_gig, gig_status = self.orchestrator.marketplace.fetch_gig_page_overview(
            target_url,
            observer=lambda event: self._record_scraper_event(event, scraper_event_callback),
        )
        if my_gig is None:
            my_gig = self._fallback_gig_overview_from_url(
                gig_url=target_url,
                snapshot=snapshot,
            )
            self._record_scraper_event(
                {
                    "stage": "my_gig_fallback",
                    "level": "warning",
                    "term": ", ".join(search_terms or []),
                    "url": target_url,
                    "message": (
                        f"{gig_status.detail} GigOptimizer is using a URL-derived fallback profile so the market comparison can still continue."
                    ),
                },
                scraper_event_callback,
            )
            comparison_message_prefix = (
                f"{gig_status.detail} GigOptimizer used a URL-derived fallback profile for your gig so the comparison could continue."
            )
        else:
            comparison_message_prefix = ""

        derived_terms = search_terms or self._derive_gig_search_terms(my_gig, snapshot)
        self._record_scraper_event(
            {
                "stage": "comparison_terms",
                "term": ", ".join(derived_terms),
                "url": my_gig.url,
                "message": f"Derived live comparison terms from your gig: {', '.join(derived_terms)}",
            },
            scraper_event_callback,
        )

        competitor_gigs, market_status = self.orchestrator.marketplace.fetch_competitor_gigs(
            derived_terms,
            observer=lambda event: self._record_scraper_event(event, scraper_event_callback),
        )
        if not competitor_gigs and market_status.status in {"warning", "skipped", "error"}:
            competitor_gigs, market_status = self.orchestrator.serpapi.fetch_fiverr_marketplace_gigs(
                derived_terms,
                gig_page_lookup=self.orchestrator.marketplace.fetch_gig_page_overview_http,
                observer=lambda event: self._record_scraper_event(event, scraper_event_callback),
            )
        if not competitor_gigs:
            competitor_gigs = self._snapshot_marketplace_gigs(snapshot, derived_terms)
            if competitor_gigs:
                market_status = ConnectorStatus(
                    connector="marketplace_fallback",
                    status="partial",
                    detail="Live Fiverr competitor scraping was blocked, so GigOptimizer used the local benchmark set to keep the optimization plan available.",
                )
        comparison_snapshot = self._build_snapshot_from_gig(my_gig, snapshot)
        analysis = (
            self.orchestrator.competitive_analysis.analyze(comparison_snapshot, competitor_gigs)
            if competitor_gigs
            else None
        )
        comparison = self._build_market_comparison(
            my_gig=my_gig,
            base_snapshot=snapshot,
            comparison_snapshot=comparison_snapshot,
            derived_terms=derived_terms,
            competitor_gigs=competitor_gigs,
            analysis=analysis,
            status=("partial" if comparison_message_prefix and market_status.status == "ok" else market_status.status),
            message=(
                (
                    f"{comparison_message_prefix} Compared your gig against {len(competitor_gigs)} public Fiverr gigs in the same niche."
                    if comparison_message_prefix
                    else f"Compared your gig against {len(competitor_gigs)} public Fiverr gigs in the same niche."
                )
                if competitor_gigs
                else (f"{comparison_message_prefix} {market_status.detail}".strip())
            ),
            comparison_source="live" if not comparison_message_prefix else "live_fallback",
            progress_callback=progress_callback,
        )
        self._save_gig_comparison(comparison)
        self._create_market_comparison_drafts(comparison_snapshot, comparison)

        state = self._load_dashboard_state()
        latest_report = dict(state.latest_report or {})
        latest_report["competitive_gap_analysis"] = asdict(analysis) if analysis is not None else None
        state.latest_report = latest_report
        self._save_dashboard_state(state)

        self._finalize_scraper_run(
            status=market_status.status,
            gigs=competitor_gigs,
            message=comparison["message"],
        )
        if scraper_event_callback is not None:
            scraper_event_callback(self.get_scraper_run_state())
        return self.get_state()

    def compare_manual_market_input(
        self,
        *,
        gig_url: str,
        competitor_input: str,
        search_terms: list[str] | None = None,
        scraper_event_callback=None,
        progress_callback=None,
    ) -> dict[str, Any]:
        snapshot = self._load_snapshot()
        settings_marketplace = self.settings_service.get_settings().marketplace if self.settings_service else None
        if settings_marketplace is not None:
            self._apply_marketplace_runtime_settings(settings_marketplace)

        target_url = gig_url.strip() or (
            settings_marketplace.my_gig_url if settings_marketplace is not None else ""
        )
        manual_competitors = self._parse_manual_competitors(
            competitor_input,
            matched_term=(search_terms or [snapshot.niche])[0] if (search_terms or [snapshot.niche]) else "",
        )
        if not manual_competitors:
            self._save_gig_comparison(
                {
                    "status": "warning",
                    "message": "Paste at least one competitor line before running manual market comparison.",
                    "gig_url": target_url,
                    "my_gig": None,
                    "detected_search_terms": search_terms or [],
                    "top_search_titles": [],
                    "title_patterns": [],
                    "market_anchor_price": None,
                    "competitor_count": 0,
                    "what_to_implement": [],
                    "why_competitors_win": [],
                    "my_advantages": [],
                    "top_competitors": [],
                    "comparison_source": "manual",
                }
            )
            return self.get_state()

        self._save_gig_comparison(
            {
                "status": "running",
                "message": "Building a market comparison from your pasted competitor input.",
                "gig_url": target_url,
                "my_gig": None,
                "detected_search_terms": search_terms or [],
                "top_search_titles": [],
                "title_patterns": [],
                "market_anchor_price": None,
                "competitor_count": len(manual_competitors),
                "what_to_implement": [],
                "why_competitors_win": [],
                "my_advantages": [],
                "top_competitors": [],
                "comparison_source": "manual",
            }
        )
        if scraper_event_callback is not None:
            scraper_event_callback(self.get_scraper_run_state())

        my_gig: GigPageOverview
        if target_url:
            live_gig, status = self.orchestrator.marketplace.fetch_gig_page_overview(
                target_url,
                observer=lambda event: self._record_scraper_event(event, scraper_event_callback),
            )
            if live_gig is not None:
                my_gig = live_gig
                detail = "Loaded your gig URL and combined it with your pasted competitor lines."
            else:
                my_gig = self._snapshot_gig_overview(snapshot, target_url)
                detail = f"{status.detail} Used your local snapshot as the 'my gig' baseline instead."
        else:
            my_gig = self._snapshot_gig_overview(snapshot, target_url)
            detail = "Used your local snapshot as the 'my gig' baseline because no public gig URL was provided."

        derived_terms = search_terms or self._derive_gig_search_terms(my_gig, snapshot)
        comparison_snapshot = self._build_snapshot_from_gig(my_gig, snapshot)
        analysis = self.orchestrator.competitive_analysis.analyze(
            comparison_snapshot,
            manual_competitors,
        )
        comparison = self._build_market_comparison(
            my_gig=my_gig,
            base_snapshot=snapshot,
            comparison_snapshot=comparison_snapshot,
            derived_terms=derived_terms,
            competitor_gigs=manual_competitors,
            analysis=analysis,
            status="ok" if analysis is not None else "warning",
            message=detail,
            comparison_source="manual",
            progress_callback=progress_callback,
        )
        self._save_gig_comparison(comparison)
        self._create_market_comparison_drafts(comparison_snapshot, comparison)

        state = self._load_dashboard_state()
        latest_report = dict(state.latest_report or {})
        latest_report["competitive_gap_analysis"] = asdict(analysis) if analysis is not None else None
        state.latest_report = latest_report
        self._save_dashboard_state(state)
        return self.get_state()

    def run_pipeline(
        self,
        *,
        use_live_connectors: bool,
        scraper_event_callback=None,
        progress_callback=None,
    ) -> dict[str, Any]:
        snapshot = self._load_snapshot()
        started_at = utc_now_iso()
        try:
            marketplace_settings = self.settings_service.get_settings().marketplace if self.settings_service else None
            if marketplace_settings is not None:
                self._apply_marketplace_runtime_settings(marketplace_settings)
            include_marketplace = bool(
                use_live_connectors
                and (
                    (marketplace_settings.enabled and marketplace_settings.search_terms)
                    if marketplace_settings is not None
                    else self.config.marketplace_enabled
                )
            )
            search_terms = (
                marketplace_settings.search_terms
                if marketplace_settings is not None and marketplace_settings.search_terms
                else self._default_marketplace_terms(snapshot)
            )
            if include_marketplace:
                self._start_scraper_run(search_terms)
                if scraper_event_callback is not None:
                    scraper_event_callback(self.get_scraper_run_state())
            live_snapshot, live_research = self.orchestrator.prepare_run(
                snapshot,
                use_live_connectors=use_live_connectors,
                include_marketplace=include_marketplace,
                marketplace_search_terms=search_terms,
                marketplace_observer=(
                    (lambda event: self._record_scraper_event(event, scraper_event_callback))
                    if include_marketplace
                    else None
                ),
            )
            report = self.orchestrator.optimize_prepared(
                live_snapshot,
                live_research,
                progress_callback=progress_callback,
            )
            if self.ai_overview_service is not None:
                report.ai_overview = self.ai_overview_service.generate_overview(report=report.to_dict())
            self._append_metric_history(live_snapshot, report)
            self._update_agent_health(status="ok", last_run_at=started_at)
            self._save_latest_report(report)
            if include_marketplace:
                self._finalize_scraper_run(
                    status="ok",
                    gigs=live_research.marketplace_gigs,
                    message=f"Live marketplace scrape finished with {len(live_research.marketplace_gigs)} unique gigs.",
                )
                if scraper_event_callback is not None:
                    scraper_event_callback(self.get_scraper_run_state())
            self._create_action_drafts(snapshot, report)
        except Exception as exc:
            if use_live_connectors:
                self._finalize_scraper_run(status="error", gigs=[], message=str(exc))
                if scraper_event_callback is not None:
                    scraper_event_callback(self.get_scraper_run_state())
            self._update_agent_health(status="error", last_run_at=started_at, last_error=str(exc))
            raise
        return self.get_state()

    def run_marketplace_scrape(
        self,
        *,
        search_terms: list[str] | None = None,
        scraper_event_callback=None,
    ) -> dict[str, Any]:
        snapshot = self._load_snapshot()
        settings_marketplace = self.settings_service.get_settings().marketplace if self.settings_service else None
        if settings_marketplace is not None:
            self._apply_marketplace_runtime_settings(settings_marketplace)
        terms = search_terms or (
            settings_marketplace.search_terms
            if settings_marketplace is not None and settings_marketplace.search_terms
            else self._default_marketplace_terms(snapshot)
        )
        self._start_scraper_run(terms)
        if scraper_event_callback is not None:
            scraper_event_callback(self.get_scraper_run_state())

        gigs, status = self.orchestrator.marketplace.fetch_competitor_gigs(
            terms,
            observer=lambda event: self._record_scraper_event(event, scraper_event_callback),
        )
        if not gigs and status.status in {"warning", "skipped", "error"}:
            gigs, status = self.orchestrator.serpapi.fetch_fiverr_marketplace_gigs(
                terms,
                gig_page_lookup=self.orchestrator.marketplace.fetch_gig_page_overview_http,
                observer=lambda event: self._record_scraper_event(event, scraper_event_callback),
            )
        self._apply_marketplace_results(snapshot=snapshot, gigs=gigs, status=status)
        self._finalize_scraper_run(
            status=status.status,
            gigs=gigs,
            message=status.detail,
        )
        if scraper_event_callback is not None:
            scraper_event_callback(self.get_scraper_run_state())
        return self.get_state()

    def run_marketplace_verification(
        self,
        *,
        search_terms: list[str] | None = None,
        scraper_event_callback=None,
    ) -> dict[str, Any]:
        snapshot = self._load_snapshot()
        settings_marketplace = self.settings_service.get_settings().marketplace if self.settings_service else None
        if settings_marketplace is not None:
            self._apply_marketplace_runtime_settings(settings_marketplace)
        terms = search_terms or (
            settings_marketplace.search_terms
            if settings_marketplace is not None and settings_marketplace.search_terms
            else self._default_marketplace_terms(snapshot)
        )
        term = terms[0] if terms else ""
        self._start_scraper_run(
            terms,
            status="verification_pending",
            message="Waiting for manual Fiverr verification in the persistent browser profile.",
        )
        if scraper_event_callback is not None:
            scraper_event_callback(self.get_scraper_run_state())

        gigs, status = self.orchestrator.marketplace.verify_and_fetch_competitor_gigs(
            terms,
            observer=lambda event: self._record_scraper_event(event, scraper_event_callback),
        )
        if status.status != "ok":
            self._finalize_scraper_run(status=status.status, gigs=gigs, message=status.detail)
            if scraper_event_callback is not None:
                scraper_event_callback(self.get_scraper_run_state())
            return self.get_state()
        self._apply_marketplace_results(snapshot=snapshot, gigs=gigs, status=status)
        self._finalize_scraper_run(status=status.status, gigs=gigs, message=status.detail)
        if scraper_event_callback is not None:
            scraper_event_callback(self.get_scraper_run_state())
        return self.get_state()

    def apply_keyword(self, keyword: str) -> dict[str, Any]:
        snapshot = self._load_snapshot()
        cleaned = keyword.strip()
        if not cleaned:
            return self.get_state()
        proposed_tags = list(dict.fromkeys([*snapshot.tags, cleaned]))
        record = self._create_queue_record(
            agent_name="Buyer Intelligence",
            action_type="keyword_tag_update",
            current_value=json.dumps(snapshot.tags),
            proposed_value=json.dumps(proposed_tags),
            validation_text=" | ".join(proposed_tags),
        )
        if record.status in {"auto_approved", "approved"}:
            self._apply_record(record)
        return self.get_state()

    def approve_record(self, record_id: str, reviewer_notes: str = "") -> dict[str, Any]:
        record = self._get_record_or_raise(record_id)
        self._apply_record(record)
        self.queue.update_status(record_id, status="approved", reviewer_notes=reviewer_notes)
        self.repository.upsert_hitl_item(self._get_record_or_raise(record_id))
        return self.run_pipeline(use_live_connectors=False)

    def reject_record(self, record_id: str, reviewer_notes: str = "") -> dict[str, Any]:
        self.queue.update_status(record_id, status="rejected", reviewer_notes=reviewer_notes)
        self.repository.upsert_hitl_item(self._get_record_or_raise(record_id))
        return self.get_state()

    def register_report(self, report_file: GeneratedReportFile) -> None:
        state = self._load_dashboard_state()
        reports = [report_file, *state.recent_reports]
        state.recent_reports = reports[:12]
        self._save_dashboard_state(state)

    def queue_market_recommendation(
        self,
        *,
        action_type: str,
        proposed_value,
    ) -> dict[str, Any]:
        snapshot = self._load_snapshot()
        normalized_action = str(action_type or "").strip()
        if normalized_action == "title_update":
            value = str(proposed_value or "").strip()
            if not value:
                return self.get_state()
            record = self._create_queue_record(
                agent_name="Gig Content Optimizer",
                action_type="title_update",
                current_value=snapshot.title,
                proposed_value=value,
                validation_text=value,
            )
            if record.status in {"approved", "auto_approved"}:
                self._apply_record(record)
        elif normalized_action == "description_update":
            value = str(proposed_value or "").strip()
            if not value:
                return self.get_state()
            record = self._create_queue_record(
                agent_name="Gig Content Optimizer",
                action_type="description_update",
                current_value=snapshot.description,
                proposed_value=value,
                validation_text=value,
            )
            if record.status in {"approved", "auto_approved"}:
                self._apply_record(record)
        elif normalized_action == "keyword_tag_update":
            items = proposed_value if isinstance(proposed_value, list) else self._parse_list_text(str(proposed_value or ""))
            cleaned_items = [item for item in items if item]
            if not cleaned_items:
                return self.get_state()
            record = self._create_queue_record(
                agent_name="Buyer Intelligence",
                action_type="keyword_tag_update",
                current_value=json.dumps(snapshot.tags),
                proposed_value=json.dumps(cleaned_items),
                validation_text=" | ".join(cleaned_items),
            )
            if record.status in {"approved", "auto_approved"}:
                self._apply_record(record)
        else:
            return self.get_state()
        return self.get_state()

    def _ensure_paths(self) -> None:
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        self.config.reports_dir.mkdir(parents=True, exist_ok=True)
        self.config.dashboard_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.metrics_history_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.agent_health_path.parent.mkdir(parents=True, exist_ok=True)
        self.config.integration_settings_path.parent.mkdir(parents=True, exist_ok=True)

    def _initialize_files(self) -> None:
        if not self.config.dashboard_state_path.exists():
            initial_state = DashboardState(
                snapshot_path=str(self.config.default_snapshot_path),
                latest_report=None,
                metrics_history=[],
                agent_health=self._default_agent_health(),
                recent_reports=[],
                scraper_run=ScraperRunState(),
                gig_comparison=None,
                comparison_history=[],
            )
            self._save_dashboard_state(initial_state)
        if not self.config.metrics_history_path.exists():
            self.config.metrics_history_path.write_text("[]", encoding="utf-8")
        if not self.config.agent_health_path.exists():
            self._save_agent_health(self._default_agent_health())

    def _bootstrap_repository(self) -> None:
        existing = self.repository.load_primary_state()
        if existing:
            return
        self._sync_repository_state(self._load_dashboard_state())

    def _default_agent_health(self) -> list[AgentHealth]:
        return [
            AgentHealth(agent_name=name, status="idle", cost_per_run=cost)
            for name, cost in AGENT_HEALTH_DEFAULTS
        ]

    def _load_snapshot(self) -> GigSnapshot:
        payload = json.loads(self.config.default_snapshot_path.read_text(encoding="utf-8"))
        return GigSnapshot.from_dict(payload)

    def _save_snapshot(self, snapshot: GigSnapshot) -> None:
        payload = {
            "niche": snapshot.niche,
            "title": snapshot.title,
            "description": snapshot.description,
            "tags": snapshot.tags,
            "faq": [asdict(item) for item in snapshot.faq],
            "packages": [asdict(item) for item in snapshot.packages],
            "analytics": asdict(snapshot.analytics),
            "competitors": [asdict(item) for item in snapshot.competitors],
            "reviews": [asdict(item) for item in snapshot.reviews],
            "buyer_messages": snapshot.buyer_messages,
            "goals": snapshot.goals,
        }
        self._write_json_atomic(self.config.default_snapshot_path, payload)

    def _append_metric_history(self, snapshot: GigSnapshot, report: OptimizationReport) -> None:
        analytics = snapshot.analytics
        point = MetricHistoryPoint(
            timestamp=utc_now_iso(),
            impressions=analytics.impressions,
            clicks=analytics.clicks,
            orders=analytics.orders,
            ctr=report.conversion_audit.impression_to_click_rate or 0.0,
            conversion_rate=report.conversion_audit.click_to_order_rate or 0.0,
        )
        history = self._load_metric_history()
        history.append(point)
        history = history[-50:]
        self._write_json_atomic(self.config.metrics_history_path, [asdict(item) for item in history])

    def _load_metric_history(self) -> list[MetricHistoryPoint]:
        raw = self._read_json_with_recovery(self.config.metrics_history_path, default=[])
        return [MetricHistoryPoint(**item) for item in raw]

    def _update_agent_health(self, *, status: str, last_run_at: str, last_error: str = "") -> None:
        health = self._load_agent_health()
        for item in health:
            item.status = status
            item.last_run_at = last_run_at
            item.last_error = last_error
        self._save_agent_health(health)

    def _load_agent_health(self) -> list[AgentHealth]:
        raw = self._read_json_with_recovery(self.config.agent_health_path, default=[])
        return [AgentHealth(**item) for item in raw]

    def _save_agent_health(self, health: list[AgentHealth]) -> None:
        self._write_json_atomic(self.config.agent_health_path, [asdict(item) for item in health])

    def _save_latest_report(self, report: OptimizationReport) -> None:
        state = self._load_dashboard_state()
        state.latest_report = report.to_dict()
        state.metrics_history = self._load_metric_history()
        state.agent_health = self._load_agent_health()
        self._save_dashboard_state(state)

    def _load_dashboard_state(self) -> DashboardState:
        default_state = asdict(
            DashboardState(
                snapshot_path=str(self.config.default_snapshot_path),
                latest_report=None,
                metrics_history=[],
                agent_health=self._default_agent_health(),
                recent_reports=[],
                scraper_run=ScraperRunState(),
                gig_comparison=None,
                comparison_history=[],
            )
        )
        raw = self.repository.load_primary_state() or self._read_json_with_recovery(
            self.config.dashboard_state_path,
            default=default_state,
        )
        metrics_history = [MetricHistoryPoint(**item) for item in raw.get("metrics_history", [])]
        agent_health = [AgentHealth(**item) for item in raw.get("agent_health", [])]
        recent_reports = [GeneratedReportFile(**item) for item in raw.get("recent_reports", [])]
        scraper_raw = raw.get("scraper_run", {}) or {}
        recent_events = [
            ScraperActivityEntry(**item) for item in scraper_raw.get("recent_events", [])
        ]
        recent_gigs = [
            MarketplaceGig(**item) for item in scraper_raw.get("recent_gigs", [])
        ]
        return DashboardState(
            snapshot_path=raw.get("snapshot_path", str(self.config.default_snapshot_path)),
            latest_report=raw.get("latest_report"),
            metrics_history=metrics_history,
            agent_health=agent_health,
            recent_reports=recent_reports,
            scraper_run=ScraperRunState(
                status=scraper_raw.get("status", "idle"),
                started_at=scraper_raw.get("started_at", ""),
                finished_at=scraper_raw.get("finished_at", ""),
                search_terms=list(scraper_raw.get("search_terms", [])),
                last_url=scraper_raw.get("last_url", ""),
                total_results=int(scraper_raw.get("total_results", 0) or 0),
                last_status_message=scraper_raw.get("last_status_message", ""),
                debug_html_path=scraper_raw.get("debug_html_path", ""),
                debug_screenshot_path=scraper_raw.get("debug_screenshot_path", ""),
                recent_events=recent_events,
                recent_gigs=recent_gigs,
            ),
            gig_comparison=raw.get("gig_comparison"),
            comparison_history=list(raw.get("comparison_history", []) or []),
        )

    def _save_dashboard_state(self, state: DashboardState) -> None:
        self._write_json_atomic(self.config.dashboard_state_path, asdict(state))
        self._sync_repository_state(state)

    def _sync_repository_state(self, state: DashboardState) -> None:
        self.repository.save_primary_state(
            asdict(state),
            snapshot_payload=asdict(self._load_snapshot()),
        )
        self.repository.sync_hitl_items(self.queue.list_records())
        self.repository.replace_competitor_snapshots(
            gigs=self._comparison_competitors(state.gig_comparison),
            source=(state.gig_comparison or {}).get("comparison_source", "dashboard_state"),
        )

    def _build_setup_health(self) -> dict[str, Any]:
        connector_status = [asdict(item) for item in self.config.validate_credentials()]
        notifications = self.settings_service.get_public_settings() if self.settings_service is not None else {}
        marketplace = notifications.get("marketplace", {})
        email = notifications.get("email", {})
        slack = notifications.get("slack", {})
        whatsapp = notifications.get("whatsapp", {})
        ai = notifications.get("ai", {})
        checks = [
            {
                "label": "Marketplace Compare",
                "status": "ready" if marketplace.get("my_gig_url") else "needs_input",
                "detail": "Your Fiverr gig URL is configured." if marketplace.get("my_gig_url") else "Add your Fiverr gig URL so the app can compare you against the market.",
            },
            {
                "label": "Auto Market Watch",
                "status": "ready" if marketplace.get("auto_compare_enabled") else "optional",
                "detail": (
                    f"Auto-compare runs every {marketplace.get('auto_compare_interval_minutes', 5)} minutes."
                    if marketplace.get("auto_compare_enabled")
                    else "Enable auto-compare to keep the market watch updating on its own."
                ),
            },
            {
                "label": "Email Alerts",
                "status": "ready" if email.get("configured") else "optional",
                "detail": "Email delivery is configured." if email.get("configured") else "Add SMTP settings if you want report and error alerts by email.",
            },
            {
                "label": "Slack Alerts",
                "status": "ready" if slack.get("configured") else "optional",
                "detail": "Slack webhook is configured." if slack.get("configured") else "Add a Slack webhook if you want live pipeline and report alerts.",
            },
            {
                "label": "WhatsApp Alerts",
                "status": "ready" if whatsapp.get("configured") else "optional",
                "detail": "WhatsApp Cloud API is configured." if whatsapp.get("configured") else "Add WhatsApp Cloud API settings if you want phone alerts.",
            },
            {
                "label": "AI Overview",
                "status": "ready" if ai.get("configured") else "fallback",
                "detail": "External AI overview is configured." if ai.get("configured") else "The app will use local fallback summaries until you add an AI API key.",
            },
        ]
        return {
            "connectors": connector_status,
            "checks": checks,
        }

    def _build_market_comparison(
        self,
        *,
        my_gig: GigPageOverview,
        base_snapshot: GigSnapshot,
        comparison_snapshot: GigSnapshot,
        derived_terms: list[str],
        competitor_gigs: list[MarketplaceGig],
        analysis,
        status: str,
        message: str,
        comparison_source: str,
        progress_callback=None,
    ) -> dict[str, Any]:
        optimization_report = self.orchestrator.optimize_prepared(
            comparison_snapshot,
            LiveResearchBundle(marketplace_gigs=competitor_gigs),
            progress_callback=progress_callback,
        )
        implementation_blueprint = self._build_implementation_blueprint(
            my_gig=my_gig,
            base_snapshot=base_snapshot,
            derived_terms=derived_terms,
            competitor_gigs=competitor_gigs,
            analysis=analysis,
            optimization_report=optimization_report,
        )
        return {
            "status": status,
            "message": message,
            "gig_url": my_gig.url,
            "my_gig": asdict(my_gig),
            "detected_search_terms": derived_terms,
            "top_search_titles": [gig.title for gig in (analysis.top_competitors if analysis else competitor_gigs[:5])],
            "title_patterns": analysis.title_patterns if analysis else [],
            "market_anchor_price": self._market_anchor_price(competitor_gigs),
            "competitor_count": len(competitor_gigs),
            "what_to_implement": analysis.what_to_implement if analysis else [],
            "why_competitors_win": analysis.why_competitors_win if analysis else [],
            "my_advantages": analysis.my_advantages if analysis else [],
            "top_competitors": [asdict(gig) for gig in (analysis.top_competitors if analysis else competitor_gigs[:5])],
            "comparison_source": comparison_source,
            "implementation_blueprint": implementation_blueprint,
            "implementation_summary": self._implementation_summary(implementation_blueprint),
            "last_compared_at": utc_now_iso(),
        }

    def _comparison_competitors(self, comparison: dict[str, Any] | None) -> list[MarketplaceGig]:
        competitors: list[MarketplaceGig] = []
        for item in (comparison or {}).get("top_competitors", []):
            if not isinstance(item, dict):
                continue
            try:
                competitors.append(MarketplaceGig(**item))
            except TypeError:
                continue
        return competitors

    def _build_implementation_blueprint(
        self,
        *,
        my_gig: GigPageOverview,
        base_snapshot: GigSnapshot,
        derived_terms: list[str],
        competitor_gigs: list[MarketplaceGig],
        analysis,
        optimization_report: OptimizationReport,
    ) -> dict[str, Any]:
        title_patterns = analysis.title_patterns if analysis else []
        recommended_title = self._select_market_ready_title(
            optimization_report.title_variants,
            title_patterns=title_patterns,
            derived_terms=derived_terms,
        )
        recommended_tags = self._recommended_market_tags(
            current_tags=my_gig.tags or base_snapshot.tags,
            title_patterns=title_patterns,
            derived_terms=derived_terms,
            tag_recommendations=optimization_report.tag_recommendations,
        )
        title_options = self._build_title_options(
            title_variants=optimization_report.title_variants,
            title_patterns=title_patterns,
            derived_terms=derived_terms,
        )
        description_pack = self._build_description_pack(
            recommended_title=recommended_title,
            my_gig=my_gig,
            derived_terms=derived_terms,
            title_patterns=title_patterns,
            optimization_report=optimization_report,
            analysis=analysis,
        )
        description_options = self._build_description_options(
            title_options=title_options,
            my_gig=my_gig,
            optimization_report=optimization_report,
            derived_terms=derived_terms,
            title_patterns=title_patterns,
        )
        return {
            "recommended_title": recommended_title,
            "title_variants": optimization_report.title_variants[:5],
            "title_options": title_options,
            "recommended_tags": recommended_tags,
            "description_opening": description_pack["opening"],
            "description_blueprint": description_pack["blueprint"],
            "description_full": description_pack["full_text"],
            "description_options": description_options,
            "faq_recommendations": optimization_report.faq_recommendations[:5],
            "pricing_strategy": self._market_pricing_strategy(
                current_price=my_gig.starting_price,
                market_anchor_price=self._market_anchor_price(competitor_gigs),
                fallback=optimization_report.pricing_recommendations,
            ),
            "recommended_packages": self._recommended_packages(
                market_anchor_price=self._market_anchor_price(competitor_gigs),
                current_price=my_gig.starting_price,
            ),
            "trust_boosters": self._trust_boosters(analysis, optimization_report),
            "weekly_actions": optimization_report.weekly_action_plan[:5],
            "review_actions": optimization_report.review_actions[:4],
            "review_follow_up_template": optimization_report.review_follow_up_template,
            "external_traffic_actions": optimization_report.external_traffic_actions[:4],
            "persona_focus": [
                {
                    "persona": insight.persona,
                    "score": round(insight.score, 1),
                    "pain_point": insight.pain_point,
                    "emphasis": insight.emphasis,
                }
                for insight in optimization_report.persona_insights[:3]
            ],
            "caution_notes": optimization_report.caution_notes[:3],
        }

    def _select_market_ready_title(
        self,
        title_variants: list[str],
        *,
        title_patterns: list[str],
        derived_terms: list[str],
    ) -> str:
        candidates = title_variants or ["I will optimize WordPress speed and improve Core Web Vitals"]
        preferred_phrases = self._prioritized_market_phrases(title_patterns=title_patterns, derived_terms=derived_terms)
        best_title = candidates[0]
        best_score = -1
        for candidate in candidates:
            lowered = candidate.lower()
            score = sum(4 for pattern in title_patterns if pattern and pattern.lower() in lowered)
            score += sum(2 for term in derived_terms if term and term.lower() in lowered)
            score += sum(3 for phrase in preferred_phrases[:3] if phrase and phrase.lower() in lowered)
            if "wordpress" in lowered:
                score += 1
            if "pagespeed" in lowered or "page speed" in lowered:
                score += 1
            if score > best_score:
                best_score = score
                best_title = candidate
        if best_score <= 0 and preferred_phrases:
            primary_term = preferred_phrases[0]
            return f"I will optimize WordPress speed and improve {primary_term.title()}"
        return best_title

    def _build_title_options(
        self,
        *,
        title_variants: list[str],
        title_patterns: list[str],
        derived_terms: list[str],
    ) -> list[dict[str, str]]:
        labels = [
            ("Search Match", "Best for exact-match visibility against current market phrases."),
            ("Trust Builder", "Best for stronger buyer confidence and before-and-after framing."),
            ("Store Focus", "Best if you want to attract WooCommerce buyers and revenue-minded clients."),
        ]
        fallback_titles = [
            "I will fix WordPress page speed and Core Web Vitals",
            "I will speed up your WordPress site and improve PageSpeed Insights",
            "I will optimize WooCommerce speed and improve checkout performance",
        ]
        candidates = title_variants[:]
        while len(candidates) < 3:
            candidates.append(fallback_titles[len(candidates)])
        preferred_phrases = self._prioritized_market_phrases(title_patterns=title_patterns, derived_terms=derived_terms)
        primary_phrase = preferred_phrases[0] if preferred_phrases else "PageSpeed Insights"
        secondary_phrase = preferred_phrases[1] if len(preferred_phrases) > 1 else "Core Web Vitals"

        options: list[dict[str, str]] = []
        for index, (label, rationale) in enumerate(labels):
            title = candidates[index]
            if label == "Search Match" and primary_phrase.lower() not in title.lower():
                title = f"I will optimize WordPress speed and improve {primary_phrase.title()}"
            if label == "Trust Builder" and secondary_phrase.lower() not in title.lower():
                title = f"I will optimize WordPress speed, {secondary_phrase.lower()}, and GTmetrix results"
            if label == "Store Focus" and not any("woocommerce" in item.lower() for item in [title, *derived_terms, *title_patterns]):
                title = "I will optimize WooCommerce speed and improve Core Web Vitals"
            options.append(
                {
                    "label": label,
                    "title": title,
                    "rationale": rationale,
                }
            )
        return options

    def _market_pricing_strategy(
        self,
        *,
        current_price: float | None,
        market_anchor_price: float | None,
        fallback: list[str],
    ) -> list[str]:
        if current_price is None or market_anchor_price is None:
            return fallback[:4]

        recommendations: list[str] = []
        if current_price > market_anchor_price * 1.15:
            recommendations.append(
                f"Your visible starting price is above the live market anchor of about ${market_anchor_price:.0f}; justify it with stronger proof, clearer deliverables, or a tighter premium angle."
            )
        elif current_price < market_anchor_price * 0.8:
            recommendations.append(
                f"Your visible starting price is below the live market anchor of about ${market_anchor_price:.0f}; raise the floor or narrow the scope so it still reads as expert work."
            )
        else:
            recommendations.append(
                f"Your visible starting price sits close to the live market anchor of about ${market_anchor_price:.0f}; compete on proof and clarity instead of discounting."
            )

        recommendations.append("Use the Standard package as the value anchor by bundling fixes with a before-and-after verification report.")
        recommendations.append("Give Premium a stronger reason to exist, such as rush delivery, WooCommerce focus, or post-fix monitoring.")
        return self._dedupe_strings(recommendations)[:4]

    def _recommended_market_tags(
        self,
        *,
        current_tags: list[str],
        title_patterns: list[str],
        derived_terms: list[str],
        tag_recommendations: list[str],
    ) -> list[str]:
        candidates = [*title_patterns, *tag_recommendations, *derived_terms, *current_tags]
        tags: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            cleaned = re.sub(r"\s+", " ", str(candidate or "").strip())
            if not cleaned or len(cleaned) > 20:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            tags.append(cleaned)
        return tags[:5]

    def _build_description_pack(
        self,
        *,
        recommended_title: str,
        my_gig: GigPageOverview,
        derived_terms: list[str],
        title_patterns: list[str],
        optimization_report: OptimizationReport,
        analysis,
    ) -> dict[str, Any]:
        preferred_phrases = self._prioritized_market_phrases(title_patterns=title_patterns, derived_terms=derived_terms)
        keyword_primary = preferred_phrases[0] if preferred_phrases else "PageSpeed Insights"
        keyword_secondary = preferred_phrases[1] if len(preferred_phrases) > 1 else "Core Web Vitals"
        hook = (
            f"Need a faster WordPress site with stronger {keyword_primary.title()} and {keyword_secondary.title()} results? "
            f"I will audit and optimize the issues slowing your site so you can improve speed, user experience, and conversions."
        )
        blueprint = [
            hook,
            "Lead with the business impact: explain that slow WordPress pages hurt rankings, leads, and checkout completions.",
            "List the exact problems you fix: render-blocking assets, image bloat, plugin overhead, cache issues, and Core Web Vitals gaps like LCP and CLS.",
            "Spell out deliverables: manual speed audit, fixes within scope, before-and-after report, and clear notes on hosting or server limits.",
            "Add a trust block: mention the types of sites you handle, required access, and what score improvements are realistic without making guarantees.",
        ]
        if optimization_report.description_recommendations:
            blueprint.extend(optimization_report.description_recommendations[:2])
        if analysis and analysis.what_to_implement:
            blueprint.extend(analysis.what_to_implement[:2])
        deduped_blueprint = self._dedupe_strings(blueprint)[:6]
        description_lines = [
            hook,
            "",
            "What I improve:",
            "- WordPress speed bottlenecks affecting mobile and desktop performance",
            "- Core Web Vitals issues like LCP, CLS, and render-blocking assets",
            "- PageSpeed Insights and GTmetrix issues caused by theme, plugin, image, or script bloat",
            "",
            "What you get:",
            "- A manual performance audit with clear issue mapping",
            "- Speed optimization work within the agreed scope",
            "- Before-and-after reporting so you can see what changed",
            "- Clear guidance on anything limited by hosting or server-side constraints",
            "",
            "Before I start, send the access needed for WordPress, cache/CDN, and hosting when relevant.",
        ]
        if my_gig.description_excerpt:
            description_lines.extend(
                [
                    "",
                    "Keep one short reassurance line from your current gig if it is already converting after buyers click in.",
                ]
            )
        return {
            "opening": hook,
            "blueprint": deduped_blueprint,
            "full_text": "\n".join(description_lines),
        }

    def _build_description_options(
        self,
        *,
        title_options: list[dict[str, str]],
        my_gig: GigPageOverview,
        optimization_report: OptimizationReport,
        derived_terms: list[str],
        title_patterns: list[str],
    ) -> list[dict[str, Any]]:
        preferred_phrases = self._prioritized_market_phrases(title_patterns=title_patterns, derived_terms=derived_terms)
        primary_pattern = preferred_phrases[0].title() if preferred_phrases else "PageSpeed Insights"
        secondary_pattern = preferred_phrases[1].title() if len(preferred_phrases) > 1 else "Core Web Vitals"
        description_recommendations = optimization_report.description_recommendations[:3]
        base_access_line = "Before I start, send WordPress, cache/CDN, and hosting access if server-level changes are needed."
        options = [
            {
                "label": "Conversion Focus",
                "summary": "Use this if you want the gig to speak to business owners who care about leads and lost visitors.",
                "text": (
                    f"Is your slow WordPress site costing you visitors, leads, or sales? I will improve {primary_pattern} and {secondary_pattern} performance so your site feels faster and converts better.\n\n"
                    "What I improve:\n"
                    "- Slow-loading pages, images, scripts, and plugin bottlenecks\n"
                    "- Core Web Vitals issues hurting user experience and trust\n"
                    "- PageSpeed and GTmetrix issues that keep your site feeling heavy\n\n"
                    "What you get:\n"
                    "- A manual speed audit\n"
                    "- Fixes within the agreed scope\n"
                    "- Before-and-after reporting so you can see the result\n\n"
                    f"{base_access_line}"
                ),
            },
            {
                "label": "Technical Proof",
                "summary": "Use this if you want to attract buyers searching for exact tools and metrics like PageSpeed Insights, LCP, or GTmetrix.",
                "text": (
                    f"I will audit and optimize WordPress speed issues affecting {primary_pattern}, {secondary_pattern}, GTmetrix, LCP, CLS, and overall front-end performance.\n\n"
                    "This service is ideal for plugin-heavy WordPress sites, Elementor builds, and sites slowed down by asset bloat, cache conflicts, or poor media handling.\n\n"
                    "Deliverables:\n"
                    "- Performance diagnosis\n"
                    "- Optimization fixes within scope\n"
                    "- Before-and-after benchmark summary\n\n"
                    f"{base_access_line}"
                ),
            },
            {
                "label": "WooCommerce Angle",
                "summary": "Use this if you want to lean into product-page speed, cart flow, and checkout performance.",
                "text": (
                    "I help WooCommerce store owners fix slow product pages, category pages, cart flow, and checkout performance so the site loads faster and the buying experience feels smoother.\n\n"
                    f"I will improve WordPress speed, {secondary_pattern}, and buyer-facing performance issues caused by heavy themes, apps, scripts, or image weight.\n\n"
                    "What you get:\n"
                    "- Store-focused speed audit\n"
                    "- Optimization work for the highest-impact bottlenecks\n"
                    "- Clear before-and-after reporting and next-step notes\n\n"
                    f"{base_access_line}"
                ),
            },
        ]
        for option, title_option in zip(options, title_options):
            option["paired_title"] = title_option["title"]
        if description_recommendations:
            for option in options:
                option["notes"] = description_recommendations
        return options

    def _prioritized_market_phrases(self, *, title_patterns: list[str], derived_terms: list[str]) -> list[str]:
        priority = [
            "pagespeed insights",
            "core web vitals",
            "wordpress speed",
            "woocommerce speed",
            "gtmetrix",
            "page speed",
            "speed optimization",
            "performance audit",
        ]
        combined = self._dedupe_strings([*title_patterns, *derived_terms])
        ranked: list[str] = []
        for preferred in priority:
            for candidate in combined:
                lowered = candidate.lower()
                if lowered == preferred or preferred in lowered:
                    if candidate not in ranked:
                        ranked.append(candidate)
        for candidate in combined:
            lowered = candidate.lower()
            if lowered in {"performance", "audit"}:
                continue
            if candidate not in ranked:
                ranked.append(candidate)
        return ranked[:5]

    def _recommended_packages(self, *, market_anchor_price: float | None, current_price: float | None) -> list[dict[str, Any]]:
        anchor = market_anchor_price or current_price or 55.0
        basic_price = max(25.0, round(anchor * 0.75))
        standard_price = max(basic_price + 10, round(anchor))
        premium_price = max(standard_price + 20, round(anchor * 1.6))
        return [
            {
                "name": "Basic",
                "price": basic_price,
                "focus": "Audit plus the highest-impact quick wins for PageSpeed Insights and Core Web Vitals.",
            },
            {
                "name": "Standard",
                "price": standard_price,
                "focus": "Full WordPress speed optimization with before-and-after reporting.",
            },
            {
                "name": "Premium",
                "price": premium_price,
                "focus": "Deeper optimization for plugin-heavy or WooCommerce sites plus priority turnaround.",
            },
        ]

    def _trust_boosters(self, analysis, optimization_report: OptimizationReport) -> list[str]:
        items = [
            "Add one concrete before-and-after result near the top of the gig.",
            "Mention the exact tools buyers recognize, especially PageSpeed Insights and GTmetrix.",
            "Show what access is needed and what deliverables buyers receive after the optimization.",
        ]
        if analysis and analysis.why_competitors_win:
            items.extend(analysis.why_competitors_win[:2])
        items.extend(optimization_report.review_actions[:2])
        return self._dedupe_strings(items)[:5]

    def _implementation_summary(self, implementation_blueprint: dict[str, Any]) -> str:
        title = implementation_blueprint.get("recommended_title", "")
        tags = implementation_blueprint.get("recommended_tags", [])
        return (
            f"Update the gig title to '{title}', align the first paragraph around speed + business impact, "
            f"and rotate tags toward {', '.join(tags[:3]) or 'market-intent keywords'}."
        )

    def _create_market_comparison_drafts(
        self,
        snapshot: GigSnapshot,
        comparison: dict[str, Any],
    ) -> None:
        implementation = comparison.get("implementation_blueprint") or {}
        recommended_title = str(implementation.get("recommended_title", "")).strip()
        if recommended_title:
            self._create_queue_record(
                agent_name="Gig Content Optimizer",
                action_type="title_update",
                current_value=snapshot.title,
                proposed_value=recommended_title,
                validation_text=recommended_title,
            )

        recommended_tags = implementation.get("recommended_tags") or []
        if recommended_tags:
            self._create_queue_record(
                agent_name="Buyer Intelligence",
                action_type="keyword_tag_update",
                current_value=json.dumps(snapshot.tags),
                proposed_value=json.dumps(recommended_tags),
                validation_text=" | ".join(recommended_tags),
            )

        full_description = str(implementation.get("description_full", "")).strip()
        if full_description:
            self._create_queue_record(
                agent_name="Gig Content Optimizer",
                action_type="description_update",
                current_value=snapshot.description,
                proposed_value=full_description,
                validation_text=full_description,
            )

    def _dedupe_strings(self, items: list[str]) -> list[str]:
        seen: set[str] = set()
        results: list[str] = []
        for item in items:
            cleaned = str(item or "").strip()
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            results.append(cleaned)
        return results

    def _parse_list_text(self, raw: str) -> list[str]:
        return [
            item.strip()
            for item in re.split(r"[\n,|]+", raw or "")
            if item.strip()
        ]

    def _read_json_with_recovery(self, path: Path, *, default):
        if not path.exists():
            return default
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            decoder = json.JSONDecoder()
            index = 0
            last_value = None
            while index < len(text):
                while index < len(text) and text[index].isspace():
                    index += 1
                if index >= len(text):
                    break
                try:
                    value, next_index = decoder.raw_decode(text, index)
                except json.JSONDecodeError:
                    break
                last_value = value
                index = next_index
            return last_value if last_value is not None else default

    def _write_json_atomic(self, path: Path, payload) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(payload, indent=2)
        with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent), encoding="utf-8") as temp_file:
            temp_file.write(serialized)
            temp_name = temp_file.name
        Path(temp_name).replace(path)

    def _create_action_drafts(self, snapshot: GigSnapshot, report: OptimizationReport) -> None:
        if report.title_variants:
            self._create_queue_record(
                agent_name="Gig Content Optimizer",
                action_type="title_update",
                current_value=snapshot.title,
                proposed_value=report.title_variants[0],
                validation_text=report.title_variants[0],
            )
        if report.tag_recommendations:
            proposed_tags = list(dict.fromkeys([*snapshot.tags, report.tag_recommendations[0]]))
            self._create_queue_record(
                agent_name="Buyer Intelligence",
                action_type="keyword_tag_update",
                current_value=json.dumps(snapshot.tags),
                proposed_value=json.dumps(proposed_tags),
                validation_text=" | ".join(proposed_tags),
            )

    def _create_queue_record(
        self,
        *,
        agent_name: str,
        action_type: str,
        current_value: str,
        proposed_value: str,
        validation_text: str,
    ) -> ApprovalRecord:
        existing = self._find_duplicate_record(action_type, current_value, proposed_value)
        if existing is not None:
            return existing

        validation = self.validator.validate(
            validation_text,
            allowed_numbers=self._current_allowed_numbers(),
        )
        status = self._status_for_validation(validation, action_type=action_type)
        record = self.queue.enqueue(
            agent_name=agent_name,
            action_type=action_type,
            current_value=current_value,
            proposed_value=validation.sanitized_output if action_type in {"title_update", "description_update"} else proposed_value,
            confidence_score=validation.confidence,
            validator_issues=validation.issues,
            status=status,
        )
        self.repository.upsert_hitl_item(record)
        return record

    def _find_duplicate_record(
        self,
        action_type: str,
        current_value: str,
        proposed_value: str,
    ) -> ApprovalRecord | None:
        for record in self.queue.list_records():
            if (
                record.action_type == action_type
                and record.current_value == current_value
                and record.proposed_value == proposed_value
                and record.status in {"pending", "approved", "auto_approved"}
            ):
                return record
        return None

    def _status_for_validation(self, validation, *, action_type: str) -> str:
        if validation.confidence >= 85 and not validation.issues:
            return "auto_approved"
        if validation.confidence < 70:
            return "rejected"
        if action_type in {"title_update", "keyword_tag_update", "description_update"} and validation.confidence >= 70:
            return "pending"
        return "pending"

    def _current_allowed_numbers(self) -> list[float]:
        snapshot = self._load_snapshot()
        analytics = snapshot.analytics
        numbers = [
            analytics.impressions,
            analytics.clicks,
            analytics.orders,
            analytics.saves,
        ]
        if analytics.average_response_time_hours is not None:
            numbers.append(analytics.average_response_time_hours)
        return numbers

    def _default_marketplace_terms(self, snapshot: GigSnapshot) -> list[str]:
        configured = [item.strip() for item in self.config.marketplace_search_terms.split(",") if item.strip()]
        if configured:
            return configured
        seeds = [snapshot.niche, snapshot.title, *snapshot.tags]
        unique: list[str] = []
        seen: set[str] = set()
        for seed in seeds:
            value = seed.strip().lower()
            if not value or value in seen:
                continue
            seen.add(value)
            unique.append(seed.strip())
        return unique[:4]

    def _get_record_or_raise(self, record_id: str) -> ApprovalRecord:
        for record in self.queue.list_records():
            if record.id == record_id:
                return record
        raise KeyError(record_id)

    def _apply_record(self, record: ApprovalRecord) -> None:
        snapshot = self._load_snapshot()
        if record.action_type == "title_update":
            snapshot.title = record.proposed_value
        elif record.action_type == "description_update":
            snapshot.description = record.proposed_value
        elif record.action_type == "keyword_tag_update":
            snapshot.tags = json.loads(record.proposed_value)
        self._save_snapshot(snapshot)

    def _save_gig_comparison(self, comparison: dict[str, Any] | None) -> None:
        state = self._load_dashboard_state()
        state.gig_comparison = comparison
        self._save_dashboard_state(state)

    def _start_scraper_run(
        self,
        search_terms: list[str],
        *,
        status: str = "running",
        message: str = "Starting live marketplace scraper.",
    ) -> None:
        state = self._load_dashboard_state()
        state.scraper_run = ScraperRunState(
            status=status,
            started_at=utc_now_iso(),
            search_terms=search_terms,
            last_status_message=message,
        )
        self._save_dashboard_state(state)

    def _record_scraper_event(self, event: dict[str, Any], callback=None) -> None:
        state = self._load_dashboard_state()
        entry = ScraperActivityEntry(
            timestamp=utc_now_iso(),
            stage=str(event.get("stage", "update")),
            level=str(event.get("level", "info")),
            term=str(event.get("term", "")),
            url=str(event.get("url", "")),
            message=str(event.get("message", "")),
            result_count=(
                int(event["result_count"])
                if event.get("result_count") is not None
                else None
            ),
            gig_title=str(event.get("gig_title", "")),
            seller_name=str(event.get("seller_name", "")),
            starting_price=(
                float(event["starting_price"])
                if event.get("starting_price") is not None
                else None
            ),
            rating=float(event["rating"]) if event.get("rating") is not None else None,
            debug_html_path=str(event.get("debug_html_path", "")),
            debug_screenshot_path=str(event.get("debug_screenshot_path", "")),
        )
        state.scraper_run.last_url = entry.url or state.scraper_run.last_url
        state.scraper_run.last_status_message = entry.message or state.scraper_run.last_status_message
        state.scraper_run.debug_html_path = entry.debug_html_path or state.scraper_run.debug_html_path
        state.scraper_run.debug_screenshot_path = entry.debug_screenshot_path or state.scraper_run.debug_screenshot_path
        if entry.stage == "gig_found" and entry.gig_title:
            preview_gig = MarketplaceGig(
                title=entry.gig_title,
                url=entry.url,
                seller_name=entry.seller_name,
                starting_price=entry.starting_price,
                rating=entry.rating,
                matched_term=entry.term,
            )
            state.scraper_run.recent_gigs = [preview_gig, *state.scraper_run.recent_gigs]
            state.scraper_run.recent_gigs = self._dedupe_marketplace_gigs(state.scraper_run.recent_gigs)[:12]
        if entry.result_count is not None and entry.stage == "run_completed":
            state.scraper_run.total_results = entry.result_count
        state.scraper_run.recent_events.append(entry)
        state.scraper_run.recent_events = state.scraper_run.recent_events[-80:]
        self._save_dashboard_state(state)
        if callback is not None:
            callback(self.get_scraper_run_state())

    def _finalize_scraper_run(
        self,
        *,
        status: str,
        gigs: list[MarketplaceGig],
        message: str,
    ) -> None:
        state = self._load_dashboard_state()
        state.scraper_run.status = status
        state.scraper_run.finished_at = utc_now_iso()
        state.scraper_run.total_results = len(gigs)
        state.scraper_run.last_status_message = message
        state.scraper_run.recent_gigs = gigs[:12]
        self._save_dashboard_state(state)

    def _dedupe_marketplace_gigs(self, gigs: list[MarketplaceGig]) -> list[MarketplaceGig]:
        unique: list[MarketplaceGig] = []
        seen: set[str] = set()
        for gig in gigs:
            key = gig.url or gig.title.lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(gig)
        return unique

    def _apply_marketplace_runtime_settings(self, marketplace_settings) -> None:
        self.config.fiverr_marketplace_max_results = marketplace_settings.max_results
        self.config.fiverr_marketplace_search_url_template = marketplace_settings.search_url_template
        self.config.marketplace_reader_enabled = marketplace_settings.reader_enabled
        self.config.marketplace_reader_base_url = marketplace_settings.reader_base_url
        self.config.marketplace_my_gig_url = marketplace_settings.my_gig_url
        self.config.serpapi_api_key = marketplace_settings.serpapi_api_key or self.config.serpapi_api_key
        self.config.serpapi_engine = marketplace_settings.serpapi_engine or self.config.serpapi_engine
        self.config.serpapi_num_results = marketplace_settings.serpapi_num_results or self.config.serpapi_num_results

    def _apply_marketplace_results(
        self,
        *,
        snapshot: GigSnapshot,
        gigs: list[MarketplaceGig],
        status,
    ) -> None:
        state = self._load_dashboard_state()
        latest_report = dict(state.latest_report or {})
        competitive_gap_analysis = self.orchestrator.competitive_analysis.analyze(snapshot, gigs) if gigs else None
        latest_report["competitive_gap_analysis"] = (
            asdict(competitive_gap_analysis)
            if competitive_gap_analysis is not None
            else None
        )
        connector_status = list(latest_report.get("connector_status", []))
        connector_status = [item for item in connector_status if item.get("connector") != status.connector]
        connector_status.append(asdict(status))
        latest_report["connector_status"] = connector_status
        state.latest_report = latest_report
        state.scraper_run.recent_gigs = gigs[:12]
        state.scraper_run.total_results = len(gigs)
        state.scraper_run.last_status_message = status.detail
        state.scraper_run.finished_at = utc_now_iso()
        state.scraper_run.status = status.status
        self._save_dashboard_state(state)

    def _derive_gig_search_terms(self, my_gig: GigPageOverview, snapshot: GigSnapshot) -> list[str]:
        candidates = [
            my_gig.title,
            *my_gig.tags,
            *snapshot.tags,
            snapshot.niche,
        ]
        phrases = [
            "wordpress speed",
            "core web vitals",
            "pagespeed insights",
            "woocommerce speed",
            "speed optimization",
            "gtmetrix",
            "performance audit",
        ]
        terms: list[str] = []
        seen: set[str] = set()

        def add(term: str) -> None:
            cleaned = term.strip()
            key = cleaned.lower()
            if not cleaned or key in seen:
                return
            seen.add(key)
            terms.append(cleaned)

        for phrase in phrases:
            haystack = f"{my_gig.title} {my_gig.description_excerpt}".lower()
            if phrase in haystack:
                add(phrase)
        for candidate in candidates:
            normalized = self._normalize_query(candidate)
            if normalized:
                add(normalized)
        return terms[:5] or self._default_marketplace_terms(snapshot)

    def _normalize_query(self, text: str) -> str:
        cleaned = re.sub(r"^\s*i will\s+", "", (text or "").strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned)
        return cleaned[:80].strip()

    def _build_snapshot_from_gig(self, my_gig: GigPageOverview, base_snapshot: GigSnapshot) -> GigSnapshot:
        package_price = my_gig.starting_price if my_gig.starting_price is not None else (
            min((package.price for package in base_snapshot.packages), default=39.0)
        )
        review_count = min(max(int(my_gig.reviews_count or len(base_snapshot.reviews) or 0), 0), 25)
        review_rating = int(round(my_gig.rating or 5))
        return GigSnapshot(
            niche=base_snapshot.niche,
            title=my_gig.title or base_snapshot.title,
            description=my_gig.description_excerpt or base_snapshot.description,
            tags=my_gig.tags or base_snapshot.tags,
            faq=base_snapshot.faq,
            packages=[GigPackage(name="My Gig", price=package_price)],
            analytics=base_snapshot.analytics,
            competitors=base_snapshot.competitors,
            reviews=[ReviewSnippet(text="Public gig review signal", rating=review_rating) for _ in range(review_count)],
            buyer_messages=base_snapshot.buyer_messages,
            goals=base_snapshot.goals,
        )

    def _market_anchor_price(self, gigs: list[MarketplaceGig]) -> float | None:
        prices = sorted(gig.starting_price for gig in gigs if gig.starting_price is not None)
        if not prices:
            return None
        midpoint = len(prices) // 2
        if len(prices) % 2:
            return round(float(prices[midpoint]), 2)
        return round((float(prices[midpoint - 1]) + float(prices[midpoint])) / 2, 2)

    def _snapshot_gig_overview(self, snapshot: GigSnapshot, gig_url: str) -> GigPageOverview:
        return GigPageOverview(
            url=gig_url.strip() or "snapshot://local-gig",
            title=snapshot.title,
            seller_name="Local snapshot",
            description_excerpt=snapshot.description,
            starting_price=min((package.price for package in snapshot.packages), default=None),
            rating=None,
            reviews_count=len(snapshot.reviews),
            tags=snapshot.tags,
        )

    def _fallback_gig_overview_from_url(self, *, gig_url: str, snapshot: GigSnapshot) -> GigPageOverview:
        from urllib.parse import urlparse

        parsed = urlparse(gig_url)
        parts = [part for part in parsed.path.split("/") if part]
        seller_name = parts[0] if parts else "Unknown seller"
        slug = parts[1] if len(parts) > 1 else ""
        title_seed = slug.replace("-", " ").strip()
        if title_seed and not title_seed.lower().startswith("i will "):
            title_seed = f"I will {title_seed}"
        title = self._normalize_query(title_seed) or snapshot.title
        tags = self.orchestrator.marketplace._extract_keywords_from_text(title)  # noqa: SLF001
        return GigPageOverview(
            url=gig_url.strip() or "snapshot://url-fallback",
            title=title,
            seller_name=seller_name,
            description_excerpt=snapshot.description,
            starting_price=min((package.price for package in snapshot.packages), default=None),
            rating=None,
            reviews_count=len(snapshot.reviews),
            tags=tags or snapshot.tags,
        )

    def _snapshot_marketplace_gigs(self, snapshot: GigSnapshot, derived_terms: list[str]) -> list[MarketplaceGig]:
        matched_term = derived_terms[0] if derived_terms else snapshot.niche
        gigs: list[MarketplaceGig] = []
        for competitor in snapshot.competitors[:8]:
            gigs.append(
                MarketplaceGig(
                    title=competitor.title,
                    seller_name="Snapshot benchmark",
                    starting_price=competitor.starting_price,
                    rating=competitor.rating,
                    reviews_count=competitor.reviews_count,
                    matched_term=matched_term,
                    snippet=competitor.description_excerpt,
                )
            )
        return gigs

    def _parse_manual_competitors(self, competitor_input: str, *, matched_term: str = "") -> list[MarketplaceGig]:
        json_competitors = self._parse_json_competitors(competitor_input, matched_term=matched_term)
        if json_competitors:
            return json_competitors[:20]

        competitors: list[MarketplaceGig] = []
        for raw_line in competitor_input.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            parts = [part.strip() for part in line.split("|")]
            title = parts[0] if parts else line
            url = next((part for part in parts if part.startswith("http://") or part.startswith("https://")), "")
            prices = [self._safe_number(part) for part in parts[1:]]
            starting_price = prices[0] if prices else self._safe_number(line)
            rating = None
            reviews_count = None
            delivery_days = None
            if len(prices) >= 2:
                rating = prices[1]
            if len(prices) >= 3 and prices[2] is not None:
                reviews_count = int(prices[2])
            delivery_days = self._extract_delivery_days(line)
            competitors.append(
                MarketplaceGig(
                    title=title or (url or "Manual competitor"),
                    url=url,
                    seller_name="Manual input",
                    starting_price=starting_price,
                    rating=rating,
                    reviews_count=reviews_count,
                    delivery_days=delivery_days,
                    matched_term=matched_term,
                    snippet=line,
                )
            )
        return competitors[:20]

    def _parse_json_competitors(self, competitor_input: str, *, matched_term: str = "") -> list[MarketplaceGig]:
        raw = (competitor_input or "").strip()
        if not raw:
            return []
        try:
            parsed = json.loads(raw)
        except Exception:
            return []
        if isinstance(parsed, dict):
            items = parsed.get("gigs") or parsed.get("items") or parsed.get("results") or []
            imported_term = str(parsed.get("searchTerm", "")).strip()
            matched_term = imported_term or matched_term
        elif isinstance(parsed, list):
            items = parsed
        else:
            return []

        competitors: list[MarketplaceGig] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", "")).strip()
            seller = str(item.get("seller_name", "") or item.get("seller", "")).strip()
            price = self._safe_number(item.get("starting_price") or item.get("price") or "")
            rating = self._safe_number(item.get("rating") or "")
            reviews_value = self._safe_number(item.get("reviews_count") or item.get("reviews") or "")
            reviews_count = int(reviews_value) if reviews_value is not None else None
            delivery_days = self._extract_delivery_days(
                item.get("delivery_days") or item.get("delivery") or item.get("snippet") or ""
            )
            snippet = str(item.get("snippet", "")).strip()
            if not title and not url:
                continue
            competitors.append(
                MarketplaceGig(
                    title=title or url or "Imported competitor",
                    url=url,
                    seller_name=seller,
                    starting_price=price,
                    rating=rating,
                    reviews_count=reviews_count,
                    delivery_days=delivery_days,
                    matched_term=matched_term,
                    snippet=snippet,
                )
            )
        return competitors

    def _safe_number(self, text: str) -> float | None:
        match = re.search(r"(\d+(?:\.\d+)?)", str(text or ""))
        if not match:
            return None
        return float(match.group(1))

    def _extract_delivery_days(self, text: str) -> int | None:
        match = re.search(r"(\d+)\s*(?:day|days)", str(text or "").lower())
        return int(match.group(1)) if match else None
