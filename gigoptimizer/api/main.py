from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
from dataclasses import asdict
import hashlib
from pathlib import Path
import threading
import traceback
import json
import secrets
import time
from urllib.parse import urlsplit, urlunsplit

import logging
import re
from zipfile import ZIP_DEFLATED, ZipFile
from uuid import uuid4

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..assistant.memory import ConversationMemory
from ..config import GigOptimizerConfig
from ..jobs import JobEventBus, JobService
from ..services import (
    AIOverviewService,
    AuthService,
    CacheService,
    CopilotLearningService,
    CopilotTrainingService,
    DashboardService,
    HostingerService,
    KnowledgeService,
    ManhwaFeedService,
    NotificationService,
    SlackService,
    SettingsService,
    WeeklyReportService,
    GigHealthScoreEngine,
    TagGapAnalyzer,
    PriceAlertService,
)
from ..services.copilot_learning_engine import CopilotLearningEngine
from .security import SecurityHeadersMiddleware, require_csrf
from .scheduler import WeeklyReportScheduler
from .websocket_manager import DashboardWebSocketManager


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
EXTENSION_SOURCE_DIR = PROJECT_ROOT / "extensions" / "fiverr-market-capture"


def redact_database_url(database_url: str) -> str:
    if not database_url:
        return ""
    if database_url.startswith("sqlite"):
        return "sqlite:///configured"
    parsed = urlsplit(database_url)
    if not parsed.scheme:
        return "configured"
    hostname = parsed.hostname or ""
    if parsed.port:
        hostname = f"{hostname}:{parsed.port}" if hostname else str(parsed.port)
    if parsed.username or parsed.password:
        hostname = f"<credentials>@{hostname}" if hostname else "<credentials>"
    return urlunsplit((parsed.scheme, hostname, parsed.path, "", ""))


def summarize_last_run(latest_run: dict | None) -> dict:
    if not latest_run:
        return {}
    result_payload = latest_run.get("result_payload") or {}
    state = result_payload.get("state") or {}
    latest_report = state.get("latest_report") or {}
    comparison = state.get("gig_comparison") or {}
    recommended_title = (
        result_payload.get("recommended_title")
        or latest_report.get("recommended_title")
        or (comparison.get("implementation_blueprint") or {}).get("recommended_title")
        or ""
    )
    optimization_score = (
        result_payload.get("optimization_score")
        or latest_report.get("optimization_score")
    )
    competitor_count = comparison.get("competitor_count")
    summary = {
        "run_id": latest_run.get("run_id"),
        "job_id": latest_run.get("job_id"),
        "run_type": latest_run.get("run_type"),
        "status": latest_run.get("status"),
        "current_stage": latest_run.get("current_stage"),
        "progress": latest_run.get("progress"),
        "output_summary": latest_run.get("output_summary", ""),
        "error_message": latest_run.get("error_message", ""),
        "created_at": latest_run.get("created_at"),
        "started_at": latest_run.get("started_at"),
        "finished_at": latest_run.get("finished_at"),
        "optimization_score": optimization_score,
        "recommended_title": recommended_title,
        "competitor_count": competitor_count,
    }
    return {key: value for key, value in summary.items() if value not in (None, "", [])}


def api_error_response(*, message: str, code: str, status_code: int, details: dict | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": message,
            "code": code,
            "details": details or {},
        },
    )


def build_extension_bundle(config: GigOptimizerConfig) -> Path:
    if not EXTENSION_SOURCE_DIR.exists():
        raise FileNotFoundError("Extension source directory is missing.")
    build_dir = (config.data_dir / "extension_builds").resolve()
    build_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = build_dir / "fiverr-market-capture.zip"
    source_files = [path for path in EXTENSION_SOURCE_DIR.rglob("*") if path.is_file()]
    latest_source_mtime = max((path.stat().st_mtime for path in source_files), default=0)
    if bundle_path.exists() and bundle_path.stat().st_mtime >= latest_source_mtime:
        return bundle_path
    with ZipFile(bundle_path, "w", compression=ZIP_DEFLATED) as archive:
        for file_path in source_files:
            archive.write(file_path, arcname=file_path.relative_to(EXTENSION_SOURCE_DIR))
    return bundle_path


def slugify_text(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower())
    return normalized.strip("-") or uuid4().hex


def create_app() -> FastAPI:
    config = GigOptimizerConfig.from_env()
    if config.sentry_dsn:
        try:
            import sentry_sdk

            sentry_sdk.init(
                dsn=config.sentry_dsn,
                environment=config.app_env,
                traces_sample_rate=0.1,
            )
        except Exception as exc:
            logging.warning("GigOptimizer Pro could not initialize Sentry: %s", exc)
    settings_service = SettingsService(config)
    cache_service = CacheService(config)
    slack_service = SlackService(settings_service)
    ai_overview_service = AIOverviewService(settings_service, cache_service)
    dashboard_service = DashboardService(
        config,
        settings_service=settings_service,
        ai_overview_service=ai_overview_service,
        cache_service=cache_service,
        slack_service=slack_service,
    )
    knowledge_service = KnowledgeService(config, dashboard_service.repository, cache_service)
    copilot_learning_service = CopilotLearningService(
        config,
        dashboard_service.repository,
        knowledge_service,
        cache_service,
    )
    manhwa_service = ManhwaFeedService(config, dashboard_service.repository, cache_service)
    report_service = WeeklyReportService(dashboard_service)
    database_manager = dashboard_service.database_manager
    repository = dashboard_service.repository
    copilot_training_service = CopilotTrainingService(config, repository)
    _learning_engine = CopilotLearningEngine(config.data_dir)
    try:
        from gigoptimizer.assistant.api_routes import build_assistant
        from gigoptimizer.assistant.training import AssistantTrainer

        ai_assistant = build_assistant(
            provider=config.ai_provider,
            model=config.ai_model,
            api_key=config.ai_api_key,
            base_url=getattr(config, "ai_api_base_url", "") or None,
        )
        assistant_trainer = AssistantTrainer(
            data_dir=config.data_dir,
            repository=repository,
        )
        # Attach a previously built RAG index if one exists on disk.
        try:
            from gigoptimizer.assistant.rag import RAGIndex
            from pathlib import Path as _P

            _rag_index_path = _P(config.data_dir) / "assistant" / "rag_index.json"
            _rag_chunks_path = _P(config.data_dir) / "assistant" / "rag_chunks.jsonl"
            if _rag_index_path.exists() and _rag_chunks_path.exists():
                ai_assistant.rag_index = RAGIndex.load(
                    index_path=_rag_index_path,
                    chunks_path=_rag_chunks_path,
                )
        except Exception as _rag_exc:  # noqa: BLE001
            logging.warning("GigOptimizer Pro could not load RAG index: %s", _rag_exc)
    except Exception as exc:  # noqa: BLE001
        logging.warning("GigOptimizer Pro could not initialize AI assistant: %s", exc)
        ai_assistant = None
        assistant_trainer = None
    event_bus = JobEventBus(config)
    job_service = JobService(config, repository, event_bus, cache_service=cache_service)
    auth_service = AuthService(config)
    hostinger_service = HostingerService(config, settings_service)
    validation_errors, validation_warnings = auth_service.validate_runtime()
    if validation_errors:
        raise RuntimeError("GigOptimizer Pro startup validation failed: " + " | ".join(validation_errors))
    for warning in validation_warnings:
        logging.warning("GigOptimizer Pro security warning: %s", warning)
    notification_service = NotificationService(settings_service)
    notification_service.slack_service = slack_service
    websocket_manager = DashboardWebSocketManager()
    scheduler = WeeklyReportScheduler(
        report_service,
        websocket_manager,
        notification_service,
        job_service=job_service,
        config=config,
        manhwa_service=manhwa_service,
        copilot_learning_service=copilot_learning_service,
        copilot_training_service=copilot_training_service,
    )
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    frontend_dist_dir = Path(config.frontend_dist_dir).resolve()
    frontend_assets_dir = frontend_dist_dir / "assets"
    login_capture_dir = (config.data_dir / "security" / "login_attempts").resolve()
    login_capture_dir.mkdir(parents=True, exist_ok=True)

    def build_extension_install_payload() -> dict:
        return {
            "enabled": bool(config.extension_enabled),
            "installed": False,
            "download_url": "/downloads/fiverr-market-capture.zip",
            "guide_url": "/extension/install",
            "token_configured": bool(str(config.extension_api_token or "").strip()),
            "api_token": str(config.extension_api_token or "").strip(),
            "api_base_url": str(config.app_base_url or "").strip() or "https://animha.co.in",
            "source_dir_present": EXTENSION_SOURCE_DIR.exists(),
        }

    def start_copilot_query_sync(query: str) -> None:
        cleaned_query = str(query or "").strip()
        if not cleaned_query or not config.copilot_learning_enabled:
            return
        loop = asyncio.get_running_loop()

        def worker() -> None:
            try:
                if not config.data_dir.exists():
                    return
                result = copilot_learning_service.sync_query_context(cleaned_query, force=False)
                asyncio.run_coroutine_threadsafe(
                    websocket_manager.broadcast_json(
                        {
                            "type": "state",
                            "payload": build_state(),
                        }
                    ),
                    loop,
                )
                asyncio.run_coroutine_threadsafe(
                    websocket_manager.broadcast_json(
                        {
                            "type": "copilot_learning",
                            "payload": result,
                        }
                    ),
                    loop,
                )
            except Exception as exc:
                logging.warning("GigOptimizer Pro could not refresh copilot query learning: %s", exc)

        threading.Thread(target=worker, daemon=True).start()

    def normalize_extension_comparison_payload(comparison: dict | None, *, keyword: str) -> dict:
        normalized = dict(comparison or {})
        normalized_keyword = dashboard_service._normalize_query(keyword).strip()  # noqa: SLF001
        detected = [str(item).strip() for item in (normalized.get("detected_search_terms") or []) if str(item).strip()]
        if normalized_keyword and not detected:
            detected = [normalized_keyword]
            normalized["detected_search_terms"] = detected
        if not str(normalized.get("primary_search_term", "")).strip():
            normalized["primary_search_term"] = normalized_keyword or (detected[0] if detected else "")
        return normalized

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        loop = asyncio.get_running_loop()

        def relay_bus_event(event: dict) -> None:
            payload = dict(event)
            if payload.get("type") == "state":
                state = dict(payload.get("payload") or {})
                state.setdefault("notifications", settings_service.get_public_settings())
                state.setdefault("setup_health", dashboard_service._build_setup_health())
                payload["payload"] = state
            asyncio.run_coroutine_threadsafe(
                websocket_manager.broadcast_json(payload),
                loop,
            )

        app.state.config = config
        app.state.dashboard_service = dashboard_service
        app.state.ai_overview_service = ai_overview_service
        app.state.report_service = report_service
        app.state.database_manager = database_manager
        app.state.repository = repository
        app.state.event_bus = event_bus
        app.state.job_service = job_service
        app.state.auth_service = auth_service
        app.state.settings_service = settings_service
        app.state.notification_service = notification_service
        app.state.slack_service = slack_service
        app.state.hostinger_service = hostinger_service
        app.state.knowledge_service = knowledge_service
        app.state.copilot_learning_service = copilot_learning_service
        app.state.copilot_training_service = copilot_training_service
        app.state.learning_engine = _learning_engine
        app.state.manhwa_service = manhwa_service
        app.state.websocket_manager = websocket_manager
        event_bus.subscribe(relay_bus_event)
        event_bus.start()
        app.state.scheduler_status = scheduler.start()

        # --- Copilot Learning Engine cron loop ---
        import asyncio as _asyncio

        async def _learning_cron_loop():
            import logging as _logging
            _log = _logging.getLogger("copilot.learning.cron")
            conversations_dir = config.data_dir / "conversations"
            while True:
                try:
                    schedule = _learning_engine.get_schedule()
                    if schedule.get("enabled", True):
                        interval_s = schedule.get("interval_seconds", 21600)
                        next_run_str = schedule.get("next_run")
                        if next_run_str:
                            from datetime import datetime, timezone as _tz
                            next_run = datetime.fromisoformat(next_run_str)
                            now = datetime.now(_tz.utc)
                            if now < next_run:
                                wait_s = (next_run - now).total_seconds()
                                await _asyncio.sleep(min(wait_s, 3600))
                                continue
                        _log.info("Copilot learning cron: running training cycle")
                        await _asyncio.to_thread(
                            _learning_engine.run_training_cycle, conversations_dir
                        )
                        _log.info("Copilot learning cron: cycle complete")
                    await _asyncio.sleep(300)  # check schedule every 5 min
                except _asyncio.CancelledError:
                    break
                except Exception as _exc:
                    _log.warning("Copilot learning cron error: %s", _exc)
                    await _asyncio.sleep(60)

        _cron_task = _asyncio.create_task(_learning_cron_loop())

        # --- 4-hour Slack digest cron ---
        async def _slack_digest_loop():
            import logging as _log2
            _slog = _log2.getLogger("copilot.slack.cron")
            _SLACK_INTERVAL = 4 * 3600  # 4 hours
            await _asyncio.sleep(60)  # brief startup delay
            while True:
                try:
                    slack_url = getattr(config, "slack_webhook_url", None) or ""
                    if slack_url:
                        import httpx as _hx
                        payload = _learning_engine.build_slack_digest()
                        async with _hx.AsyncClient(timeout=10) as _c:
                            r = await _c.post(slack_url, json=payload)
                        _slog.info("Slack digest sent: %s", r.status_code)
                    else:
                        _slog.debug("SLACK_WEBHOOK_URL not set — skipping digest")
                except _asyncio.CancelledError:
                    break
                except Exception as _exc:
                    _slog.warning("Slack digest error: %s", _exc)
                await _asyncio.sleep(_SLACK_INTERVAL)

        _slack_task = _asyncio.create_task(_slack_digest_loop())

        yield
        _cron_task.cancel()
        _slack_task.cancel()
        try:
            await _asyncio.gather(_cron_task, _slack_task, return_exceptions=True)
        except Exception:
            pass
        scheduler.stop()
        event_bus.unsubscribe(relay_bus_event)
        event_bus.stop()
        database_manager.engine.dispose()

    app = FastAPI(title="GigOptimizer Pro Dashboard", version="0.5.0", lifespan=lifespan)
    if config.trusted_hosts_list:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=config.trusted_hosts_list)
    if config.app_force_https:
        app.add_middleware(HTTPSRedirectMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, config=config)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    if frontend_assets_dir.exists():
        app.mount("/dashboard/assets", StaticFiles(directory=str(frontend_assets_dir)), name="dashboard-assets")

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if request.url.path.startswith("/api/"):
            message = str(exc.detail) if isinstance(exc.detail, str) else "Request failed."
            details = exc.detail if isinstance(exc.detail, dict) else {}
            return api_error_response(
                message=message,
                code=f"http_{exc.status_code}",
                status_code=exc.status_code,
                details=details,
            )
        return HTMLResponse(str(exc.detail), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/api/"):
            return api_error_response(
                message="Request validation failed.",
                code="request_validation_error",
                status_code=422,
                details={"errors": exc.errors()},
            )
        return HTMLResponse("Request validation failed.", status_code=422)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        send_slack_event(
            "system_error",
            {
                "error_message": str(exc),
                "job_id": "api-request",
                "stack_trace": traceback.format_exc(limit=6),
                "path": request.url.path,
            },
        )
        if request.url.path.startswith("/api/"):
            return api_error_response(
                message="Internal server error.",
                code="internal_error",
                status_code=500,
                details={"path": request.url.path},
            )
        return HTMLResponse("Internal server error.", status_code=500)

    def build_state(
        *,
        request: Request | None = None,
        authenticated: bool | None = None,
        session=None,
        safe: bool = False,
    ) -> dict:
        state = dashboard_service.get_state(safe=safe)
        resolved_session = session if session is not None else (
            auth_service.get_request_session(request) if request is not None else None
        )
        if authenticated is True and resolved_session is None:
            auth_state = {"enabled": auth_service.auth_enabled, "authenticated": True, "username": auth_service.admin_username}
        else:
            auth_state = auth_service.get_auth_state(resolved_session)
        state["notifications"] = settings_service.get_public_settings()
        state["auth"] = auth_state
        state["security_warnings"] = validation_warnings
        return state

    def _resolve_gig_context(state: dict) -> tuple[str, str, str]:
        """Return (active_gig_url, gig_id, primary_search_term) from a state dict."""
        comparison = state.get("gig_comparison") or {}
        marketplace_settings = settings_service.get_settings().marketplace
        active_gig_url = str(marketplace_settings.my_gig_url or comparison.get("gig_url") or "").strip()
        gig_id = dashboard_service._gig_identifier(active_gig_url or None)  # noqa: SLF001
        primary_search_term = str(comparison.get("primary_search_term", "")).strip()
        return active_gig_url, gig_id, primary_search_term

    def build_blueprint_state(
        *,
        request: Request | None = None,
        authenticated: bool | None = None,
        session=None,
    ) -> dict:
        """Fast-path bootstrap — returns in <1 s on a warm system.

        Slow fields (health, hostinger, tag_gap, timeline, comparison_diff,
        scraper_summary) are moved to ``/api/v2/bootstrap/extended`` so the
        frontend can render immediately and fetch the rest lazily.
        """
        state = build_state(request=request, authenticated=authenticated, session=session, safe=True)
        _gig_url, gig_id, _term = _resolve_gig_context(state)
        return {
            "state": state,
            "job_runs": job_service.list_runs(limit=25),
            "queue": repository.list_hitl_items(limit=50),
            "competitors": repository.list_competitor_snapshots(limit=30),
            "memory": dashboard_service._memory_context(gig_id=gig_id),  # noqa: SLF001
            "assistant_history": list(reversed(repository.list_assistant_messages(gig_id=gig_id, limit=12))),
            "datasets": knowledge_service.list_documents(gig_id=gig_id, limit=20),
            "copilot_learning": copilot_learning_service.status(),
            "copilot_training": copilot_training_service.status(gig_id=gig_id),
            "security": build_login_security_payload(),
            "workers": job_service.worker_snapshot(),
            "scraper_logs": repository.list_scraper_logs(limit=10),
            "extension_install": build_extension_install_payload(),
        }

    def build_blueprint_state_extended(
        *,
        request: Request | None = None,
        authenticated: bool | None = None,
        session=None,
    ) -> dict:
        """Slow-path bootstrap — fetches DB-heavy and HTTP-bound fields.

        The frontend calls this after the initial render so the dashboard is
        not blocked on health-checks, Hostinger API calls, or tag gap analysis.
        """
        state = build_state(request=request, authenticated=authenticated, session=session, safe=True)
        _gig_url, gig_id, primary_search_term = _resolve_gig_context(state)
        try:
            _snapshot = dashboard_service._load_snapshot()  # noqa: SLF001
            tag_gap = TagGapAnalyzer().analyze(_snapshot).to_dict()
        except Exception:
            tag_gap = {}
        return {
            "health": build_health_payload(),
            "hostinger": hostinger_service.get_public_status(),
            "scraper_summary": repository.scraper_log_summary(limit=50),
            "timeline": dashboard_service.comparison_timeline(gig_id=gig_id, keyword=primary_search_term, limit=16),
            "comparison_diff": dashboard_service.comparison_diff(gig_id=gig_id),
            "tag_gap": tag_gap,
        }

    def build_assistant_context() -> dict:
        state = dashboard_service.get_state()
        comparison = state.get("gig_comparison") or {}
        marketplace_settings = settings_service.get_settings().marketplace
        implementation = comparison.get("implementation_blueprint") or {}
        active_gig_url = str(marketplace_settings.my_gig_url or comparison.get("gig_url") or "").strip()
        active_terms = marketplace_settings.search_terms or comparison.get("detected_search_terms") or []
        gig_id = dashboard_service._gig_identifier(active_gig_url or None)  # noqa: SLF001
        memory_context = dashboard_service._memory_context(gig_id=gig_id)  # noqa: SLF001
        latest_report = state.get("latest_report") or {}
        scraper_run = state.get("scraper_run") or {}
        top_ten = (comparison.get("first_page_top_10") or [])[:10]
        one_by_one = (comparison.get("one_by_one_recommendations") or [])[:10]
        pending_queue = [
            item
            for item in state.get("queue", [])
            if item.get("status") in {"pending", "auto_approved", "approved"}
        ][:8]
        return {
            "optimization_score": latest_report.get("optimization_score"),
            "gig_id": gig_id,
            "gig_url": active_gig_url,
            "primary_search_term": (active_terms[0] if active_terms else comparison.get("primary_search_term", "")),
            "recommended_title": implementation.get("recommended_title", ""),
            "recommended_tags": implementation.get("recommended_tags", []),
            "market_anchor_price": comparison.get("market_anchor_price"),
            "competitor_count": comparison.get("competitor_count", 0),
            "top_ranked_gig": comparison.get("top_ranked_gig", {}),
            "first_page_top_10": top_ten,
            "one_by_one_recommendations": one_by_one,
            "top_search_titles": comparison.get("top_search_titles", []),
            "title_patterns": comparison.get("title_patterns", []),
            "why_competitors_win": comparison.get("why_competitors_win", []),
            "what_to_implement": comparison.get("what_to_implement", []),
            "do_this_first": implementation.get("do_this_first", []),
            "prioritized_actions": implementation.get("prioritized_actions", []),
            "pricing_strategy": implementation.get("pricing_strategy", []),
            "trust_boosters": implementation.get("trust_boosters", []),
            "faq_recommendations": implementation.get("faq_recommendations", []),
            "persona_focus": implementation.get("persona_focus", []),
            "description_full": implementation.get("description_full", ""),
            "title_options": implementation.get("title_options", []),
            "description_options": implementation.get("description_options", []),
            "scraper_status": scraper_run.get("status", "idle"),
            "scraper_message": scraper_run.get("last_status_message", ""),
            "recent_scraper_events": list(reversed((scraper_run.get("recent_events") or [])[-8:])),
            "recent_scraper_gigs": (scraper_run.get("recent_gigs") or [])[:8],
            "keyword_pulse": latest_report.get("niche_pulse", {}).get("trending_queries", [])[:8],
            "pending_queue": pending_queue,
            "hostinger": hostinger_service.get_public_status(),
            "user_actions": memory_context.get("user_actions", []),
            "comparison_history": memory_context.get("comparison_history", []),
            "assistant_history": memory_context.get("assistant_history", []),
            "knowledge_documents": knowledge_service.summarize_documents(gig_id=gig_id, limit=8),
            "copilot_learning": copilot_learning_service.status(),
            "copilot_training": copilot_training_service.status(gig_id=gig_id),
            "global_knowledge_documents": copilot_learning_service.summarize_documents(limit=8),
            "feedback_summary": repository.feedback_summary(gig_id=gig_id),
        }

    def merge_knowledge_results(*knowledge_sets: list[dict[str, object]], limit: int = 8) -> list[dict[str, object]]:
        merged: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        for group in knowledge_sets:
            for item in group:
                document_key = (
                    str(item.get("document_id", ""))
                    or str(item.get("id", ""))
                    or str(item.get("filename", ""))
                )
                snippet_key = (
                    str(item.get("snippet", ""))
                    or str(item.get("preview", ""))
                    or str(item.get("content", ""))[:180]
                )
                key = (document_key, snippet_key)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
                if len(merged) >= limit:
                    return merged
        return merged

    def sync_marketplace_context(*, gig_url: str = "", search_terms: list[str] | None = None) -> None:
        cleaned_gig_url = str(gig_url or "").strip()
        cleaned_terms = [str(item).strip() for item in (search_terms or []) if str(item).strip()]
        if not cleaned_gig_url and not cleaned_terms:
            return
        payload: dict[str, dict[str, object]] = {"marketplace": {}}
        if cleaned_gig_url:
            payload["marketplace"]["my_gig_url"] = cleaned_gig_url
        if cleaned_terms:
            payload["marketplace"]["search_terms"] = cleaned_terms
        settings_service.update_settings(payload)

    def build_health_payload() -> dict:
        db_ok, db_detail = database_manager.healthcheck()
        bus_ok, bus_detail = event_bus.healthcheck()
        latest_run = repository.last_successful_run()
        last_scrape = repository.last_successful_run(run_type="marketplace_scrape") or repository.last_successful_run(run_type="marketplace_compare")
        scraper_summary = repository.scraper_log_summary(limit=50)
        workers = job_service.worker_snapshot()
        frontend_ready = frontend_dist_dir.exists() and (frontend_dist_dir / "index.html").exists()
        healthy = db_ok and bus_ok and bool(workers)
        return {
            "status": "ok" if healthy else "degraded",
            "app": app.title,
            "version": app.version,
            "auth_enabled": auth_service.auth_enabled,
            "scheduler_status": app.state.scheduler_status if hasattr(app.state, "scheduler_status") else "starting",
            "components": {
                "database": {
                    "ok": db_ok,
                    "detail": db_detail,
                    "url": redact_database_url(config.database_url),
                },
                "events": {
                    "ok": bus_ok,
                    "detail": bus_detail,
                },
                "workers": workers,
                "frontend": {
                    "ok": frontend_ready or bool(config.frontend_dev_url),
                    "detail": (
                        f"dist ready at {frontend_dist_dir}"
                        if frontend_ready
                        else f"waiting for a Vite build or dev server at {config.frontend_dev_url}"
                    ),
                },
                "last_successful_run": summarize_last_run(latest_run),
                "last_successful_scrape": summarize_last_run(last_scrape),
                "scraper_logs": scraper_summary,
            },
        }

    _n8n_api_key: str = str(getattr(config, "n8n_internal_api_key", "") or "").strip()

    def require_auth(request: Request) -> None:
        # Allow internal automation tools (n8n) via API key header — no session/CSRF needed
        if _n8n_api_key and request.headers.get("X-Internal-API-Key") == _n8n_api_key:
            return
        if not auth_service.auth_enabled:
            return
        if auth_service.get_request_session(request) is None:
            raise HTTPException(status_code=401, detail="Authentication required.")

    if ai_assistant is not None:
        try:
            from gigoptimizer.assistant.api_routes import build_assistant_router

            assistant_router = build_assistant_router(
                assistant=ai_assistant,
                trainer=assistant_trainer,
                auth_dependency=require_auth,
                csrf_dependency=require_csrf,
            )
            app.include_router(assistant_router)
            app.state.ai_assistant = ai_assistant
            app.state.assistant_trainer = assistant_trainer
        except Exception as exc:  # noqa: BLE001
            logging.warning("GigOptimizer Pro could not mount AI assistant router: %s", exc)

    def require_extension_token(request: Request) -> None:
        if not config.extension_enabled:
            raise HTTPException(status_code=404, detail="Browser extension ingestion is disabled.")
        expected = str(config.extension_api_token or "").strip()
        if not expected:
            raise HTTPException(status_code=503, detail="Browser extension token is not configured.")
        authorization = str(request.headers.get("authorization", "")).strip()
        header_token = str(request.headers.get("x-extension-token", "")).strip()
        actual = header_token
        if authorization.lower().startswith("bearer "):
            actual = authorization[7:].strip()
        if not actual or not secrets.compare_digest(actual, expected):
            raise HTTPException(status_code=401, detail="Invalid browser extension token.")

    def notify_event(event: str, title: str, lines: list[str]) -> None:
        try:
            notification_service.notify(event=event, title=title, lines=lines)
        except Exception:
            return

    def send_slack_event(event_type: str, payload: dict) -> None:
        def worker() -> None:
            try:
                slack_service.send_slack_message(event_type, payload)
            except Exception:
                return

        threading.Thread(target=worker, daemon=True).start()

    def scraper_broadcast_factory(_loop: asyncio.AbstractEventLoop):
        def _push(scraper_state: dict) -> None:
            event_bus.publish("scraper_activity", scraper_state)

        return _push

    def render_blueprint_dashboard_html() -> HTMLResponse:
        index_path = frontend_dist_dir / "index.html"
        if index_path.exists():
            return HTMLResponse(index_path.read_text(encoding="utf-8"))
        return HTMLResponse(
            (
                "<!DOCTYPE html><html><head><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width, initial-scale=1'>"
                "<title>GigOptimizer Pro Blueprint Dashboard</title></head>"
                "<body><div id='root'>GigOptimizer Pro Blueprint Dashboard is waiting for a frontend build.</div></body></html>"
            ),
            status_code=200,
        )

    async def ensure_manhwa_content() -> dict:
        overview = manhwa_service.build_overview()
        if (
            config.manhwa_enabled
            and config.manhwa_auto_sync_enabled
            and (not overview["latest_entries"] or manhwa_service.should_auto_refresh(overview))
        ):
            await asyncio.to_thread(manhwa_service.sync_all_sources, force=True)
            overview = manhwa_service.build_overview()
        return overview

    def absolute_url(request: Request, path: str) -> str:
        forwarded_proto = str(request.headers.get("x-forwarded-proto", "")).split(",")[0].strip()
        forwarded_host = str(request.headers.get("x-forwarded-host", "")).split(",")[0].strip()
        if forwarded_proto and forwarded_host:
            base = f"{forwarded_proto}://{forwarded_host}"
        else:
            base = str(request.base_url).rstrip("/")
        return f"{base}{path}"

    def request_remote_addr(request: Request) -> str:
        forwarded_for = str(request.headers.get("x-forwarded-for", "")).split(",")[0].strip()
        if forwarded_for:
            return forwarded_for
        return request.client.host if request.client is not None else ""

    def build_login_security_payload() -> dict:
        attempts = []
        for item in repository.list_login_attempts(limit=20):
            if item["capture_status"] == "discarded":
                continue
            attempts.append(
                {
                    "id": item["id"],
                    "username": item["username"],
                    "remote_addr": item["remote_addr"],
                    "user_agent": item["user_agent"],
                    "failure_count": item["failure_count"],
                    "capture_required": item["capture_required"],
                    "capture_status": item["capture_status"],
                    "capture_error": item["capture_error"],
                    "created_at": item["created_at"],
                    "photo_captured_at": item["photo_captured_at"],
                    "photo_available": bool(item["photo_path"]),
                    "photo_url": (
                        f"/api/security/login-attempts/{item['id']}/image"
                        if item["photo_path"]
                        else ""
                    ),
                }
            )
        attempts.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        attempts.sort(key=lambda item: item["capture_status"] != "pending_review")
        return {"capture_threshold": 3, "failed_login_attempts": attempts}

    def render_manhwa_feed_xml(request: Request, entries: list[dict]) -> str:
        site_url = absolute_url(request, "/manhwa")
        items = []
        for entry in entries[:40]:
            title = str(entry.get("title", "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            link = absolute_url(request, f"/manhwa/read/{entry.get('slug', '')}")
            source_link = str(entry.get("canonical_url", "")).replace("&", "&amp;")
            description = str(entry.get("summary_text", "") or entry.get("content_text", ""))[:280]
            description = description.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            pub_date = str(entry.get("published_at") or entry.get("fetched_at") or "")
            items.append(
                "<item>"
                f"<title>{title}</title>"
                f"<link>{link}</link>"
                f"<guid>{source_link or link}</guid>"
                f"<description>{description}</description>"
                f"<pubDate>{pub_date}</pubDate>"
                "</item>"
            )
        return (
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<rss version='2.0'><channel>"
            "<title>Animha Newsroom Feed</title>"
            f"<link>{site_url}</link>"
            "<description>Latest manhwa, manga, and comics headlines published automatically on Animha.</description>"
            + "".join(items)
            + "</channel></rss>"
        )

    def render_manhwa_sitemap_xml(request: Request, entries: list[dict]) -> str:
        urls = [
            absolute_url(request, "/manhwa"),
            absolute_url(request, "/manhwa/feed.xml"),
        ]
        urls.extend(absolute_url(request, f"/manhwa/read/{entry.get('slug', '')}") for entry in entries[:200])
        body = "".join(f"<url><loc>{url}</loc></url>" for url in urls if url)
        return (
            "<?xml version='1.0' encoding='UTF-8'?>"
            "<urlset xmlns='http://www.sitemaps.org/schemas/sitemap/0.9'>"
            f"{body}</urlset>"
        )

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request) -> HTMLResponse:
        session = auth_service.get_request_session(request)
        if auth_service.auth_enabled and session is None:
            return RedirectResponse(url="/login", status_code=303)
        return RedirectResponse(url="/dashboard", status_code=303)

    @app.get("/manhwa", response_class=HTMLResponse)
    async def manhwa_home(request: Request, category: str | None = None) -> HTMLResponse:
        if not config.manhwa_enabled:
            raise HTTPException(status_code=404, detail="Animha Manhwa portal is disabled.")
        if category and category not in {"manhwa", "manga", "comics"}:
            raise HTTPException(status_code=404, detail="Category not found.")
        overview = await ensure_manhwa_content()
        entries = manhwa_service.list_entries(category=category, limit=36) if category else overview["latest_entries"]
        session = auth_service.get_request_session(request)
        canonical_path = f"/manhwa?category={category}" if category else "/manhwa"
        page_seo = dict(overview.get("seo") or {})
        if category:
            page_seo = {
                "title": f"Animha {category.title()} News | Latest {category.title()} Headlines",
                "description": f"Latest {category} headlines, release chatter, and discovery stories published automatically on Animha.",
            }
        return templates.TemplateResponse(
            request,
            "manhwa_home.html",
            {
                "overview": overview,
                "entries": entries,
                "active_category": category or "all",
                "page_seo": page_seo,
                "auth_state": auth_service.get_auth_state(session),
                "canonical_url": absolute_url(request, canonical_path),
            },
        )

    @app.get("/studio/manhwa", response_class=HTMLResponse)
    async def manhwa_dashboard(request: Request) -> HTMLResponse:
        session = auth_service.get_request_session(request)
        if auth_service.auth_enabled and session is None:
            return RedirectResponse(url="/login", status_code=303)
        overview = await ensure_manhwa_content()
        return templates.TemplateResponse(
            request,
            "manhwa_dashboard.html",
            {
                "overview": overview,
                "csrf_token": session.csrf_token if session else "",
                "auth_state": auth_service.get_auth_state(session),
                "canonical_url": absolute_url(request, "/studio/manhwa"),
            },
        )

    @app.get("/manhwa/dashboard", response_class=HTMLResponse)
    async def hidden_public_dashboard_path(request: Request) -> HTMLResponse:
        session = auth_service.get_request_session(request)
        if session is None:
            raise HTTPException(status_code=404, detail="Page not found.")
        return RedirectResponse(url="/studio/manhwa", status_code=303)

    @app.get("/manhwa/read/{entry_slug}", response_class=HTMLResponse)
    async def manhwa_reader(request: Request, entry_slug: str) -> HTMLResponse:
        if not config.manhwa_enabled:
            raise HTTPException(status_code=404, detail="Animha Manhwa portal is disabled.")
        context = manhwa_service.build_reader_context(entry_slug)
        if context is None:
            raise HTTPException(status_code=404, detail="Entry not found.")
        context["canonical_url"] = absolute_url(request, f"/manhwa/read/{entry_slug}")
        return templates.TemplateResponse(request, "manhwa_reader.html", context)

    @app.get("/manhwa/feed.xml")
    async def manhwa_feed_xml(request: Request) -> Response:
        entries = manhwa_service.list_entries(limit=40)
        return Response(render_manhwa_feed_xml(request, entries), media_type="application/rss+xml")

    @app.get("/manhwa/sitemap.xml")
    async def manhwa_sitemap_xml(request: Request) -> Response:
        entries = manhwa_service.build_sitemap_entries(limit=200)
        return Response(render_manhwa_sitemap_xml(request, entries), media_type="application/xml")

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_blueprint(request: Request) -> HTMLResponse:
        session = auth_service.get_request_session(request)
        if auth_service.auth_enabled and session is None:
            return RedirectResponse(url="/login", status_code=303)
        return render_blueprint_dashboard_html()

    @app.get("/dashboard/{path:path}", response_class=HTMLResponse)
    async def dashboard_blueprint_routes(request: Request, path: str) -> HTMLResponse:
        session = auth_service.get_request_session(request)
        if auth_service.auth_enabled and session is None:
            return RedirectResponse(url="/login", status_code=303)
        return render_blueprint_dashboard_html()

    @app.get("/extension/install", response_class=HTMLResponse)
    async def extension_install_page(request: Request) -> HTMLResponse:
        session = auth_service.get_request_session(request)
        if auth_service.auth_enabled and session is None:
            return RedirectResponse(url="/login", status_code=303)
        payload = build_extension_install_payload()
        return templates.TemplateResponse(
            request,
            "extension_install.html",
            {
                "install": payload,
                "canonical_url": absolute_url(request, "/extension/install"),
                "auth_state": auth_service.get_auth_state(session),
            },
        )

    @app.get("/downloads/fiverr-market-capture.zip")
    async def extension_download(_: None = Depends(require_auth)) -> FileResponse:
        try:
            bundle_path = build_extension_bundle(config)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Extension bundle is unavailable.") from exc
        return FileResponse(bundle_path, filename="fiverr-market-capture.zip", media_type="application/zip")

    @app.get("/dashboard-legacy", response_class=HTMLResponse)
    async def dashboard_legacy(request: Request) -> HTMLResponse:
        session = auth_service.get_request_session(request)
        if auth_service.auth_enabled and session is None:
            return RedirectResponse(url="/login", status_code=303)
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "scheduler_status": app.state.scheduler_status,
                "default_snapshot": str(config.default_snapshot_path),
                "auth_enabled": auth_service.auth_enabled,
                "auth_username": session.username if session else "",
                "csrf_token": session.csrf_token if session else "",
                "security_warnings": validation_warnings,
            },
        )

    @app.get("/login", response_class=HTMLResponse)
    async def login_page(request: Request) -> HTMLResponse:
        if not auth_service.auth_enabled:
            return RedirectResponse(url="/dashboard", status_code=303)
        if auth_service.get_request_session(request) is not None:
            return RedirectResponse(url="/dashboard", status_code=303)
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "auth_enabled": auth_service.auth_enabled,
            },
        )

    @app.get("/terms-of-service", response_class=HTMLResponse)
    async def terms_of_service_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "terms_of_service.html",
            {},
        )

    @app.get("/api/auth/session")
    async def auth_session(request: Request) -> dict:
        return auth_service.get_auth_state(auth_service.get_request_session(request))

    @app.get("/api/health")
    async def health() -> dict:
        return build_health_payload()

    @app.get("/health")
    async def public_health() -> dict:
        return build_health_payload()

    @app.get("/api/manhwa/overview")
    async def manhwa_overview_api() -> dict:
        if not config.manhwa_enabled:
            raise HTTPException(status_code=404, detail="Animha Manhwa portal is disabled.")
        overview = await ensure_manhwa_content()
        return {"overview": overview}

    @app.post("/api/manhwa/sync")
    async def manhwa_sync_api(
        request: Request,
        payload: dict = Body(default={}),
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        if not config.manhwa_enabled:
            raise HTTPException(status_code=404, detail="Animha Manhwa portal is disabled.")
        result = await asyncio.to_thread(
            manhwa_service.sync_all_sources,
            force=bool(payload.get("force", True)),
        )
        overview = manhwa_service.build_overview()
        notify_event(
            "pipeline_run",
            "Animha content sync completed",
            [
                f"Sources checked: {result.get('total_sources', 0)}",
                f"Entries fetched: {result.get('total_entries', 0)}",
                f"New entries: {result.get('total_new_entries', 0)}",
                f"Errors: {result.get('error_count', 0)}",
            ],
        )
        return {"result": result, "overview": overview, "auth": build_state(request=request).get("auth", {})}

    @app.get("/api/manhwa/sources")
    async def manhwa_sources_api(_: None = Depends(require_auth)) -> dict:
        if not config.manhwa_enabled:
            raise HTTPException(status_code=404, detail="Animha Manhwa portal is disabled.")
        return {"sources": manhwa_service.build_overview()["sources"]}

    @app.post("/api/manhwa/sources")
    async def manhwa_save_source_api(
        request: Request,
        payload: dict = Body(...),
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        if not config.manhwa_enabled:
            raise HTTPException(status_code=404, detail="Animha Manhwa portal is disabled.")
        try:
            source = manhwa_service.save_source(payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        overview = manhwa_service.build_overview()
        notify_event(
            "queue_pending",
            "Animha source saved",
            [
                f"Source: {source['title']}",
                f"Category: {source['category']}",
                f"Feed URL: {source['feed_url']}",
            ],
        )
        return {"source": source, "overview": overview, "auth": build_state(request=request).get("auth", {})}

    @app.post("/api/manhwa/sources/{source_slug}/toggle")
    async def manhwa_toggle_source_api(
        request: Request,
        source_slug: str,
        payload: dict = Body(default={}),
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        if not config.manhwa_enabled:
            raise HTTPException(status_code=404, detail="Animha Manhwa portal is disabled.")
        try:
            source = manhwa_service.set_source_active(
                slug=source_slug,
                active=bool(payload.get("active", True)),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Source not found.") from exc
        overview = manhwa_service.build_overview()
        return {"source": source, "overview": overview, "auth": build_state(request=request).get("auth", {})}

    @app.get("/rq", response_class=HTMLResponse)
    async def rq_overview(request: Request, _: None = Depends(require_auth)) -> HTMLResponse:
        worker_state = job_service.worker_snapshot()
        return HTMLResponse(
            f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
              <meta charset="utf-8">
              <meta name="viewport" content="width=device-width, initial-scale=1">
              <title>GigOptimizer Queue Overview</title>
              <style>
                body {{ font-family: system-ui, sans-serif; background: #0f172a; color: #e2e8f0; padding: 32px; }}
                .card {{ max-width: 720px; margin: 0 auto; background: #111827; border: 1px solid #334155; border-radius: 18px; padding: 24px; }}
                pre {{ white-space: pre-wrap; background: #020617; border-radius: 12px; padding: 16px; }}
              </style>
            </head>
            <body>
              <div class="card">
                <h1>Queue Overview</h1>
                <p>This environment is currently using <strong>{worker_state['backend']}</strong> mode.</p>
                <p>{worker_state['detail']}</p>
                <pre>{worker_state}</pre>
              </div>
            </body>
            </html>
            """
        )

    @app.post("/api/auth/login")
    async def login(request: Request, payload: dict = Body(...)) -> JSONResponse:
        if not auth_service.auth_enabled:
            return JSONResponse({"auth": auth_service.get_auth_state(None)})

        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        client_id = str(payload.get("client_id", "")).strip()
        remote_addr = request_remote_addr(request)
        user_agent = str(request.headers.get("user-agent", "")).strip()
        client_key = auth_service.build_login_client_key(
            client_id=client_id,
            remote_addr=remote_addr,
            user_agent=user_agent,
        )
        if not auth_service.authenticate(username, password):
            failure_count = repository.count_recent_failed_login_attempts(client_key=client_key, window_minutes=30) + 1
            attempt = repository.record_login_attempt(
                username=username,
                client_key=client_key,
                remote_addr=remote_addr,
                user_agent=user_agent,
                success=False,
                failure_count=failure_count,
                capture_required=failure_count >= 3,
                capture_status="pending_capture" if failure_count >= 3 else "not_requested",
            )
            await websocket_manager.broadcast_json({"type": "security_update", "payload": build_login_security_payload()})
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Invalid username or password.",
                    "failed_attempts": failure_count,
                    "capture_required": failure_count >= 3,
                    "attempt_id": attempt["id"],
                },
            )

        repository.record_login_attempt(
            username=username,
            client_key=client_key,
            remote_addr=remote_addr,
            user_agent=user_agent,
            success=True,
            failure_count=0,
            capture_required=False,
            capture_status="success",
        )
        token = auth_service.create_session_token(username)
        session = auth_service.get_session(token)
        response = JSONResponse({"auth": auth_service.get_auth_state(session)})
        response.set_cookie(
            key=auth_service.COOKIE_NAME,
            value=token,
            httponly=True,
            secure=config.app_cookie_secure,
            samesite="strict",
            max_age=config.app_session_ttl_minutes * 60,
            path="/",
        )
        return response

    @app.post("/api/auth/login-attempts/capture")
    async def capture_login_attempt(request: Request, payload: dict = Body(...)) -> dict:
        attempt_id = str(payload.get("attempt_id", "")).strip()
        if not attempt_id:
            raise HTTPException(status_code=400, detail="Missing attempt_id.")
        attempt = repository.get_login_attempt(attempt_id)
        if attempt is None:
            raise HTTPException(status_code=404, detail="Login attempt not found.")

        client_id = str(payload.get("client_id", "")).strip()
        remote_addr = request_remote_addr(request)
        user_agent = str(request.headers.get("user-agent", "")).strip()
        client_key = auth_service.build_login_client_key(
            client_id=client_id,
            remote_addr=remote_addr,
            user_agent=user_agent,
        )
        if attempt["client_key"] != client_key:
            raise HTTPException(status_code=403, detail="Capture request does not match the original login attempt.")

        image_base64 = str(payload.get("image_base64", "")).strip()
        content_type = str(payload.get("content_type", "image/jpeg")).strip() or "image/jpeg"
        capture_error = str(payload.get("capture_error", "")).strip()
        device_info = payload.get("device_info") or {}
        device_summary_parts: list[str] = []
        if isinstance(device_info, dict):
            for label, key in (
                ("platform", "platform"),
                ("language", "language"),
                ("screen", "screen"),
                ("timezone", "timezone"),
                ("touch", "touch_points"),
            ):
                value = str(device_info.get(key, "")).strip()
                if value:
                    device_summary_parts.append(f"{label}={value}")
        device_summary = ", ".join(device_summary_parts)

        photo_path = ""
        capture_status = "pending_review"
        if image_base64:
            try:
                image_bytes = base64.b64decode(image_base64, validate=True)
            except Exception as exc:
                raise HTTPException(status_code=400, detail="Invalid capture image payload.") from exc
            if len(image_bytes) > 5 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="Capture image is too large.")
            extension = ".png" if "png" in content_type.lower() else ".jpg"
            output_path = login_capture_dir / f"{attempt_id}{extension}"
            output_path.write_bytes(image_bytes)
            photo_path = str(output_path)
        else:
            normalized_error = capture_error.lower()
            if normalized_error == "consent_declined":
                capture_status = "consent_declined"
            elif normalized_error == "camera_not_supported":
                capture_status = "camera_unavailable"
            elif capture_error:
                capture_status = "camera_denied"
            else:
                capture_status = "not_captured"

        updated = repository.attach_login_attempt_capture(
            attempt_id=attempt_id,
            photo_path=photo_path or None,
            photo_content_type=content_type if photo_path else None,
            capture_status=capture_status,
            capture_error=capture_error,
            device_summary=device_summary,
        )
        await websocket_manager.broadcast_json({"type": "security_update", "payload": build_login_security_payload()})
        return {
            "attempt": {
                **updated,
                "photo_available": bool(updated.get("photo_path")),
                "photo_url": f"/api/security/login-attempts/{attempt_id}/image" if updated.get("photo_path") else "",
            }
        }

    @app.post("/api/security/login-attempts/{attempt_id}/{action}")
    async def review_login_attempt(
        attempt_id: str,
        action: str,
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        normalized = action.strip().lower()
        if normalized not in {"save", "discard"}:
            raise HTTPException(status_code=400, detail="Unsupported login-attempt action.")
        attempt = repository.get_login_attempt(attempt_id)
        if attempt is None:
            raise HTTPException(status_code=404, detail="Login attempt not found.")
        photo_path_value = str(attempt.get("photo_path") or "").strip()
        if normalized == "discard" and photo_path_value:
            photo_path = Path(photo_path_value)
            if photo_path.exists():
                photo_path.unlink(missing_ok=True)
        updated = repository.review_login_attempt(
            attempt_id=attempt_id,
            capture_status="saved" if normalized == "save" else "discarded",
            clear_photo=(normalized == "discard"),
        )
        await websocket_manager.broadcast_json({"type": "security_update", "payload": build_login_security_payload()})
        return {"attempt": updated}

    @app.get("/api/security/login-attempts/{attempt_id}/image")
    async def login_attempt_image(attempt_id: str, _: None = Depends(require_auth)) -> FileResponse:
        attempt = repository.get_login_attempt(attempt_id)
        if attempt is None or not attempt.get("photo_path"):
            raise HTTPException(status_code=404, detail="Security capture not found.")
        photo_path = Path(str(attempt["photo_path"])).resolve()
        try:
            photo_path.relative_to(login_capture_dir)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Security capture not found.") from exc
        if not photo_path.exists():
            raise HTTPException(status_code=404, detail="Security capture not found.")
        return FileResponse(photo_path, media_type=str(attempt.get("photo_content_type", "") or "image/jpeg"))

    @app.post("/api/auth/logout")
    async def logout(request: Request, _: None = Depends(require_csrf)) -> JSONResponse:
        response = JSONResponse({"auth": auth_service.get_auth_state(None)})
        response.delete_cookie(auth_service.COOKIE_NAME, path="/")
        return response

    @app.get("/api/state")
    async def state(request: Request, _: None = Depends(require_auth)) -> dict:
        return build_state(request=request)

    @app.get("/api/v2/bootstrap")
    async def blueprint_bootstrap(request: Request, _: None = Depends(require_auth)) -> dict:
        """Fast bootstrap — returns essential state immediately (< 1 s)."""
        return build_blueprint_state(request=request)

    @app.get("/api/v2/bootstrap/extended")
    async def blueprint_bootstrap_extended(request: Request, _: None = Depends(require_auth)) -> dict:
        """Slow bootstrap — health, hostinger, tag gap, timeline, comparison diff.
        
        Call this after the initial render to avoid blocking the dashboard load.
        Typically takes 2-8 s depending on DB size and Hostinger API latency.
        """
        return build_blueprint_state_extended(request=request)

    @app.get("/api/v2/jobs")
    async def list_jobs(_: None = Depends(require_auth)) -> dict:
        return {
            "jobs": job_service.list_runs(limit=25),
            "workers": job_service.worker_snapshot(),
        }

    @app.get("/api/v2/jobs/{run_id}")
    async def get_job(run_id: str, _: None = Depends(require_auth)) -> dict:
        run = job_service.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail=f"Job '{run_id}' was not found.")
        return {"job": run}

    @app.get("/api/scraper/stream/{run_id}")
    async def scraper_stream(run_id: str, _: None = Depends(require_auth)):
        if not config.feature_scraper_sse:
            raise HTTPException(status_code=404, detail="Scraper SSE is disabled.")

        async def event_generator():
            queue: asyncio.Queue[str | None] = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def callback(event: dict) -> None:
                event_type = str(event.get("type", "")).strip()
                payload = event.get("payload") or {}
                event_run_id = str(payload.get("run_id") or payload.get("job_id") or payload.get("runId") or "").strip()
                if event_type in {"job_progress", "job_completed", "job_failed", "job_queued"}:
                    event_run_id = str(payload.get("run_id", "")).strip()
                if event_run_id != run_id:
                    return
                packet = f"event: {event_type}\ndata: {json.dumps(payload, default=str)}\n\n"
                loop.call_soon_threadsafe(queue.put_nowait, packet)

            event_bus.subscribe(callback)
            keepalive_task = asyncio.create_task(asyncio.sleep(0))
            try:
                while True:
                    try:
                        message = await asyncio.wait_for(queue.get(), timeout=15)
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
                        continue
                    if message is None:
                        break
                    yield message
            finally:
                keepalive_task.cancel()
                event_bus.unsubscribe(callback)

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @app.post("/api/v2/jobs")
    async def enqueue_job(
        request: Request,
        payload: dict = Body(default={}),
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        job_type = str(payload.get("job_type", "pipeline")).strip().lower()
        if job_type == "pipeline":
            run = job_service.enqueue_pipeline(
                use_live_connectors=bool(payload.get("use_live_connectors", False))
            )
        elif job_type == "marketplace_compare":
            sync_marketplace_context(
                gig_url=str(payload.get("gig_url", "")).strip(),
                search_terms=[str(item).strip() for item in (payload.get("search_terms") or []) if str(item).strip()],
            )
            run = job_service.enqueue_marketplace_compare(
                gig_url=str(payload.get("gig_url", "")).strip(),
                search_terms=[str(item).strip() for item in (payload.get("search_terms") or []) if str(item).strip()],
            )
        elif job_type == "manual_compare":
            sync_marketplace_context(
                gig_url=str(payload.get("gig_url", "")).strip(),
                search_terms=[str(item).strip() for item in (payload.get("search_terms") or []) if str(item).strip()],
            )
            run = job_service.enqueue_manual_compare(
                gig_url=str(payload.get("gig_url", "")).strip(),
                competitor_input=str(payload.get("competitor_input", "")),
                search_terms=[str(item).strip() for item in (payload.get("search_terms") or []) if str(item).strip()],
            )
        elif job_type == "marketplace_scrape":
            sync_marketplace_context(
                gig_url=str(payload.get("gig_url", "")).strip(),
                search_terms=[str(item).strip() for item in (payload.get("search_terms") or []) if str(item).strip()],
            )
            run = job_service.enqueue_marketplace_scrape(
                gig_url=str(payload.get("gig_url", "")).strip(),
                search_terms=[str(item).strip() for item in (payload.get("search_terms") or []) if str(item).strip()],
            )
        elif job_type == "weekly_report":
            run = job_service.enqueue_weekly_report(
                use_live_connectors=bool(payload.get("use_live_connectors", False))
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported job_type '{job_type}'.")

        await websocket_manager.broadcast_json({"type": "job_queued", "payload": run})
        response = build_blueprint_state(request=request)
        response["queued_job"] = run
        return response

    @app.get("/api/v2/competitors")
    async def list_competitors(_: None = Depends(require_auth)) -> dict:
        return {"competitors": repository.list_competitor_snapshots(limit=30)}

    @app.get("/api/v2/history/timeline")
    async def comparison_timeline(
        gig_url: str = "",
        keyword: str = "",
        limit: int = 16,
        _: None = Depends(require_auth),
    ) -> dict:
        gig_id = dashboard_service._gig_identifier(gig_url or None)  # noqa: SLF001
        return {
            "timeline": dashboard_service.comparison_timeline(
                gig_id=gig_id,
                keyword=keyword,
                limit=max(1, min(limit, 60)),
            )
        }

    @app.get("/api/v2/history/diff")
    async def comparison_diff(
        gig_url: str = "",
        left_id: int | None = None,
        right_id: int | None = None,
        _: None = Depends(require_auth),
    ) -> dict:
        gig_id = dashboard_service._gig_identifier(gig_url or None)  # noqa: SLF001
        return {"diff": dashboard_service.comparison_diff(gig_id=gig_id, left_id=left_id, right_id=right_id)}

    @app.get("/api/v2/hitl")
    async def list_hitl(_: None = Depends(require_auth)) -> dict:
        return {"records": repository.list_hitl_items(limit=50)}

    @app.get("/api/v2/datasets")
    async def list_datasets(request: Request, gig_url: str = "", _: None = Depends(require_auth)) -> dict:
        gig_id = dashboard_service._gig_identifier(gig_url or None)  # noqa: SLF001
        return {
            "gig_id": gig_id,
            "datasets": knowledge_service.list_documents(gig_id=gig_id, limit=20),
        }

    @app.post("/api/v2/datasets/upload")
    async def upload_dataset(
        request: Request,
        payload: dict = Body(...),
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        filename = str(payload.get("filename", "")).strip()
        content_type = str(payload.get("content_type", "application/octet-stream")).strip() or "application/octet-stream"
        content_base64 = str(payload.get("content_base64", "")).strip()
        gig_url = str(payload.get("gig_url", "")).strip()
        if not filename or not content_base64:
            raise HTTPException(status_code=400, detail="filename and content_base64 are required.")
        try:
            raw_bytes = base64.b64decode(content_base64, validate=True)
        except Exception as exc:
            raise HTTPException(status_code=400, detail="Dataset payload is not valid base64.") from exc

        sync_marketplace_context(gig_url=gig_url)
        gig_id = dashboard_service._gig_identifier(gig_url or None)  # noqa: SLF001
        try:
            document = knowledge_service.ingest_document(
                gig_id=gig_id,
                filename=filename,
                content_type=content_type,
                raw_bytes=raw_bytes,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        response = build_blueprint_state(request=request)
        response["uploaded_document"] = document
        await websocket_manager.broadcast_json(
            {
                "type": "state",
                "payload": build_state(request=request),
            }
        )
        return response

    @app.delete("/api/v2/datasets/{document_id}")
    async def delete_dataset(
        request: Request,
        document_id: str,
        gig_url: str = "",
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        gig_id = dashboard_service._gig_identifier(gig_url or None)  # noqa: SLF001
        try:
            deleted = knowledge_service.delete_document(gig_id=gig_id, document_id=document_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Dataset not found.") from exc
        response = build_blueprint_state(request=request)
        response["deleted_document"] = deleted
        await websocket_manager.broadcast_json(
            {
                "type": "state",
                "payload": build_state(request=request),
            }
        )
        return response

    @app.get("/api/settings")
    async def get_settings(_: None = Depends(require_auth)) -> dict:
        return settings_service.get_public_settings()

    @app.get("/api/hostinger/status")
    async def hostinger_status(_: None = Depends(require_auth)) -> dict:
        return {"hostinger": hostinger_service.get_public_status()}

    @app.get("/api/copilot/status")
    async def copilot_status(_: None = Depends(require_auth)) -> dict:
        return {
            "copilot_learning": copilot_learning_service.status(),
            "copilot_training": copilot_training_service.status(),
            "datasets": copilot_learning_service.summarize_documents(limit=8),
        }

    @app.post("/api/copilot/sync")
    async def copilot_sync(_: None = Depends(require_auth), __: None = Depends(require_csrf)) -> dict:
        result = await asyncio.to_thread(copilot_learning_service.sync_sources, force=True)
        await websocket_manager.broadcast_json(
            {
                "type": "state",
                "payload": build_state(),
            }
        )
        return {
            "copilot_learning": result,
            "copilot_training": copilot_training_service.status(),
            "datasets": copilot_learning_service.summarize_documents(limit=8),
        }

    @app.get("/api/copilot/training/status")
    async def copilot_training_status(_: None = Depends(require_auth)) -> dict:
        context = build_assistant_context()
        return {
            "copilot_training": copilot_training_service.status(gig_id=str(context.get("gig_id") or "")),
        }

    @app.post("/api/copilot/training/export")
    async def copilot_training_export(_: None = Depends(require_auth), __: None = Depends(require_csrf)) -> dict:
        context = build_assistant_context()
        status = await asyncio.to_thread(
            copilot_training_service.export_training_bundle,
            gig_id=str(context.get("gig_id") or ""),
            force=True,
        )
        await websocket_manager.broadcast_json(
            {
                "type": "state",
                "payload": build_state(),
            }
        )
        await websocket_manager.broadcast_json(
            {
                "type": "copilot_training",
                "payload": status,
            }
        )
        return {"copilot_training": status}

    @app.post("/api/webhooks/n8n")
    async def n8n_webhook(payload: dict = Body(...)) -> dict:
        secret = str(payload.get("secret", "")).strip()
        expected_secret = str(config.n8n_webhook_secret or "change_me").strip() or "change_me"
        if not secrets.compare_digest(secret, expected_secret):
            raise HTTPException(status_code=401, detail="Invalid n8n webhook secret.")

        event = str(payload.get("event", "")).strip() or "unknown"
        body = payload.get("payload") or {}

        if event == "trigger_pipeline":
            from ..jobs.tasks import run_pipeline_job

            asyncio.create_task(
                asyncio.to_thread(
                    run_pipeline_job,
                    uuid4().hex,
                    use_live_connectors=True,
                )
            )
        elif event == "trigger_compare":
            from ..jobs.tasks import run_marketplace_compare_job

            raw_terms = body.get("search_terms") or []
            if isinstance(raw_terms, str):
                search_terms = [item.strip() for item in re.split(r"[\n,;]+", raw_terms) if item.strip()]
            else:
                search_terms = [str(item).strip() for item in raw_terms if str(item).strip()]
            asyncio.create_task(
                asyncio.to_thread(
                    run_marketplace_compare_job,
                    uuid4().hex,
                    gig_url=str(body.get("gig_url", "")).strip(),
                    search_terms=search_terms,
                )
            )
        elif event == "knowledge_refresh":
            title = str(body.get("title", "")).strip() or "n8n-knowledge-refresh"
            content = str(body.get("content", "")).strip()
            knowledge_dir = (config.data_dir / "knowledge").resolve()
            knowledge_dir.mkdir(parents=True, exist_ok=True)
            target_path = knowledge_dir / f"{slugify_text(title)}.md"
            target_path.write_text(content, encoding="utf-8")
            if content:
                knowledge_service.ingest_document(
                    gig_id=copilot_learning_service.GLOBAL_GIG_ID,
                    filename=target_path.name,
                    content_type="text/markdown",
                    raw_bytes=content.encode("utf-8"),
                    source="n8n_webhook",
                )
        elif event == "unknown":
            return {"status": "ignored"}
        else:
            return {"status": "ignored"}

        return {"status": "ok", "event": event}

    async def generate_assistant_chat_response(message: str, *, session_id: str = "global") -> dict:
        context = build_assistant_context()
        gig_id = str(context.get("gig_id") or dashboard_service._gig_identifier())  # noqa: SLF001
        normalized_session_id = str(session_id or "global").strip() or "global"
        memory = ConversationMemory(normalized_session_id, data_dir=config.data_dir / "conversations")
        memory.add("user", message)
        memory_context = memory.summary()
        if memory_context.strip():
            prompt_message = f"[Recent context]\n{memory_context}\n\n[User input]\n{message}"
        else:
            prompt_message = message
        topic_tags = copilot_training_service.classify_topics(message)
        start_copilot_query_sync(message)
        retrieval_query_parts = [
            message,
            str(context.get("primary_search_term", "")).strip(),
            str(context.get("recommended_title", "")).strip(),
            " ".join(str(item).strip() for item in (context.get("recommended_tags") or [])[:3] if str(item).strip()),
            " ".join(str(item).strip() for item in (context.get("do_this_first") or [])[:2] if str(item).strip()),
        ]
        retrieval_query = " ".join(part for part in retrieval_query_parts if part).strip()
        local_knowledge = knowledge_service.retrieve_context(
            gig_id=gig_id,
            query=retrieval_query or message,
            limit=6,
        )
        global_knowledge = copilot_learning_service.retrieve_context(
            query=retrieval_query or message,
            limit=4,
        )
        retrieved_knowledge = merge_knowledge_results(
            local_knowledge,
            global_knowledge,
            limit=8,
        )
        if not retrieved_knowledge:
            local_previews = [
                {
                    "document_id": item.get("id"),
                    "filename": item.get("filename", ""),
                    "score": 1,
                    "snippet": str(item.get("preview", "")).strip(),
                    "content": str(item.get("preview", "")).strip(),
                    "metadata": {"source": "document_preview"},
                    "created_at": item.get("created_at"),
                }
                for item in knowledge_service.summarize_documents(gig_id=gig_id, limit=3)
                if str(item.get("preview", "")).strip()
            ]
            global_previews = [
                {
                    "document_id": item.get("id"),
                    "filename": item.get("filename", ""),
                    "score": 1,
                    "snippet": str(item.get("preview", "")).strip(),
                    "content": str(item.get("preview", "")).strip(),
                    "metadata": {"source": "copilot_feed_preview"},
                    "created_at": item.get("created_at"),
                }
                for item in copilot_learning_service.summarize_documents(limit=3)
                if str(item.get("preview", "")).strip()
            ]
            retrieved_knowledge = merge_knowledge_results(local_previews, global_previews, limit=8)
        context["knowledge_documents"] = merge_knowledge_results(
            knowledge_service.summarize_documents(gig_id=gig_id, limit=8),
            copilot_learning_service.summarize_documents(limit=8),
            limit=12,
        )
        context["retrieved_knowledge"] = retrieved_knowledge
        context["copilot_learning"] = copilot_learning_service.status()
        context["copilot_training"] = copilot_training_service.status(gig_id=gig_id)
        repository.record_assistant_message(
            gig_id=gig_id,
            role="user",
            content=message,
            source="dashboard_chat",
            metadata={
                "topic_tags": topic_tags,
                "estimated_tokens": copilot_training_service.estimate_tokens(message),
            },
        )
        started_at = time.perf_counter()
        reply = None
        try:
            reply = ai_overview_service.chat(
                message=prompt_message,
                context=context,
            )
        except Exception as exc:  # noqa: BLE001
            logging.warning(
                "GigOptimizer Pro grounded copilot path failed, "
                "falling back to unified assistant: %s",
                exc,
            )
            reply = None

        if reply is None and ai_assistant is not None:
            try:
                grounding_lines: list[str] = []
                if context.get("recommended_title"):
                    grounding_lines.append(
                        f"Current recommended gig title: {context['recommended_title']}"
                    )
                if context.get("primary_search_term"):
                    grounding_lines.append(
                        f"Primary search term: {context['primary_search_term']}"
                    )
                recommended_tags = context.get("recommended_tags") or []
                if recommended_tags:
                    grounding_lines.append(
                        "Recommended tags: "
                        + ", ".join(str(tag) for tag in recommended_tags[:8])
                    )
                do_this_first = context.get("do_this_first") or []
                if do_this_first:
                    grounding_lines.append(
                        "Immediate actions in progress: "
                        + "; ".join(str(step) for step in do_this_first[:5])
                    )
                for idx, doc in enumerate(retrieved_knowledge[:5], start=1):
                    snippet = str(
                        doc.get("snippet")
                        or doc.get("content")
                        or doc.get("preview")
                        or ""
                    ).strip()
                    if not snippet:
                        continue
                    if len(snippet) > 600:
                        snippet = snippet[:600].rstrip() + "..."
                    source = str(doc.get("filename") or doc.get("document_id") or f"doc_{idx}")
                    grounding_lines.append(f"[{idx}] {source}:\n{snippet}")
                grounded_context = "\n\n".join(grounding_lines).strip() or None

                envelope = await asyncio.to_thread(
                    ai_assistant.ask,
                    message,
                    context=grounded_context,
                    temperature=0.4,
                )
                structured = envelope.structured or {}
                reply_text_new = (envelope.raw_text or "").strip()
                suggestions_new: list[str] = []
                for step in (structured.get("action_steps") or [])[:6]:
                    step_text = str(step).strip()
                    if step_text:
                        suggestions_new.append(step_text)
                status_new = "ok"
                if envelope.fallback_used:
                    status_new = "fallback"
                if not reply_text_new:
                    status_new = "empty"
                reply = {
                    "reply": reply_text_new,
                    "provider": envelope.provider or "ai_assistant",
                    "status": status_new,
                    "model": envelope.model or "",
                    "suggestions": suggestions_new,
                    "score": envelope.score,
                    "structured": structured,
                    "warnings": list(envelope.warnings or []),
                    "latency_ms": envelope.latency_ms,
                }
            except Exception as exc:  # noqa: BLE001
                logging.warning(
                    "GigOptimizer Pro unified assistant path failed after grounded fallback: %s",
                    exc,
                )
                reply = None

        if reply is None:
            reply = {
                "reply": "The copilot could not answer right now. Try again after refreshing the dashboard state.",
                "provider": "assistant-fallback",
                "status": "error",
                "suggestions": [],
            }
        latency_ms = round((time.perf_counter() - started_at) * 1000)
        reply_text = str(reply.get("reply", ""))
        assistant_topic_tags = sorted(
            set(
                topic_tags
                + copilot_training_service.classify_topics(reply_text)
            )
        )
        repository.record_assistant_message(
            gig_id=gig_id,
            role="assistant",
            content=reply_text,
            source=str(reply.get("provider", "assistant")),
            metadata={
                "status": reply.get("status"),
                "model": reply.get("model"),
                "suggestions": reply.get("suggestions", []),
                "topic_tags": assistant_topic_tags,
                "latency_ms": latency_ms,
                "estimated_tokens": copilot_training_service.estimate_tokens(reply_text),
                "retrieved_sources": [str(item.get("filename", "")) for item in retrieved_knowledge[:5] if item.get("filename")],
            },
        )
        memory.add("assistant", reply_text)
        return {
            "assistant": reply,
            "assistant_history": list(reversed(repository.list_assistant_messages(gig_id=gig_id, limit=12))),
            "copilot_training": copilot_training_service.status(gig_id=gig_id),
            "session_id": normalized_session_id,
        }

    @app.post("/api/assistant/chat")
    async def assistant_chat(
        payload: dict = Body(...),
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        message = str(payload.get("message", "")).strip()
        session_id = str(payload.get("session_id", "global")).strip() or "global"
        if not message:
            raise HTTPException(status_code=400, detail="message is required.")
        return await generate_assistant_chat_response(message, session_id=session_id)

    @app.post("/api/assistant/stream")
    async def assistant_stream(
        payload: dict = Body(...),
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> StreamingResponse:
        message = str(payload.get("message", "")).strip()
        session_id = str(payload.get("session_id", "global")).strip() or "global"
        if not message:
            raise HTTPException(status_code=400, detail="message is required.")
        response_payload = await generate_assistant_chat_response(message, session_id=session_id)
        reply_text = str((response_payload.get("assistant") or {}).get("reply", ""))

        async def event_stream():
            if not reply_text:
                yield "data: [DONE]\n\n"
                return
            # Send reply as words (split on spaces) so the frontend receives clean
            # SSE tokens without embedded newlines that corrupt the data: prefix.
            suggestions = (response_payload.get("assistant") or {}).get("suggestions", [])
            words = reply_text.split(" ")
            for i, word in enumerate(words):
                token = word if i == 0 else " " + word
                # Escape any newlines inside the token to avoid breaking SSE framing
                token_safe = token.replace("\n", " ")
                yield f"data: {token_safe}\n\n"
                await asyncio.sleep(0.012)
            if suggestions:
                import json as _json
                yield f"data: [SUGGESTIONS]{_json.dumps(suggestions)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.post("/api/assistant/feedback")
    async def assistant_feedback(
        payload: dict = Body(...),
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        message_id = int(payload.get("message_id") or 0)
        rating = int(payload.get("rating") or 0)
        note = str(payload.get("note", "") or "")
        if not message_id:
            raise HTTPException(status_code=400, detail="message_id is required.")
        if rating not in {-1, 1}:
            raise HTTPException(status_code=400, detail="rating must be -1 or 1.")
        try:
            feedback = await asyncio.to_thread(
                copilot_training_service.record_feedback,
                message_id=message_id,
                rating=rating,
                note=note,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Assistant message {exc.args[0]} was not found.") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        gig_id = str(feedback.get("gig_id") or dashboard_service._gig_identifier())  # noqa: SLF001
        training_status = copilot_training_service.status(gig_id=gig_id)
        await websocket_manager.broadcast_json(
            {
                "type": "state",
                "payload": build_state(),
            }
        )
        await websocket_manager.broadcast_json(
            {
                "type": "copilot_training",
                "payload": training_status,
            }
        )
        return {
            "feedback": feedback,
            "copilot_training": training_status,
            "assistant_history": list(reversed(repository.list_assistant_messages(gig_id=gig_id, limit=12))),
        }

    @app.get("/api/assistant/sessions/count")
    async def assistant_sessions_count(_: None = Depends(require_auth)) -> dict:
        """Return total and active (modified within 30 min) conversation session counts."""
        import time as _time
        conversations_dir = config.data_dir / "conversations"
        total = 0
        active = 0
        cutoff = _time.time() - 1800  # 30 minutes
        if conversations_dir.exists():
            for p in conversations_dir.glob("*.jsonl"):
                total += 1
                try:
                    if p.stat().st_mtime >= cutoff:
                        active += 1
                except OSError:
                    pass
        return {"active_sessions": active, "total_sessions": total}

    @app.post("/api/settings")
    async def save_settings(payload: dict = Body(...), _: None = Depends(require_auth), __: None = Depends(require_csrf)) -> dict:
        return settings_service.update_settings(payload)

    @app.post("/api/settings/notifications/test")
    async def test_notification(payload: dict = Body(...), _: None = Depends(require_auth), __: None = Depends(require_csrf)) -> dict:
        result = notification_service.send_test(channel=str(payload.get("channel", "")).strip())
        if not result.ok:
            raise HTTPException(status_code=400, detail=result.detail)
        return {"result": asdict(result)}

    @app.post("/api/run")
    async def run_pipeline(request: Request, payload: dict = Body(default={}), _: None = Depends(require_auth), __: None = Depends(require_csrf)) -> dict:
        use_live_connectors = bool(payload.get("use_live_connectors", False))
        try:
            await asyncio.to_thread(
                dashboard_service.run_pipeline,
                use_live_connectors=use_live_connectors,
                scraper_event_callback=scraper_broadcast_factory(asyncio.get_running_loop()),
            )
        except Exception as exc:
            send_slack_event(
                "system_error",
                {
                    "error_message": str(exc),
                    "job_id": "api-run-pipeline",
                    "stack_trace": traceback.format_exc(limit=6),
                },
            )
            notify_event(
                "error",
                "GigOptimizer pipeline failed",
                [str(exc)],
            )
            raise
        response_state = build_state(request=request)
        notify_event(
            "pipeline_run",
            "GigOptimizer pipeline completed",
            [
                f"Optimization score: {response_state['latest_report'].get('optimization_score', '--')}",
                f"Pending approvals: {sum(1 for item in response_state['queue'] if item['status'] == 'pending')}",
                f"Live connectors: {'on' if use_live_connectors else 'off'}",
                (
                    (response_state["latest_report"].get("competitive_gap_analysis") or {})
                    .get("why_competitors_win", ["No live competitor reason yet."])[0]
                ),
                (
                    (response_state["latest_report"].get("competitive_gap_analysis") or {})
                    .get("what_to_implement", ["No live implementation advice yet."])[0]
                ),
            ],
        )
        top_action = (
            ((response_state.get("gig_comparison") or {}).get("implementation_blueprint") or {}).get("top_action")
            or {}
        )
        if top_action:
            send_slack_event(
                "high_impact_action",
                {
                    "action_text": top_action.get("action_text", ""),
                    "expected_gain": top_action.get("expected_gain"),
                    "confidence_score": top_action.get("confidence_score"),
                    "impact_score": top_action.get("impact_score"),
                },
            )
        await websocket_manager.broadcast_json({"type": "state", "payload": response_state})
        return response_state

    @app.post("/api/marketplace/run")
    async def run_marketplace_scrape(
        request: Request,
        payload: dict = Body(default={}),
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        raw_terms = payload.get("search_terms") or []
        search_terms = [str(item).strip() for item in raw_terms if str(item).strip()]
        try:
            response_state = await asyncio.to_thread(
                dashboard_service.run_marketplace_scrape,
                search_terms=search_terms or None,
                scraper_event_callback=scraper_broadcast_factory(asyncio.get_running_loop()),
            )
        except Exception as exc:
            send_slack_event(
                "system_error",
                {
                    "error_message": str(exc),
                    "job_id": "api-marketplace-scrape",
                    "stack_trace": traceback.format_exc(limit=6),
                },
            )
            notify_event(
                "error",
                "Marketplace scraper failed",
                [str(exc)],
            )
            raise

        scraper_run = response_state.get("scraper_run", {})
        notify_event(
            "pipeline_run",
            "Marketplace scraper completed",
            [
                f"Status: {scraper_run.get('status', 'unknown')}",
                f"Total gigs: {scraper_run.get('total_results', 0)}",
                f"Search terms: {', '.join(scraper_run.get('search_terms', [])[:4]) or 'None'}",
            ],
        )
        await websocket_manager.broadcast_json({"type": "state", "payload": response_state})
        return response_state

    @app.post("/api/marketplace/verification/start")
    async def start_marketplace_verification(
        request: Request,
        payload: dict = Body(default={}),
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        raw_terms = payload.get("search_terms") or []
        search_terms = [str(item).strip() for item in raw_terms if str(item).strip()]
        loop = asyncio.get_running_loop()
        push = scraper_broadcast_factory(loop)

        def worker() -> None:
            try:
                state = dashboard_service.run_marketplace_verification(
                    search_terms=search_terms or None,
                    scraper_event_callback=push,
                )
                asyncio.run_coroutine_threadsafe(
                    websocket_manager.broadcast_json({"type": "state", "payload": state}),
                    loop,
                )
            except Exception as exc:
                notify_event("error", "Marketplace verification failed", [str(exc)])

        threading.Thread(target=worker, daemon=True).start()
        response_state = build_state(request=request)
        notify_event(
            "pipeline_run",
            "Marketplace verification started",
            [
                f"Verification terms: {', '.join(search_terms[:4]) or 'Configured marketplace terms'}",
                "Solve the Fiverr challenge in the opened persistent browser window to let scraping resume automatically.",
            ],
        )
        return response_state

    @app.post("/api/marketplace/compare-gig")
    async def compare_marketplace_gig(
        request: Request,
        payload: dict = Body(default={}),
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        gig_url = str(payload.get("gig_url", "")).strip()
        raw_terms = payload.get("search_terms") or []
        search_terms = [str(item).strip() for item in raw_terms if str(item).strip()]
        try:
            response_state = await asyncio.to_thread(
                dashboard_service.compare_my_gig_to_market,
                gig_url=gig_url,
                search_terms=search_terms or None,
                scraper_event_callback=scraper_broadcast_factory(asyncio.get_running_loop()),
            )
        except Exception as exc:
            notify_event(
                "error",
                "My gig market comparison failed",
                [str(exc)],
            )
            raise

        gig_comparison = response_state.get("gig_comparison") or {}
        generated_report = report_service.generate_market_watch_report_from_state(response_state)
        gig_comparison["latest_report_file"] = asdict(generated_report)
        response_state["gig_comparison"] = gig_comparison
        notify_event(
            "pipeline_run",
            "My gig market comparison completed",
            [
                f"Status: {gig_comparison.get('status', 'unknown')}",
                f"Gig URL: {gig_comparison.get('gig_url', gig_url or '--')}",
                f"Competitors compared: {gig_comparison.get('competitor_count', 0)}",
                f"Recommended title: {((gig_comparison.get('implementation_blueprint') or {}).get('recommended_title') or '--')}",
                (
                    (gig_comparison.get("why_competitors_win") or ["No competitor reason was generated yet."])[0]
                ),
                (
                    (gig_comparison.get("what_to_implement") or ["No implementation advice was generated yet."])[0]
                ),
                f"Report: {Path(generated_report.html_path).name}",
            ],
        )
        refreshed_meta = build_state(request=request)
        response_state["recent_reports"] = refreshed_meta.get("recent_reports", [])
        response_state["comparison_history"] = refreshed_meta.get("comparison_history", [])
        response_state["notifications"] = refreshed_meta.get("notifications", {})
        response_state["auth"] = refreshed_meta.get("auth", {})
        response_state["security_warnings"] = refreshed_meta.get("security_warnings", [])
        response_state["setup_health"] = refreshed_meta.get("setup_health", {})
        await websocket_manager.broadcast_json({"type": "state", "payload": response_state})
        return response_state

    @app.post("/api/marketplace/compare-manual")
    async def compare_manual_marketplace_input(
        request: Request,
        payload: dict = Body(default={}),
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        gig_url = str(payload.get("gig_url", "")).strip()
        competitor_input = str(payload.get("competitor_input", ""))
        raw_terms = payload.get("search_terms") or []
        search_terms = [str(item).strip() for item in raw_terms if str(item).strip()]
        response_state = await asyncio.to_thread(
            dashboard_service.compare_manual_market_input,
            gig_url=gig_url,
            competitor_input=competitor_input,
            search_terms=search_terms or None,
            scraper_event_callback=scraper_broadcast_factory(asyncio.get_running_loop()),
        )
        gig_comparison = response_state.get("gig_comparison") or {}
        generated_report = report_service.generate_market_watch_report_from_state(response_state)
        gig_comparison["latest_report_file"] = asdict(generated_report)
        response_state["gig_comparison"] = gig_comparison
        notify_event(
            "pipeline_run",
            "Manual market comparison completed",
            [
                f"Status: {gig_comparison.get('status', 'unknown')}",
                f"Competitors compared: {gig_comparison.get('competitor_count', 0)}",
                f"Recommended title: {((gig_comparison.get('implementation_blueprint') or {}).get('recommended_title') or '--')}",
                (
                    (gig_comparison.get("what_to_implement") or ["No implementation advice was generated yet."])[0]
                ),
                f"Report: {Path(generated_report.html_path).name}",
            ],
        )
        refreshed_meta = build_state(request=request)
        response_state["recent_reports"] = refreshed_meta.get("recent_reports", [])
        response_state["comparison_history"] = refreshed_meta.get("comparison_history", [])
        response_state["notifications"] = refreshed_meta.get("notifications", {})
        response_state["auth"] = refreshed_meta.get("auth", {})
        response_state["security_warnings"] = refreshed_meta.get("security_warnings", [])
        response_state["setup_health"] = refreshed_meta.get("setup_health", {})
        await websocket_manager.broadcast_json({"type": "state", "payload": response_state})
        return response_state

    @app.get("/api/queue")
    async def queue(request: Request, _: None = Depends(require_auth)) -> dict:
        return {"records": build_state(request=request)["queue"]}

    @app.post("/api/queue/{record_id}/approve")
    async def approve_record(
        request: Request,
        record_id: str,
        payload: dict = Body(default={}),
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        try:
            dashboard_service.approve_record(record_id, reviewer_notes=str(payload.get("reviewer_notes", "")))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Queue record '{record_id}' was not found.") from exc

        response_state = build_state(request=request)
        notify_event(
            "approval_decision",
            "GigOptimizer approval applied",
            [
                f"Record: {record_id}",
                f"Reviewer notes: {str(payload.get('reviewer_notes', '')).strip() or 'None'}",
            ],
        )
        await websocket_manager.broadcast_json({"type": "state", "payload": response_state})
        return response_state

    @app.post("/api/queue/{record_id}/reject")
    async def reject_record(
        request: Request,
        record_id: str,
        payload: dict = Body(default={}),
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        try:
            dashboard_service.reject_record(record_id, reviewer_notes=str(payload.get("reviewer_notes", "")))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"Queue record '{record_id}' was not found.") from exc

        response_state = build_state(request=request)
        notify_event(
            "approval_decision",
            "GigOptimizer approval rejected",
            [
                f"Record: {record_id}",
                f"Reviewer notes: {str(payload.get('reviewer_notes', '')).strip() or 'None'}",
            ],
        )
        await websocket_manager.broadcast_json({"type": "state", "payload": response_state})
        return response_state

    @app.post("/api/keywords/apply")
    async def apply_keyword(request: Request, payload: dict = Body(...), _: None = Depends(require_auth), __: None = Depends(require_csrf)) -> dict:
        response_state = dashboard_service.apply_keyword(str(payload.get("keyword", "")))
        built_state = build_state(request=request)
        pending_keywords = [
            item["proposed_value"]
            for item in built_state["queue"]
            if item["action_type"] == "keyword_tag_update" and item["status"] == "pending"
        ]
        if pending_keywords:
            notify_event(
                "queue_pending",
                "GigOptimizer queued a keyword change",
                [
                    f"Keyword request: {str(payload.get('keyword', '')).strip()}",
                    f"Pending queue items: {len(pending_keywords)}",
                ],
            )
        await websocket_manager.broadcast_json({"type": "state", "payload": built_state})
        return built_state

    @app.post("/api/marketplace/recommendations/apply")
    async def apply_marketplace_recommendation(
        request: Request,
        payload: dict = Body(...),
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        response_state = dashboard_service.queue_market_recommendation(
            action_type=str(payload.get("action_type", "")),
            proposed_value=payload.get("proposed_value"),
        )
        notify_event(
            "queue_pending",
            "GigOptimizer queued a market recommendation",
            [
                f"Action: {str(payload.get('action_type', '')).strip() or 'unknown'}",
                f"Pending approvals: {sum(1 for item in response_state.get('queue', []) if item.get('status') == 'pending')}",
            ],
        )
        enriched_state = build_state(request=request)
        response_state["notifications"] = enriched_state.get("notifications", {})
        response_state["auth"] = enriched_state.get("auth", {})
        response_state["security_warnings"] = enriched_state.get("security_warnings", [])
        response_state["comparison_history"] = enriched_state.get("comparison_history", [])
        response_state["setup_health"] = enriched_state.get("setup_health", {})
        await websocket_manager.broadcast_json({"type": "state", "payload": response_state})
        return response_state

    @app.post("/api/extension/import")
    async def import_extension_marketplace_page(request: Request, payload: dict = Body(...)) -> dict:
        require_extension_token(request)
        keyword = str(payload.get("keyword", "")).strip()
        gig_url = str(payload.get("gig_url", "")).strip()
        source_url = str(payload.get("page_url", "") or payload.get("source_url", "")).strip()
        source_label = str(payload.get("source", "browser_extension")).strip() or "browser_extension"
        gigs = payload.get("gigs") or []
        if not isinstance(gigs, list):
            raise HTTPException(status_code=400, detail="gigs must be an array of visible Fiverr cards.")
        if not gigs:
            raise HTTPException(status_code=400, detail="No gigs were provided by the browser extension.")
        if len(gigs) > max(1, config.extension_max_gigs_per_import):
            gigs = gigs[: max(1, config.extension_max_gigs_per_import)]

        sync_marketplace_context(
            gig_url=gig_url,
            search_terms=[keyword] if keyword else [],
        )
        fingerprint_payload = {
            "keyword": keyword,
            "gig_url": gig_url,
            "source_url": source_url,
            "gigs": gigs,
        }
        fingerprint = hashlib.sha256(
            json.dumps(fingerprint_payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        cache_key = f"gigoptimizer:extension-import:{fingerprint}"
        cached_state = cache_service.get_json(cache_key)
        if isinstance(cached_state, dict) and cached_state.get("gig_comparison"):
            comparison = normalize_extension_comparison_payload(
                cached_state.get("gig_comparison"),
                keyword=keyword,
            )
            return {
                "status": "cached",
                "gig_comparison": comparison,
                "optimization_score": (cached_state.get("latest_report") or {}).get("optimization_score"),
            }

        response_state = await asyncio.to_thread(
            dashboard_service.compare_imported_market_data,
            gig_url=gig_url,
            keyword=keyword,
            gigs_payload=gigs,
            source_url=source_url,
            source_label=source_label,
            scraper_event_callback=scraper_broadcast_factory(asyncio.get_running_loop()),
        )
        cache_service.set_json(
            cache_key,
            response_state,
            ttl_seconds=max(60, int(config.extension_import_ttl_seconds)),
        )
        comparison = normalize_extension_comparison_payload(
            response_state.get("gig_comparison"),
            keyword=keyword,
        )
        await websocket_manager.broadcast_json({"type": "state", "payload": response_state})
        return {
            "status": "ok",
            "gig_comparison": comparison,
            "optimization_score": (response_state.get("latest_report") or {}).get("optimization_score"),
        }

    @app.get("/api/reports")
    async def reports(request: Request, _: None = Depends(require_auth)) -> dict:
        return {"reports": build_state(request=request)["recent_reports"]}

    @app.post("/api/reports/run")
    async def run_report(request: Request, payload: dict = Body(default={}), _: None = Depends(require_auth), __: None = Depends(require_csrf)) -> dict:
        report = report_service.generate_weekly_report(
            use_live_connectors=bool(payload.get("use_live_connectors", False))
        )
        response_state = build_state(request=request)
        latest_report = response_state.get("latest_report") or {}
        notify_event(
            "report_generated",
            "GigOptimizer weekly report generated",
            [
                f"Report ID: {report.report_id}",
                f"HTML report: {Path(report.html_path).name}",
            ],
        )
        send_slack_event(
            "weekly_report",
            {
                "summary": (latest_report.get("ai_overview") or {}).get("summary", "") or f"Report {report.report_id} is ready.",
                "top_improvements": latest_report.get("weekly_action_plan", [])[:3],
                "key_insights": ((latest_report.get("competitive_gap_analysis") or {}).get("why_competitors_win", [])[:3]),
                "report_path": report.html_path,
            },
        )
        await websocket_manager.broadcast_json({"type": "state", "payload": response_state})
        return {"report": asdict(report), "state": response_state}

    @app.get("/reports/{file_name}")
    async def serve_report(file_name: str, _: None = Depends(require_auth)) -> FileResponse:
        report_path = (config.reports_dir / file_name).resolve()
        try:
            report_path.relative_to(config.reports_dir.resolve())
        except ValueError as exc:
            raise HTTPException(status_code=404, detail="Report not found.") from exc
        if not report_path.exists():
            raise HTTPException(status_code=404, detail="Report not found.")
        return FileResponse(report_path)


    # ------------------------------------------------------------------
    # Gig Health Score  POST /api/gig/health-score
    # ------------------------------------------------------------------

    @app.post("/api/gig/health-score")
    async def gig_health_score_endpoint(
        request: Request,
        _: None = Depends(require_auth),
    ) -> JSONResponse:
        """Compute a structured 5-dimension health score (0-100) for a gig snapshot."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body.")
        from ..models import GigSnapshot as _GS
        try:
            snapshot = _GS.from_dict(body.get("snapshot", body))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid snapshot: {exc}")
        import asyncio
        health = await asyncio.to_thread(GigHealthScoreEngine().score, snapshot)
        return JSONResponse(content=health.to_dict())

    # ------------------------------------------------------------------
    # SEO Tag Gap  POST /api/gig/tag-gap
    # ------------------------------------------------------------------

    @app.post("/api/gig/tag-gap")
    async def gig_tag_gap_endpoint(
        request: Request,
        _: None = Depends(require_auth),
    ) -> JSONResponse:
        """Return missing, unique, shared, and power tags vs page-one competitors."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body.")
        from ..models import GigSnapshot as _GS, MarketplaceGig as _MG
        try:
            snapshot = _GS.from_dict(body.get("snapshot", body))
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Invalid snapshot: {exc}")
        competitors = [_MG.from_dict(r) for r in body.get("competitors", []) if isinstance(r, dict)]
        report = TagGapAnalyzer().analyze(snapshot, competitors or None)
        return JSONResponse(content=report.to_dict())

    # ------------------------------------------------------------------
    # Price Alert  POST /api/gig/{gig_id}/price-alert/check
    # ------------------------------------------------------------------

    @app.post("/api/gig/{gig_id}/price-alert/check")
    async def price_alert_check_endpoint(
        gig_id: str,
        request: Request,
        _: None = Depends(require_auth),
    ) -> JSONResponse:
        """Compare current competitors against stored baseline; return fired alerts."""
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body.")
        from ..models import MarketplaceGig as _MG
        competitors = [_MG.from_dict(r) for r in body.get("competitors", []) if isinstance(r, dict)]
        service = PriceAlertService(config)
        alerts = service.check_and_alert(gig_id, competitors)
        for alert in alerts:
            try:
                await websocket_manager.broadcast_json(alert.to_ws_event())
            except Exception:
                pass
        if alerts:
            try:
                notification_service.notify(
                    event="price_alert",
                    title=f"\u26a0\ufe0f GigOptimizer \u2014 {len(alerts)} price alert(s) on gig {gig_id}",
                    lines=[a.message for a in alerts],
                )
            except Exception:
                pass
        return JSONResponse(content={"alerts": [a.to_dict() for a in alerts], "count": len(alerts)})

    @app.get("/api/gig/{gig_id}/price-alert/baseline")
    async def price_alert_baseline_endpoint(
        gig_id: str,
        _: None = Depends(require_auth),
    ) -> JSONResponse:
        """Return stored price/review baseline for a gig."""
        return JSONResponse(content=PriceAlertService(config).get_baseline(gig_id))

    @app.websocket("/ws/dashboard")
    async def dashboard_ws(websocket: WebSocket) -> None:
        if not verify_websocket_origin(websocket, config):
            await websocket.close(code=1008)
            return
        session = auth_service.get_websocket_session(websocket)
        if auth_service.auth_enabled and session is None:
            await websocket.close(code=1008)
            return

        await websocket_manager.connect(websocket)
        try:
            await websocket.send_json({"type": "state", "payload": build_state(authenticated=True, session=session)})
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            websocket_manager.disconnect(websocket)


    # ===========================================================================
    # Copilot Training Dashboard Endpoints
    # ===========================================================================

    @app.get("/api/copilot/training-dashboard")
    async def copilot_training_dashboard(_: None = Depends(require_auth)) -> dict:
        """Full dashboard state: vocab model, learning log, test results, schedule."""
        return _learning_engine.get_dashboard_stats()

    @app.post("/api/copilot/training-dashboard/ingest")
    async def copilot_ingest_text(
        payload: dict,
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        """Manually ingest a text document into the learning corpus."""
        text = str(payload.get("text", "")).strip()
        source = str(payload.get("source", "manual")).strip() or "manual"
        source_type = str(payload.get("source_type", "manual")).strip() or "manual"
        if not text:
            raise HTTPException(status_code=422, detail="text field is required")
        result = await asyncio.to_thread(
            _learning_engine.ingest_text, text, source, source_type
        )
        return result

    @app.post("/api/copilot/training-dashboard/train")
    async def copilot_run_training(
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        """Trigger a manual training cycle (ingests conversations + updates schedule)."""
        conversations_dir = config.data_dir / "conversations"
        result = await asyncio.to_thread(
            _learning_engine.run_training_cycle, conversations_dir
        )
        await websocket_manager.broadcast_json({
            "type": "copilot_training",
            "payload": {"status": "cycle_complete", "result": result},
        })
        return result

    @app.post("/api/copilot/training-dashboard/run-tests")
    async def copilot_run_tests(
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        """Run the pure-Python test suites and return results."""
        import pathlib as _pathlib
        repo_root = _pathlib.Path(__file__).parent.parent.parent
        result = await asyncio.to_thread(_learning_engine.run_tests, repo_root)
        return result

    @app.get("/api/copilot/training-dashboard/predict")
    async def copilot_predict(
        q: str = "",
        top_n: int = 8,
        _: None = Depends(require_auth),
    ) -> dict:
        """Return query/word completions for a partial input."""
        if not q.strip():
            return {"completions": []}
        completions = await asyncio.to_thread(
            _learning_engine.predict_completions, q, min(top_n, 20)
        )
        return {"query": q, "completions": completions}

    @app.get("/api/copilot/training-dashboard/schedule")
    async def copilot_get_schedule(_: None = Depends(require_auth)) -> dict:
        return _learning_engine.get_schedule()

    @app.put("/api/copilot/training-dashboard/schedule")
    async def copilot_set_schedule(
        payload: dict,
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        """Update the cron schedule: {interval: '6h'|'12h'|'24h'|'48h', enabled: bool}"""
        interval = str(payload.get("interval", "6h"))
        enabled = bool(payload.get("enabled", True))
        try:
            return _learning_engine.set_schedule(interval, enabled)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    @app.post("/api/copilot/training-dashboard/slack-notify")
    async def copilot_slack_notify(
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        """Send an immediate Slack digest of the current learning state."""
        import httpx as _httpx
        slack_url = getattr(config, "slack_webhook_url", None) or ""
        if not slack_url:
            raise HTTPException(status_code=503, detail="SLACK_WEBHOOK_URL not configured")
        payload = _learning_engine.build_slack_digest()
        async with _httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(slack_url, json=payload)
        if resp.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail="Slack returned " + str(resp.status_code) + ": " + resp.text[:200],
            )
        return {"sent": True, "status_code": resp.status_code}


    return app


app = create_app()


def run() -> None:
    import uvicorn

    config = GigOptimizerConfig.from_env()
    uvicorn.run(
        "gigoptimizer.api.main:app",
        host=config.app_host,
        port=config.app_port,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips=config.app_forwarded_allow_ips,
    )


if __name__ == "__main__":
    run()
