from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Callable
from typing import Any

from ..config import GigOptimizerConfig
from ..persistence import BlueprintRepository
from ..services.cache_service import CacheService
from .bus import JobEventBus
from . import tasks


class JobService:
    def __init__(
        self,
        config: GigOptimizerConfig,
        repository: BlueprintRepository,
        event_bus: JobEventBus,
        cache_service: CacheService | None = None,
    ) -> None:
        self.config = config
        self.repository = repository
        self.event_bus = event_bus
        self.cache_service = cache_service
        self._threads: dict[str, threading.Thread] = {}
        self._rq_available = self._detect_rq()

    def enqueue_pipeline(self, *, use_live_connectors: bool = False) -> dict[str, Any]:
        run = self.repository.create_agent_run(
            run_type="pipeline",
            input_payload={"use_live_connectors": use_live_connectors},
            status="queued",
        )
        self._dispatch(
            run,
            lambda: tasks.run_pipeline_job(
                run["run_id"],
                use_live_connectors=use_live_connectors,
            ),
        )
        return self.repository.get_agent_run(run["run_id"]) or run

    def enqueue_marketplace_compare(
        self,
        *,
        gig_url: str,
        search_terms: list[str] | None = None,
    ) -> dict[str, Any]:
        dedupe_key = self._marketplace_dedupe_key("marketplace_compare", gig_url=gig_url, search_terms=search_terms)
        existing = self._existing_deduped_run(dedupe_key)
        if existing is not None:
            return existing
        run = self.repository.create_agent_run(
            run_type="marketplace_compare",
            input_payload={
                "gig_url": gig_url,
                "search_terms": search_terms or [],
                "dedupe_key": dedupe_key,
            },
            status="queued",
        )
        self._store_dedupe_run(dedupe_key, run["run_id"])
        self._dispatch(
            run,
            lambda: tasks.run_marketplace_compare_job(
                run["run_id"],
                gig_url=gig_url,
                search_terms=search_terms,
            ),
        )
        return self.repository.get_agent_run(run["run_id"]) or run

    def enqueue_manual_compare(
        self,
        *,
        gig_url: str,
        competitor_input: str,
        search_terms: list[str] | None = None,
    ) -> dict[str, Any]:
        dedupe_key = self._marketplace_dedupe_key(
            "manual_compare",
            gig_url=gig_url,
            search_terms=search_terms,
            extra={"competitor_input": competitor_input[:500]},
        )
        existing = self._existing_deduped_run(dedupe_key)
        if existing is not None:
            return existing
        run = self.repository.create_agent_run(
            run_type="manual_compare",
            input_payload={
                "gig_url": gig_url,
                "search_terms": search_terms or [],
                "competitor_input": competitor_input,
                "dedupe_key": dedupe_key,
            },
            status="queued",
        )
        self._store_dedupe_run(dedupe_key, run["run_id"])
        self._dispatch(
            run,
            lambda: tasks.run_manual_compare_job(
                run["run_id"],
                gig_url=gig_url,
                competitor_input=competitor_input,
                search_terms=search_terms,
            ),
        )
        return self.repository.get_agent_run(run["run_id"]) or run

    def enqueue_marketplace_scrape(
        self,
        *,
        gig_url: str = "",
        search_terms: list[str] | None = None,
    ) -> dict[str, Any]:
        dedupe_key = self._marketplace_dedupe_key("marketplace_scrape", gig_url=gig_url, search_terms=search_terms)
        existing = self._existing_deduped_run(dedupe_key)
        if existing is not None:
            return existing
        run = self.repository.create_agent_run(
            run_type="marketplace_scrape",
            input_payload={
                "gig_url": gig_url,
                "search_terms": search_terms or [],
                "dedupe_key": dedupe_key,
            },
            status="queued",
        )
        self._store_dedupe_run(dedupe_key, run["run_id"])
        self._dispatch(
            run,
            lambda: tasks.run_marketplace_scrape_job(run["run_id"], search_terms=search_terms),
        )
        return self.repository.get_agent_run(run["run_id"]) or run

    def enqueue_weekly_report(self, *, use_live_connectors: bool = False) -> dict[str, Any]:
        run = self.repository.create_agent_run(
            run_type="weekly_report",
            input_payload={"use_live_connectors": use_live_connectors},
            status="queued",
        )
        self._dispatch(
            run,
            lambda: tasks.run_weekly_report_job(
                run["run_id"],
                use_live_connectors=use_live_connectors,
            ),
        )
        return self.repository.get_agent_run(run["run_id"]) or run

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self.repository.get_agent_run(run_id)

    def list_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return self.repository.list_agent_runs(limit=limit)

    def worker_snapshot(self) -> dict[str, Any]:
        if self._rq_available and self.config.redis_url and not self.config.job_queue_eager:
            worker_count = 0
            detail = "RQ/Redis mode will be active on a Linux host with REDIS_URL configured."
            try:
                from redis import Redis
                from rq import Worker

                connection = Redis.from_url(self.config.redis_url)
                worker_count = len(Worker.all(connection=connection))
                detail = f"RQ/Redis mode active with {worker_count} worker(s) registered."
            except Exception:
                worker_count = 0
            return {
                "backend": "rq",
                "mode": "distributed",
                "detail": detail,
                "worker_count": worker_count,
                "local_threads": len([thread for thread in self._threads.values() if thread.is_alive()]),
            }
        return {
            "backend": "thread",
            "mode": "local",
            "detail": "Local background thread execution is active for this environment.",
            "worker_count": len([thread for thread in self._threads.values() if thread.is_alive()]),
            "local_threads": len([thread for thread in self._threads.values() if thread.is_alive()]),
        }

    def _dispatch(self, run: dict[str, Any], local_runner: Callable[[], Any]) -> None:
        run_id = run["run_id"]
        if self._rq_available and self.config.redis_url and not self.config.job_queue_eager:
            try:
                from redis import Redis
                from rq import Queue
            except Exception:
                self._start_local_thread(run_id, local_runner)
                return
            try:
                connection = Redis.from_url(self.config.redis_url)
                queue = Queue(self.config.rq_queue_name, connection=connection)
                job = queue.enqueue(
                    "gigoptimizer.jobs.tasks.run_job_dispatch",
                    run_id,
                    run.get("run_type", "pipeline"),
                    run.get("input_payload", {}) or {},
                )
                self.repository.update_agent_run(run_id, job_id=job.id)
                return
            except Exception:
                self._start_local_thread(run_id, local_runner)
                return
        self._start_local_thread(run_id, local_runner)

    def _start_local_thread(self, run_id: str, runner: Callable[[], Any]) -> None:
        thread = threading.Thread(target=runner, daemon=True, name=f"gigoptimizer-{run_id[:8]}")
        self._threads[run_id] = thread
        thread.start()

    def _detect_rq(self) -> bool:
        if os.name == "nt":
            return False
        try:
            import rq  # noqa: F401
        except Exception:
            return False
        return True

    def _marketplace_dedupe_key(
        self,
        run_type: str,
        *,
        gig_url: str,
        search_terms: list[str] | None,
        extra: dict[str, Any] | None = None,
    ) -> str:
        payload = {
            "run_type": run_type,
            "gig_url": str(gig_url or "").strip(),
            "search_terms": [str(item).strip().lower() for item in (search_terms or []) if str(item).strip()],
            "extra": extra or {},
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        return f"gigoptimizer:job:active:{digest}"

    def _existing_deduped_run(self, dedupe_key: str) -> dict[str, Any] | None:
        if self.cache_service is None:
            return None
        payload = self.cache_service.get_json(dedupe_key)
        if not isinstance(payload, dict):
            return None
        run_id = str(payload.get("run_id", "")).strip()
        if not run_id:
            return None
        run = self.repository.get_agent_run(run_id)
        if run is None or run.get("status") not in {"queued", "running"}:
            self.cache_service.delete(dedupe_key)
            return None
        return run

    def _store_dedupe_run(self, dedupe_key: str, run_id: str) -> None:
        if self.cache_service is None:
            return
        stored = self.cache_service.set_json_if_absent(
            dedupe_key,
            {"run_id": run_id},
            ttl_seconds=10 * 60,
        )
        if not stored:
            self.cache_service.set_json(
                dedupe_key,
                {"run_id": run_id},
                ttl_seconds=10 * 60,
            )
