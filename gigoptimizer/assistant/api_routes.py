"""FastAPI router exposing the GigOptimizer AI assistant.

This module wires the ``AIAssistant`` class to a small set of HTTP endpoints
under ``/api/assistant/*``. The router is created by
:func:`build_assistant_router` and can be mounted onto any ``FastAPI`` app.

All endpoints return JSON and never raise unless the input is malformed; on
LLM failure the assistant's deterministic fallback kicks in and the response
is still a valid envelope.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

try:
    from fastapi import APIRouter, Body, Depends, HTTPException
except Exception:  # pragma: no cover - allows import without fastapi installed
    APIRouter = None  # type: ignore[assignment]
    Body = None  # type: ignore[assignment]
    Depends = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment]

from .assistant import AIAssistant
from .client import LLMClient, build_default_client
from ..connectors.pagespeed import PageSpeedConnector
from .training import AssistantTrainer

logger = logging.getLogger(__name__)


def _coerce_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return [value]


def build_assistant(
    *,
    provider: str | None = None,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    client: LLMClient | None = None,
) -> AIAssistant:
    """Build an :class:`AIAssistant` using env-aware defaults."""

    if client is None:
        client = build_default_client(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
    return AIAssistant(client=client)


def build_assistant_router(
    *,
    assistant: AIAssistant | None = None,
    trainer: AssistantTrainer | None = None,
    data_dir: str | Path | None = None,
    repository: Any | None = None,
    rag_index: Any | None = None,
    auth_dependency: Any | None = None,
    csrf_dependency: Any | None = None,
) -> "APIRouter":
    """Return a ``FastAPI`` ``APIRouter`` exposing the assistant endpoints.

    Parameters
    ----------
    assistant:
        Optional pre-built assistant. If omitted we build one via
        :func:`build_assistant`.
    trainer:
        Optional pre-built trainer. If omitted one is built when ``data_dir``
        is provided.
    data_dir:
        Directory to place training artifacts under. Required if ``trainer``
        is not provided and the ``/train`` endpoint should work.
    repository:
        Optional repository passed to the trainer for dataset export.
    auth_dependency, csrf_dependency:
        Optional FastAPI ``Depends`` callables the host app wants us to
        enforce. Each endpoint wraps them if provided.
    """

    if APIRouter is None:  # pragma: no cover - fastapi missing
        raise RuntimeError(
            "fastapi is required to build the assistant router - install fastapi first"
        )

    assistant = assistant or build_assistant()
    if trainer is None and data_dir is not None:
        trainer = AssistantTrainer(data_dir=data_dir, repository=repository)
    if rag_index is not None and getattr(assistant, "rag_index", None) is None:
        assistant.rag_index = rag_index

    router = APIRouter(prefix="/api/assistant", tags=["assistant"])

    def _guard() -> list[Any]:
        deps: list[Any] = []
        if auth_dependency is not None:
            deps.append(Depends(auth_dependency))
        if csrf_dependency is not None:
            deps.append(Depends(csrf_dependency))
        return deps

    guarded = _guard()

    # ------------------------------------------------------------------
    # /ask
    # ------------------------------------------------------------------
    @router.post("/ask", dependencies=guarded)
    async def ask_endpoint(payload: dict = Body(...)) -> dict:
        question = str(payload.get("question") or "").strip()
        if not question:
            raise HTTPException(status_code=400, detail="'question' is required")
        context = payload.get("context")
        envelope = assistant.ask(question, context=context)
        return {"envelope": envelope.to_dict()}

    # ------------------------------------------------------------------
    # /optimize-gig
    # ------------------------------------------------------------------
    @router.post("/optimize-gig", dependencies=guarded)
    async def optimize_gig_endpoint(payload: dict = Body(...)) -> dict:
        current_gig = payload.get("current_gig") or payload.get("gig")
        if not isinstance(current_gig, dict):
            raise HTTPException(
                status_code=400, detail="'current_gig' object is required"
            )
        competitors = _coerce_list(payload.get("competitor_gigs") or payload.get("competitors"))
        keywords = [str(k) for k in _coerce_list(payload.get("target_keywords"))]
        envelope, result = assistant.optimize_gig(
            current_gig=current_gig,
            competitor_gigs=competitors,
            target_keywords=keywords,
        )
        return {"envelope": envelope.to_dict(), "result": result.to_dict()}

    # ------------------------------------------------------------------
    # /audit-website
    # ------------------------------------------------------------------
    @router.post("/audit-website", dependencies=guarded)
    async def audit_website_endpoint(payload: dict = Body(...)) -> dict:
        url = payload.get("url")
        copy_block = payload.get("copy") or payload.get("content")
        keywords = [str(k) for k in _coerce_list(payload.get("target_keywords"))]
        try:
            envelope, result = assistant.audit_website(
                url=url,
                copy_sample=copy_block,
                target_keywords=keywords,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        pagespeed = PageSpeedConnector().fetch(str(url or ""))
        return {"envelope": envelope.to_dict(), "result": result.to_dict(), "pagespeed": pagespeed}

    # ------------------------------------------------------------------
    # /generate-content
    # ------------------------------------------------------------------
    @router.post("/generate-content", dependencies=guarded)
    async def generate_content_endpoint(payload: dict = Body(...)) -> dict:
        topic = str(payload.get("topic") or "").strip()
        if not topic:
            raise HTTPException(status_code=400, detail="'topic' is required")
        platform = str(payload.get("platform") or "twitter")
        count = int(payload.get("count") or 3)
        audience = payload.get("audience")
        envelope, result = assistant.generate_content(
            topic=topic,
            platform=platform,
            count=max(1, min(20, count)),
            audience=audience,
        )
        return {"envelope": envelope.to_dict(), "result": result.to_dict()}

    # ------------------------------------------------------------------
    # /improve
    # ------------------------------------------------------------------
    @router.post("/improve", dependencies=guarded)
    async def improve_endpoint(payload: dict = Body(...)) -> dict:
        original = str(payload.get("original_output") or payload.get("output") or "").strip()
        if not original:
            raise HTTPException(
                status_code=400, detail="'original_output' is required"
            )
        keywords = [str(k) for k in _coerce_list(payload.get("target_keywords"))]
        audience = payload.get("audience")
        envelope, result = assistant.improve_output(
            original_output=original,
            target_keywords=keywords,
            audience=audience,
        )
        return {"envelope": envelope.to_dict(), "result": result.to_dict()}

    # ------------------------------------------------------------------
    # /self-audit
    # ------------------------------------------------------------------
    @router.post("/self-audit", dependencies=guarded)
    async def self_audit_endpoint(payload: dict = Body(default={})) -> dict:
        snapshot = payload.get("product_snapshot") or payload.get("snapshot") or {}
        if not isinstance(snapshot, dict):
            raise HTTPException(
                status_code=400, detail="'product_snapshot' must be an object"
            )
        envelope, result = assistant.self_audit(product_snapshot=snapshot)
        return {"envelope": envelope.to_dict(), "result": result.to_dict()}

    # ------------------------------------------------------------------
    # /train
    # ------------------------------------------------------------------
    @router.post("/train", dependencies=guarded)
    async def train_endpoint(payload: dict = Body(default={})) -> dict:
        if trainer is None:
            raise HTTPException(
                status_code=503,
                detail="Training is not configured on this server (no data_dir).",
            )
        try:
            report = trainer.train()
        except Exception as exc:  # noqa: BLE001 - surface as 500
            logger.exception("assistant training failed")
            raise HTTPException(status_code=500, detail=f"Training failed: {exc}") from exc
        return {"report": report.to_dict()}

    # ------------------------------------------------------------------
    # /status
    # ------------------------------------------------------------------
    @router.get("/status", dependencies=guarded)
    async def status_endpoint() -> dict:
        return {
            "provider": getattr(assistant.client, "name", "unknown"),
            "model": getattr(assistant.client, "model", "unknown"),
            "has_trainer": trainer is not None,
            "features": [
                "ask",
                "optimize_gig",
                "audit_website",
                "generate_content",
                "improve",
                "self_audit",
                "train",
            ],
        }

    return router


__all__ = ["build_assistant", "build_assistant_router"]
