from __future__ import annotations

import asyncio
import base64
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
import threading
import traceback
from urllib.parse import urlsplit, urlunsplit

import logging

from fastapi import Body, Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.wsgi import WSGIMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..config import GigOptimizerConfig
from ..jobs import JobEventBus, JobService
from ..persistence import BlueprintRepository, DatabaseManager
from ..services import (
    AIOverviewService,
    AuthService,
    CacheService,
    DashboardService,
    HostingerService,
    KnowledgeService,
    ManhwaFeedService,
    NotificationService,
    SlackService,
    SettingsService,
    WeeklyReportService,
)
from .security import SecurityHeadersMiddleware, require_csrf, verify_websocket_origin
from .scheduler import WeeklyReportScheduler
from .websocket_manager import DashboardWebSocketManager


BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


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
    manhwa_service = ManhwaFeedService(config, dashboard_service.repository, cache_service)
    report_service = WeeklyReportService(dashboard_service)
    database_manager = dashboard_service.database_manager
    repository = dashboard_service.repository
    event_bus = JobEventBus(config)
    job_service = JobService(config, repository, event_bus)
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
    )
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    frontend_dist_dir = Path(config.frontend_dist_dir).resolve()
    frontend_assets_dir = frontend_dist_dir / "assets"

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
        app.state.manhwa_service = manhwa_service
        app.state.websocket_manager = websocket_manager
        event_bus.subscribe(relay_bus_event)
        event_bus.start()
        app.state.scheduler_status = scheduler.start()
        yield
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
            return JSONResponse(status_code=500, content={"detail": "Internal server error."})
        return HTMLResponse("Internal server error.", status_code=500)

    def build_state(
        *,
        request: Request | None = None,
        authenticated: bool | None = None,
        session=None,
    ) -> dict:
        state = dashboard_service.get_state()
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

    def build_blueprint_state(
        *,
        request: Request | None = None,
        authenticated: bool | None = None,
        session=None,
    ) -> dict:
        state = build_state(request=request, authenticated=authenticated, session=session)
        comparison = state.get("gig_comparison") or {}
        marketplace_settings = settings_service.get_settings().marketplace
        active_gig_url = str(marketplace_settings.my_gig_url or comparison.get("gig_url") or "").strip()
        gig_id = dashboard_service._gig_identifier(active_gig_url or None)  # noqa: SLF001
        return {
            "state": state,
            "job_runs": job_service.list_runs(limit=25),
            "queue": repository.list_hitl_items(limit=50),
            "competitors": repository.list_competitor_snapshots(limit=30),
            "memory": dashboard_service._memory_context(gig_id=gig_id),  # noqa: SLF001
            "assistant_history": list(reversed(repository.list_assistant_messages(gig_id=gig_id, limit=12))),
            "datasets": knowledge_service.list_documents(gig_id=gig_id, limit=20),
            "hostinger": hostinger_service.get_public_status(),
            "workers": job_service.worker_snapshot(),
            "health": build_health_payload(),
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
        }

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
        frontend_ready = frontend_dist_dir.exists() and (frontend_dist_dir / "index.html").exists()
        return {
            "status": "ok" if db_ok and bus_ok else "degraded",
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
                "workers": job_service.worker_snapshot(),
                "frontend": {
                    "ok": frontend_ready or bool(config.frontend_dev_url),
                    "detail": (
                        f"dist ready at {frontend_dist_dir}"
                        if frontend_ready
                        else f"waiting for a Vite build or dev server at {config.frontend_dev_url}"
                    ),
                },
                "last_successful_run": summarize_last_run(latest_run),
            },
        }

    def require_auth(request: Request) -> None:
        if not auth_service.auth_enabled:
            return
        if auth_service.get_request_session(request) is None:
            raise HTTPException(status_code=401, detail="Authentication required.")

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

    def scraper_broadcast_factory(loop: asyncio.AbstractEventLoop):
        def _push(scraper_state: dict) -> None:
            asyncio.run_coroutine_threadsafe(
                websocket_manager.broadcast_json({"type": "scraper_activity", "payload": scraper_state}),
                loop,
            )

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

    @app.get("/api/auth/session")
    async def auth_session(request: Request) -> dict:
        return auth_service.get_auth_state(auth_service.get_request_session(request))

    @app.get("/api/health")
    async def health() -> dict:
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
    async def login(payload: dict = Body(...)) -> JSONResponse:
        if not auth_service.auth_enabled:
            return JSONResponse({"auth": auth_service.get_auth_state(None)})

        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        if not auth_service.authenticate(username, password):
            raise HTTPException(status_code=401, detail="Invalid username or password.")

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
        return build_blueprint_state(request=request)

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
                search_terms=[str(item).strip() for item in (payload.get("search_terms") or []) if str(item).strip()],
            )
            run = job_service.enqueue_marketplace_scrape(
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

    @app.post("/api/assistant/chat")
    async def assistant_chat(
        payload: dict = Body(...),
        _: None = Depends(require_auth),
        __: None = Depends(require_csrf),
    ) -> dict:
        context = build_assistant_context()
        gig_id = str(context.get("gig_id") or dashboard_service._gig_identifier())  # noqa: SLF001
        message = str(payload.get("message", ""))
        retrieval_query_parts = [
            message,
            str(context.get("primary_search_term", "")).strip(),
            str(context.get("recommended_title", "")).strip(),
            " ".join(str(item).strip() for item in (context.get("recommended_tags") or [])[:3] if str(item).strip()),
            " ".join(str(item).strip() for item in (context.get("do_this_first") or [])[:2] if str(item).strip()),
        ]
        retrieval_query = " ".join(part for part in retrieval_query_parts if part).strip()
        retrieved_knowledge = knowledge_service.retrieve_context(
            gig_id=gig_id,
            query=retrieval_query or message,
            limit=6,
        )
        if not retrieved_knowledge:
            retrieved_knowledge = [
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
        context["retrieved_knowledge"] = retrieved_knowledge
        repository.record_assistant_message(
            gig_id=gig_id,
            role="user",
            content=message,
            source="dashboard_chat",
        )
        reply = ai_overview_service.chat(
            message=message,
            context=context,
        )
        repository.record_assistant_message(
            gig_id=gig_id,
            role="assistant",
            content=str(reply.get("reply", "")),
            source=str(reply.get("provider", "assistant")),
            metadata={
                "status": reply.get("status"),
                "model": reply.get("model"),
                "suggestions": reply.get("suggestions", []),
            },
        )
        return {
            "assistant": reply,
            "assistant_history": list(reversed(repository.list_assistant_messages(gig_id=gig_id, limit=12))),
        }

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
