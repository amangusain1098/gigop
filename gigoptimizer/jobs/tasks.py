from __future__ import annotations

from dataclasses import asdict
from typing import Any

from ..config import GigOptimizerConfig
from ..services import AIOverviewService, DashboardService, SettingsService, WeeklyReportService
from .bus import JobEventBus


def run_job_dispatch(run_id: str, run_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    details = payload or {}
    if run_type == "pipeline":
        return run_pipeline_job(
            run_id,
            use_live_connectors=bool(details.get("use_live_connectors", False)),
        )
    if run_type == "marketplace_compare":
        return run_marketplace_compare_job(
            run_id,
            gig_url=str(details.get("gig_url", "")),
            search_terms=_coerce_terms(details.get("search_terms")),
        )
    if run_type == "manual_compare":
        return run_manual_compare_job(
            run_id,
            gig_url=str(details.get("gig_url", "")),
            competitor_input=str(details.get("competitor_input", "")),
            search_terms=_coerce_terms(details.get("search_terms")),
        )
    if run_type == "marketplace_scrape":
        return run_marketplace_scrape_job(
            run_id,
            search_terms=_coerce_terms(details.get("search_terms")),
        )
    if run_type == "weekly_report":
        return run_weekly_report_job(
            run_id,
            use_live_connectors=bool(details.get("use_live_connectors", False)),
        )
    raise ValueError(f"Unsupported run_type: {run_type}")


def run_pipeline_job(run_id: str, *, use_live_connectors: bool = False) -> dict[str, Any]:
    runtime = _build_runtime()
    return _execute_job(
        run_id=run_id,
        run_type="pipeline",
        runtime=runtime,
        runner=lambda progress_callback: runtime["dashboard_service"].run_pipeline(
            use_live_connectors=use_live_connectors,
            progress_callback=progress_callback,
            scraper_event_callback=lambda state: runtime["event_bus"].publish("scraper_activity", state),
        ),
    )


def run_marketplace_compare_job(
    run_id: str,
    *,
    gig_url: str,
    search_terms: list[str] | None = None,
) -> dict[str, Any]:
    runtime = _build_runtime()
    return _execute_job(
        run_id=run_id,
        run_type="marketplace_compare",
        runtime=runtime,
        initial_stage="Loading gig and market data",
        runner=lambda progress_callback: runtime["dashboard_service"].compare_my_gig_to_market(
            gig_url=gig_url,
            search_terms=search_terms,
            progress_callback=progress_callback,
            scraper_event_callback=lambda current_state: runtime["event_bus"].publish("scraper_activity", current_state),
        ),
    )


def run_manual_compare_job(
    run_id: str,
    *,
    gig_url: str,
    competitor_input: str,
    search_terms: list[str] | None = None,
) -> dict[str, Any]:
    runtime = _build_runtime()
    return _execute_job(
        run_id=run_id,
        run_type="manual_compare",
        runtime=runtime,
        initial_stage="Analyzing imported competitors",
        runner=lambda progress_callback: runtime["dashboard_service"].compare_manual_market_input(
            gig_url=gig_url,
            competitor_input=competitor_input,
            search_terms=search_terms,
            progress_callback=progress_callback,
            scraper_event_callback=lambda current_state: runtime["event_bus"].publish("scraper_activity", current_state),
        ),
    )


def run_marketplace_scrape_job(run_id: str, *, search_terms: list[str] | None = None) -> dict[str, Any]:
    runtime = _build_runtime()
    return _execute_job(
        run_id=run_id,
        run_type="marketplace_scrape",
        runtime=runtime,
        initial_stage="Scanning Fiverr marketplace",
        runner=lambda progress_callback: runtime["dashboard_service"].run_marketplace_scrape(
            search_terms=search_terms,
            scraper_event_callback=lambda current_state: runtime["event_bus"].publish("scraper_activity", current_state),
        ),
    )


def run_weekly_report_job(run_id: str, *, use_live_connectors: bool = False) -> dict[str, Any]:
    runtime = _build_runtime()
    return _execute_job(
        run_id=run_id,
        run_type="weekly_report",
        runtime=runtime,
        initial_stage="Generating weekly report",
        runner=lambda progress_callback: _generate_weekly_report_state(runtime, use_live_connectors),
    )


def _build_runtime() -> dict[str, Any]:
    config = GigOptimizerConfig.from_env()
    settings_service = SettingsService(config)
    ai_overview_service = AIOverviewService(settings_service)
    dashboard_service = DashboardService(
        config,
        settings_service=settings_service,
        ai_overview_service=ai_overview_service,
    )
    report_service = WeeklyReportService(dashboard_service)
    database_manager = dashboard_service.database_manager
    repository = dashboard_service.repository
    event_bus = JobEventBus(config)
    return {
        "config": config,
        "settings_service": settings_service,
        "database_manager": database_manager,
        "dashboard_service": dashboard_service,
        "report_service": report_service,
        "repository": repository,
        "event_bus": event_bus,
    }


def _execute_job(
    run_id: str,
    *,
    run_type: str,
    runtime: dict[str, Any],
    runner,
    initial_stage: str = "Preparing job",
) -> dict[str, Any]:
    repository = runtime["repository"]
    event_bus = runtime["event_bus"]
    repository.update_agent_run(
        run_id,
        status="running",
        started=True,
        current_stage=initial_stage,
        progress=0.05,
    )
    event_bus.publish("job_progress", repository.get_agent_run(run_id) or {})
    try:
        state = runner(
            lambda event: _publish_progress(
                repository=repository,
                event_bus=event_bus,
                run_id=run_id,
                event=event,
            )
        )
        return _finish_success(
            run_id=run_id,
            repository=repository,
            event_bus=event_bus,
            state=state,
            summary=_summarize_state(state, run_type=run_type),
        )
    except Exception as exc:
        repository.update_agent_run(
            run_id,
            status="failed",
            current_stage="Failed",
            error_message=str(exc),
            finished=True,
        )
        failed = repository.get_agent_run(run_id) or {}
        event_bus.publish("job_failed", failed)
        raise
    finally:
        _cleanup_runtime(runtime)


def _generate_weekly_report_state(runtime: dict[str, Any], use_live_connectors: bool) -> dict[str, Any]:
    report = runtime["report_service"].generate_weekly_report(use_live_connectors=use_live_connectors)
    state = runtime["dashboard_service"].get_state()
    state["generated_report"] = asdict(report)
    return state


def _finish_success(
    *,
    run_id: str,
    repository: BlueprintRepository,
    event_bus: JobEventBus,
    state: dict[str, Any],
    summary: str,
) -> dict[str, Any]:
    result_payload = {
        "optimization_score": (state.get("latest_report") or {}).get("optimization_score"),
        "recommended_title": (
            ((state.get("gig_comparison") or {}).get("implementation_blueprint") or {}).get("recommended_title")
            or (state.get("latest_report") or {}).get("title_variants", [""])[0]
        ),
        "state": state,
    }
    repository.update_agent_run(
        run_id,
        status="completed",
        current_stage="Completed",
        progress=1.0,
        result_payload=result_payload,
        output_summary=summary,
        finished=True,
    )
    completed = repository.get_agent_run(run_id) or {}
    event_bus.publish("state", state)
    event_bus.publish("job_completed", completed)
    return completed


def _publish_progress(
    *,
    repository: BlueprintRepository,
    event_bus: JobEventBus,
    run_id: str,
    event: dict[str, Any],
) -> None:
    agent_name = str(event.get("agent_name", "Agent"))
    step = int(event.get("step", 0) or 0)
    total_steps = max(int(event.get("total_steps", 1) or 1), 1)
    raw_progress = float(event.get("progress", 0) or 0)
    progress = raw_progress / 100 if raw_progress > 1 else raw_progress
    progress = min(0.95, max(0.05, progress or (step / total_steps)))
    repository.update_agent_run(
        run_id,
        status="running",
        current_agent=agent_name,
        current_stage=f"{agent_name} ({step}/{total_steps})",
        progress=progress,
    )
    event_bus.publish("job_progress", repository.get_agent_run(run_id) or {})


def _summarize_state(state: dict[str, Any], *, run_type: str = "pipeline") -> str:
    latest_report = state.get("latest_report") or {}
    gig_comparison = state.get("gig_comparison") or {}
    if run_type in {"marketplace_compare", "manual_compare"}:
        blueprint = gig_comparison.get("implementation_blueprint") or {}
        return (
            f"Compared {gig_comparison.get('competitor_count', 0)} competitors and recommended "
            f"'{blueprint.get('recommended_title', 'a new title')}'."
        )
    return (
        f"Optimization score {latest_report.get('optimization_score', '--')} with "
        f"{len(latest_report.get('tag_recommendations', []))} tag recommendations."
    )


def _coerce_terms(value: Any) -> list[str] | None:
    if not value:
        return None
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def _cleanup_runtime(runtime: dict[str, Any]) -> None:
    event_bus = runtime.get("event_bus")
    if event_bus is not None:
        try:
            event_bus.stop()
        except Exception:
            pass

    database_manager = runtime.get("database_manager")
    if database_manager is not None:
        try:
            database_manager.engine.dispose()
        except Exception:
            pass
