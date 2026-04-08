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
    ) -> None:
        self.report_service = report_service
        self.dashboard_service = report_service.dashboard_service
        self.websocket_manager = websocket_manager
        self.notification_service = notification_service
        self.job_service = job_service
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._weekly_schedule_available = False
        self._market_watch_running = False
        self._next_market_watch_run = 0.0
        self._market_watch_signature: tuple | None = None

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
        except Exception as exc:
            try:
                self.notification_service.notify(
                    event="error",
                    title="GigOptimizer market watch failed",
                    lines=[str(exc)],
                )
            except Exception:
                pass
        finally:
            self._market_watch_running = False
            self._broadcast_state()

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
