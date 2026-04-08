from __future__ import annotations

import threading
import time

from ..services import NotificationService, WeeklyReportService
from .websocket_manager import DashboardWebSocketManager


class WeeklyReportScheduler:
    JOB_TAG = "gigoptimizer-weekly-report"

    def __init__(
        self,
        report_service: WeeklyReportService,
        websocket_manager: DashboardWebSocketManager,
        notification_service: NotificationService,
        job_service=None,
        config=None,
        manhwa_service=None,
        copilot_learning_service=None,
    ) -> None:
        self.report_service = report_service
        self.dashboard_service = report_service.dashboard_service
        self.websocket_manager = websocket_manager
        self.notification_service = notification_service
        self.slack_service = getattr(notification_service, "slack_service", None)
        self.job_service = job_service
        self.config = config
        self.manhwa_service = manhwa_service
        self.copilot_learning_service = copilot_learning_service
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._weekly_schedule_available = False
        self._market_watch_running = False
        self._next_market_watch_run = 0.0
        self._market_watch_signature: tuple | None = None
        self._manhwa_sync_running = False
        self._next_manhwa_sync_run = 0.0
        self._copilot_learning_running = False
        self._next_copilot_learning_run = 0.0

    def start(self) -> str:
        self._weekly_schedule_available = self._configure_weekly_schedule()

        if self._thread and self._thread.is_alive():
            return self._status_message()

        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return self._status_message()

    def stop(self) -> None:
        self._stop.set()
        try:
            import schedule

            schedule.clear(self.JOB_TAG)
        except ImportError:
            return

    def _configure_weekly_schedule(self) -> bool:
        try:
            import schedule
        except ImportError:
            return False

        schedule.clear(self.JOB_TAG)
        schedule.every().sunday.at("08:00").do(self._run_weekly_job).tag(self.JOB_TAG)
        return True

    def _status_message(self) -> str:
        weekly_text = (
            "weekly scheduler running for Sundays at 08:00 local time"
            if self._weekly_schedule_available
            else "weekly scheduler disabled because the optional 'schedule' dependency is missing"
        )
        return f"{weekly_text}; market watch checks every 5 minutes when enabled."

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._weekly_schedule_available:
                try:
                    import schedule

                    schedule.run_pending()
                except Exception:
                    pass
            self._maybe_run_market_watch()
            self._maybe_run_manhwa_sync()
            self._maybe_run_copilot_learning_sync()
            time.sleep(1)

    def _maybe_run_market_watch(self) -> None:
        settings_service = self.dashboard_service.settings_service
        if settings_service is None:
            return

        marketplace = settings_service.get_settings().marketplace
        interval_minutes = max(5, int(marketplace.auto_compare_interval_minutes or 5))
        search_terms = tuple(marketplace.search_terms or [])
        signature = (
            bool(marketplace.auto_compare_enabled),
            marketplace.my_gig_url.strip(),
            search_terms,
            interval_minutes,
        )
        if signature != self._market_watch_signature:
            self._market_watch_signature = signature
            self._next_market_watch_run = time.time() + 10

        if not marketplace.auto_compare_enabled or not marketplace.my_gig_url.strip():
            self._next_market_watch_run = 0.0
            return
        if self._market_watch_running:
            return
        if time.time() < self._next_market_watch_run:
            return

        self._market_watch_running = True
        self._next_market_watch_run = time.time() + (interval_minutes * 60)
        threading.Thread(
            target=self._run_market_watch_job,
            args=(marketplace.my_gig_url.strip(), list(search_terms)),
            daemon=True,
        ).start()

    def _run_weekly_job(self) -> None:
        if self.job_service is not None:
            self.job_service.enqueue_weekly_report(use_live_connectors=False)
            return
        report = self.report_service.generate_weekly_report(use_live_connectors=False)
        try:
            self.notification_service.notify(
                event="report_generated",
                title="GigOptimizer scheduled weekly report",
                lines=[
                    f"Report ID: {report.report_id}",
                    f"HTML report: {report.html_path}",
                ],
            )
        except Exception:
            pass
        if self.slack_service is not None:
            latest_report = self.dashboard_service.get_state().get("latest_report") or {}
            try:
                self.slack_service.send_slack_message(
                    "weekly_report",
                    {
                        "summary": (latest_report.get("ai_overview") or {}).get("summary", "") or f"Report {report.report_id} is ready.",
                        "top_improvements": latest_report.get("weekly_action_plan", [])[:3],
                        "key_insights": ((latest_report.get("competitive_gap_analysis") or {}).get("why_competitors_win", [])[:3]),
                        "report_path": report.html_path,
                    },
                )
            except Exception:
                pass
        self._broadcast_state()

    def _run_market_watch_job(self, gig_url: str, search_terms: list[str]) -> None:
        try:
            if self.job_service is not None:
                self.job_service.enqueue_marketplace_compare(
                    gig_url=gig_url,
                    search_terms=search_terms,
                )
                return
            report = self.report_service.generate_market_watch_report(
                gig_url=gig_url,
                search_terms=search_terms,
            )
            if report is None:
                return

            comparison = self.dashboard_service.get_state().get("gig_comparison") or {}
            blueprint = comparison.get("implementation_blueprint") or {}
            self.notification_service.notify(
                event="report_generated",
                title="GigOptimizer market watch update",
                lines=[
                    f"Gig URL: {comparison.get('gig_url', gig_url)}",
                    f"Recommended title: {blueprint.get('recommended_title', 'Not generated yet')}",
                    f"Recommended tags: {', '.join(blueprint.get('recommended_tags', [])[:3]) or 'None'}",
                    f"Why competitors win: {(comparison.get('why_competitors_win') or ['No reason generated yet.'])[0]}",
                    f"What to implement: {(comparison.get('what_to_implement') or ['No action generated yet.'])[0]}",
                    f"Report: {report.html_path}",
                ],
            )
            if self.slack_service is not None:
                top_action = (blueprint.get("top_action") or {})
                try:
                    self.slack_service.send_slack_message(
                        "comparison_complete",
                        {
                            "gig_url": comparison.get("gig_url", gig_url),
                            "optimization_score": comparison.get("optimization_score", "--"),
                            "recommended_title": blueprint.get("recommended_title", ""),
                            "top_action": top_action.get("action_text", ""),
                            "top_action_expected_gain": top_action.get("expected_gain"),
                            "competitor_count": comparison.get("competitor_count", 0),
                        },
                    )
                except Exception:
                    pass
        except Exception as exc:
            try:
                self.notification_service.notify(
                    event="error",
                    title="GigOptimizer market watch failed",
                    lines=[str(exc)],
                )
            except Exception:
                pass
            if self.slack_service is not None:
                try:
                    self.slack_service.send_slack_message(
                        "system_error",
                        {
                            "error_message": str(exc),
                            "job_id": "market-watch-scheduler",
                            "stack_trace": str(exc),
                        },
                    )
                except Exception:
                    pass
        finally:
            self._market_watch_running = False
            self._broadcast_state()

    def _maybe_run_manhwa_sync(self) -> None:
        if self.config is None or self.manhwa_service is None:
            return
        if not getattr(self.config, "manhwa_enabled", False):
            return
        if not getattr(self.config, "manhwa_auto_sync_enabled", False):
            return
        if self._manhwa_sync_running:
            return
        if self._next_manhwa_sync_run and time.time() < self._next_manhwa_sync_run:
            return

        interval_minutes = max(5, int(getattr(self.config, "manhwa_sync_interval_minutes", 30) or 30))
        self._next_manhwa_sync_run = time.time() + (interval_minutes * 60)
        self._manhwa_sync_running = True
        threading.Thread(target=self._run_manhwa_sync_job, daemon=True).start()

    def _run_manhwa_sync_job(self) -> None:
        try:
            result = self.manhwa_service.sync_all_sources(force=False)
            self.notification_service.notify(
                event="pipeline_run",
                title="Animha content sync completed",
                lines=[
                    f"Sources checked: {result.get('total_sources', 0)}",
                    f"Entries fetched: {result.get('total_entries', 0)}",
                    f"New entries: {result.get('total_new_entries', 0)}",
                    f"Errors: {result.get('error_count', 0)}",
                ],
            )
        except Exception as exc:
            try:
                self.notification_service.notify(
                    event="error",
                    title="Animha content sync failed",
                    lines=[str(exc)],
                )
            except Exception:
                pass
        finally:
            self._manhwa_sync_running = False

    def _maybe_run_copilot_learning_sync(self) -> None:
        if self.config is None or self.copilot_learning_service is None:
            return
        if not getattr(self.config, "copilot_learning_enabled", False):
            return
        if self._copilot_learning_running:
            return
        if self._next_copilot_learning_run and time.time() < self._next_copilot_learning_run:
            return

        interval_minutes = max(5, int(getattr(self.config, "copilot_learning_interval_minutes", 30) or 30))
        self._next_copilot_learning_run = time.time() + (interval_minutes * 60)
        self._copilot_learning_running = True
        threading.Thread(target=self._run_copilot_learning_job, daemon=True).start()

    def _run_copilot_learning_job(self) -> None:
        try:
            result = self.copilot_learning_service.sync_sources(force=False)
            self.notification_service.notify(
                event="pipeline_run",
                title="GigOptimizer copilot learning sync completed",
                lines=[
                    f"Sources checked: {result.get('total_sources', 0)}",
                    f"Documents seen: {result.get('total_documents_seen', 0)}",
                    f"New documents: {result.get('new_documents', 0)}",
                    f"Errors: {result.get('error_count', 0)}",
                ],
            )
        except Exception as exc:
            try:
                self.notification_service.notify(
                    event="error",
                    title="GigOptimizer copilot learning sync failed",
                    lines=[str(exc)],
                )
            except Exception:
                pass
        finally:
            self._copilot_learning_running = False

    def _broadcast_state(self) -> None:
        try:
            import asyncio

            asyncio.run(
                self.websocket_manager.broadcast_json(
                    {
                        "type": "state",
                        "payload": self.dashboard_service.get_state(),
                    }
                )
            )
        except Exception:
            return
