from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select

from ..models import ApprovalRecord, MarketplaceGig, ValidationIssue
from ..utils import build_gig_key
from .database import DatabaseManager
from .models import (
    AgentRunORM,
    AssistantMessageORM,
    ComparisonHistoryORM,
    CompetitorSnapshotORM,
    GigStateORM,
    HITLItemORM,
    KnowledgeChunkORM,
    KnowledgeDocumentORM,
    UserActionORM,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class BlueprintRepository:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database
        self.database.create_schema()

    def load_primary_state(self) -> dict[str, Any] | None:
        with self.database.session() as session:
            record = session.scalar(
                select(GigStateORM).where(GigStateORM.gig_key == "primary")
            )
            if record is None:
                return None
            return record.latest_state or {}

    def save_primary_state(
        self,
        state: dict[str, Any],
        *,
        snapshot_payload: dict[str, Any] | None = None,
        run_id: str | None = None,
    ) -> None:
        latest_report = state.get("latest_report") or {}
        gig_comparison = state.get("gig_comparison") or {}
        blueprint = gig_comparison.get("implementation_blueprint") or {}
        with self.database.session() as session:
            record = session.scalar(
                select(GigStateORM).where(GigStateORM.gig_key == "primary")
            )
            if record is None:
                record = GigStateORM(gig_key="primary")
                session.add(record)
            record.gig_url = (gig_comparison.get("gig_url") or "") or None
            record.snapshot_path = state.get("snapshot_path")
            if snapshot_payload is not None:
                record.snapshot_payload = snapshot_payload
            record.latest_state = state
            record.latest_report = latest_report
            record.gig_comparison = gig_comparison
            record.optimization_score = latest_report.get("optimization_score")
            record.recommended_title = blueprint.get("recommended_title")
            record.recommended_tags = blueprint.get("recommended_tags") or []
            record.last_run_id = run_id
            record.updated_at = utc_now()

    def create_agent_run(
        self,
        *,
        run_type: str,
        input_payload: dict[str, Any] | None = None,
        job_id: str | None = None,
        status: str = "queued",
    ) -> dict[str, Any]:
        run_id = uuid.uuid4().hex
        with self.database.session() as session:
            record = AgentRunORM(
                run_id=run_id,
                run_type=run_type,
                job_id=job_id,
                status=status,
                input_payload=input_payload or {},
                progress=0.0,
            )
            session.add(record)
        return self.get_agent_run(run_id) or {}

    def update_agent_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        current_agent: str | None = None,
        current_stage: str | None = None,
        progress: float | None = None,
        result_payload: dict[str, Any] | None = None,
        error_message: str | None = None,
        output_summary: str | None = None,
        started: bool = False,
        finished: bool = False,
        job_id: str | None = None,
    ) -> dict[str, Any]:
        with self.database.session() as session:
            record = session.get(AgentRunORM, run_id)
            if record is None:
                raise KeyError(run_id)
            if status is not None:
                record.status = status
            if current_agent is not None:
                record.current_agent = current_agent
            if current_stage is not None:
                record.current_stage = current_stage
            if progress is not None:
                record.progress = progress
            if result_payload is not None:
                record.result_payload = result_payload
            if error_message is not None:
                record.error_message = error_message
            if output_summary is not None:
                record.output_summary = output_summary
            if job_id is not None:
                record.job_id = job_id
            if started and record.started_at is None:
                record.started_at = utc_now()
            if finished:
                record.finished_at = utc_now()
        return self.get_agent_run(run_id) or {}

    def get_agent_run(self, run_id: str) -> dict[str, Any] | None:
        with self.database.session() as session:
            record = session.get(AgentRunORM, run_id)
            if record is None:
                return None
            return self._agent_run_to_dict(record)

    def list_agent_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self.database.session() as session:
            rows = session.scalars(
                select(AgentRunORM).order_by(AgentRunORM.created_at.desc()).limit(limit)
            ).all()
            return [self._agent_run_to_dict(item) for item in rows]

    def upsert_hitl_item(self, record: ApprovalRecord) -> None:
        with self.database.session() as session:
            item = session.get(HITLItemORM, record.id)
            if item is None:
                item = HITLItemORM(id=record.id)
                session.add(item)
            item.agent_name = record.agent_name
            item.action_type = record.action_type
            item.current_value = record.current_value
            item.proposed_value = record.proposed_value
            item.confidence_score = record.confidence_score
            item.validator_issues = [issue.__dict__ for issue in record.validator_issues]
            item.status = record.status
            item.reviewer_notes = record.reviewer_notes
            item.created_at = self._coerce_datetime(record.created_at)
            item.reviewed_at = self._coerce_datetime(record.reviewed_at)

    def sync_hitl_items(self, records: list[ApprovalRecord]) -> None:
        for record in records:
            self.upsert_hitl_item(record)

    def list_hitl_items(self, *, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        with self.database.session() as session:
            query = select(HITLItemORM).order_by(HITLItemORM.created_at.desc()).limit(limit)
            if status:
                query = query.where(HITLItemORM.status == status)
            rows = session.scalars(query).all()
            return [self._hitl_to_dict(item) for item in rows]

    def update_hitl_status(self, item_id: str, *, status: str, reviewer_notes: str = "") -> dict[str, Any]:
        with self.database.session() as session:
            item = session.get(HITLItemORM, item_id)
            if item is None:
                raise KeyError(item_id)
            item.status = status
            item.reviewer_notes = reviewer_notes
            item.reviewed_at = utc_now()
        with self.database.session() as session:
            item = session.get(HITLItemORM, item_id)
            return self._hitl_to_dict(item)

    def replace_competitor_snapshots(
        self,
        *,
        gigs: list[MarketplaceGig],
        run_id: str | None = None,
        source: str = "marketplace",
    ) -> None:
        with self.database.session() as session:
            session.execute(
                delete(CompetitorSnapshotORM).where(CompetitorSnapshotORM.gig_key == "primary")
            )
            for gig in gigs:
                session.add(
                    CompetitorSnapshotORM(
                        run_id=run_id,
                        gig_key="primary",
                        source=source,
                        url=gig.url or None,
                        title=gig.title,
                        seller_name=gig.seller_name or None,
                        starting_price=gig.starting_price,
                        rating=gig.rating,
                        reviews_count=gig.reviews_count,
                        delivery_days=gig.delivery_days,
                        badges=gig.badges,
                        snippet=gig.snippet,
                        matched_term=gig.matched_term,
                        conversion_proxy_score=gig.conversion_proxy_score,
                        win_reasons=gig.win_reasons,
                    )
                )

    def list_competitor_snapshots(self, *, limit: int = 40) -> list[dict[str, Any]]:
        with self.database.session() as session:
            rows = session.scalars(
                select(CompetitorSnapshotORM)
                .where(CompetitorSnapshotORM.gig_key == "primary")
                .order_by(CompetitorSnapshotORM.captured_at.desc(), CompetitorSnapshotORM.id.desc())
                .limit(limit)
            ).all()
            return [self._competitor_to_dict(item) for item in rows]

    def last_successful_run(self, run_type: str | None = None) -> dict[str, Any] | None:
        with self.database.session() as session:
            query = select(AgentRunORM).where(AgentRunORM.status == "completed")
            if run_type:
                query = query.where(AgentRunORM.run_type == run_type)
            query = query.order_by(AgentRunORM.finished_at.desc())
            item = session.scalar(query)
            return self._agent_run_to_dict(item) if item is not None else None

    def record_user_action(
        self,
        *,
        gig_id: str,
        action: dict[str, Any],
        approved: bool = False,
        rejected: bool = False,
    ) -> dict[str, Any]:
        item_id = uuid.uuid4().hex
        normalized_gig_id = build_gig_key(gig_id)
        with self.database.session() as session:
            item = UserActionORM(
                id=item_id,
                gig_id=normalized_gig_id,
                action=action,
                approved=approved,
                rejected=rejected,
            )
            session.add(item)
        return self.get_user_action(item_id) or {}

    def get_user_action(self, action_id: str) -> dict[str, Any] | None:
        with self.database.session() as session:
            item = session.get(UserActionORM, action_id)
            return self._user_action_to_dict(item) if item is not None else None

    def list_user_actions(self, *, gig_id: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
        with self.database.session() as session:
            query = select(UserActionORM).order_by(UserActionORM.timestamp.desc()).limit(limit)
            if gig_id:
                query = query.where(UserActionORM.gig_id == build_gig_key(gig_id))
            rows = session.scalars(query).all()
            return [self._user_action_to_dict(item) for item in rows]

    def record_comparison_history(
        self,
        *,
        gig_id: str,
        score_before: int | None,
        score_after: int | None,
        result_json: dict[str, Any],
    ) -> dict[str, Any]:
        normalized_gig_id = build_gig_key(gig_id)
        with self.database.session() as session:
            item = ComparisonHistoryORM(
                gig_id=normalized_gig_id,
                score_before=score_before,
                score_after=score_after,
                result_json=result_json,
            )
            session.add(item)
        return self.latest_comparison_history(gig_id=normalized_gig_id) or {}

    def latest_comparison_history(self, *, gig_id: str | None = None) -> dict[str, Any] | None:
        rows = self.list_comparison_history(gig_id=gig_id, limit=1)
        return rows[0] if rows else None

    def list_comparison_history(self, *, gig_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        with self.database.session() as session:
            query = select(ComparisonHistoryORM).order_by(ComparisonHistoryORM.created_at.desc()).limit(limit)
            if gig_id:
                query = query.where(ComparisonHistoryORM.gig_id == build_gig_key(gig_id))
            rows = session.scalars(query).all()
            return [self._comparison_history_to_dict(item) for item in rows]

    def record_assistant_message(
        self,
        *,
        gig_id: str,
        role: str,
        content: str,
        source: str = "assistant",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_gig_id = build_gig_key(gig_id)
        with self.database.session() as session:
            item = AssistantMessageORM(
                gig_id=normalized_gig_id,
                role=str(role).strip() or "assistant",
                content=str(content).strip(),
                source=str(source).strip() or "assistant",
                metadata_json=metadata or {},
            )
            session.add(item)
        return self.latest_assistant_message(gig_id=normalized_gig_id) or {}

    def latest_assistant_message(self, *, gig_id: str | None = None) -> dict[str, Any] | None:
        rows = self.list_assistant_messages(gig_id=gig_id, limit=1)
        return rows[0] if rows else None

    def list_assistant_messages(self, *, gig_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        with self.database.session() as session:
            query = select(AssistantMessageORM).order_by(AssistantMessageORM.created_at.desc()).limit(limit)
            if gig_id:
                query = query.where(AssistantMessageORM.gig_id == build_gig_key(gig_id))
            rows = session.scalars(query).all()
            return [self._assistant_message_to_dict(item) for item in rows]

    def find_knowledge_document_by_checksum(self, *, gig_id: str, checksum: str) -> dict[str, Any] | None:
        normalized_gig_id = build_gig_key(gig_id)
        with self.database.session() as session:
            query = (
                select(KnowledgeDocumentORM)
                .where(KnowledgeDocumentORM.gig_id == normalized_gig_id)
                .where(KnowledgeDocumentORM.checksum == checksum)
            )
            item = session.scalar(query)
            return self._knowledge_document_to_dict(item) if item is not None else None

    def upsert_knowledge_document(
        self,
        *,
        document_id: str,
        gig_id: str,
        filename: str,
        stored_path: str,
        content_type: str,
        size_bytes: int,
        checksum: str,
        preview: str,
        metadata: dict[str, Any] | None = None,
        source: str = "upload",
        status: str = "ready",
    ) -> dict[str, Any]:
        normalized_gig_id = build_gig_key(gig_id)
        with self.database.session() as session:
            item = session.get(KnowledgeDocumentORM, document_id)
            if item is None:
                item = KnowledgeDocumentORM(id=document_id)
                session.add(item)
            item.gig_id = normalized_gig_id
            item.filename = filename
            item.stored_path = stored_path
            item.content_type = content_type
            item.size_bytes = size_bytes
            item.checksum = checksum
            item.preview = preview
            item.metadata_json = metadata or {}
            item.source = source
            item.status = status
            item.updated_at = utc_now()
        return self.get_knowledge_document(document_id) or {}

    def replace_knowledge_chunks(
        self,
        *,
        document_id: str,
        gig_id: str,
        chunks: list[dict[str, Any]],
    ) -> None:
        normalized_gig_id = build_gig_key(gig_id)
        with self.database.session() as session:
            session.execute(
                delete(KnowledgeChunkORM).where(KnowledgeChunkORM.document_id == document_id)
            )
            for index, chunk in enumerate(chunks):
                content = str(chunk.get("content", "")).strip()
                if not content:
                    continue
                session.add(
                    KnowledgeChunkORM(
                        document_id=document_id,
                        gig_id=normalized_gig_id,
                        chunk_index=int(chunk.get("chunk_index", index)),
                        content=content,
                        char_count=int(chunk.get("char_count", len(content))),
                        metadata_json=chunk.get("metadata") or {},
                    )
                )

    def get_knowledge_document(self, document_id: str) -> dict[str, Any] | None:
        with self.database.session() as session:
            item = session.get(KnowledgeDocumentORM, document_id)
            return self._knowledge_document_to_dict(item) if item is not None else None

    def list_knowledge_documents(self, *, gig_id: str | None = None, limit: int = 25) -> list[dict[str, Any]]:
        with self.database.session() as session:
            query = select(KnowledgeDocumentORM).order_by(KnowledgeDocumentORM.created_at.desc()).limit(limit)
            if gig_id:
                query = query.where(KnowledgeDocumentORM.gig_id == build_gig_key(gig_id))
            rows = session.scalars(query).all()
            return [self._knowledge_document_to_dict(item) for item in rows]

    def list_knowledge_chunks(
        self,
        *,
        gig_id: str | None = None,
        document_id: str | None = None,
        limit: int = 250,
    ) -> list[dict[str, Any]]:
        with self.database.session() as session:
            query = select(KnowledgeChunkORM).order_by(KnowledgeChunkORM.created_at.desc()).limit(limit)
            if gig_id:
                query = query.where(KnowledgeChunkORM.gig_id == build_gig_key(gig_id))
            if document_id:
                query = query.where(KnowledgeChunkORM.document_id == document_id)
            rows = session.scalars(query).all()
            return [self._knowledge_chunk_to_dict(item) for item in rows]

    def delete_knowledge_document(self, document_id: str) -> dict[str, Any] | None:
        existing = self.get_knowledge_document(document_id)
        if existing is None:
            return None
        with self.database.session() as session:
            session.execute(
                delete(KnowledgeChunkORM).where(KnowledgeChunkORM.document_id == document_id)
            )
            session.execute(
                delete(KnowledgeDocumentORM).where(KnowledgeDocumentORM.id == document_id)
            )
        return existing

    def _agent_run_to_dict(self, item: AgentRunORM) -> dict[str, Any]:
        return {
            "run_id": item.run_id,
            "job_id": item.job_id,
            "run_type": item.run_type,
            "status": item.status,
            "current_agent": item.current_agent,
            "current_stage": item.current_stage,
            "progress": item.progress,
            "input_payload": item.input_payload or {},
            "result_payload": item.result_payload or {},
            "error_message": item.error_message or "",
            "output_summary": item.output_summary or "",
            "created_at": self._iso(item.created_at),
            "started_at": self._iso(item.started_at),
            "finished_at": self._iso(item.finished_at),
        }

    def _hitl_to_dict(self, item: HITLItemORM) -> dict[str, Any]:
        return {
            "id": item.id,
            "agent_name": item.agent_name,
            "action_type": item.action_type,
            "current_value": item.current_value,
            "proposed_value": item.proposed_value,
            "confidence_score": item.confidence_score,
            "validator_issues": item.validator_issues or [],
            "status": item.status,
            "created_at": self._iso(item.created_at),
            "reviewed_at": self._iso(item.reviewed_at),
            "reviewer_notes": item.reviewer_notes,
        }

    def _competitor_to_dict(self, item: CompetitorSnapshotORM) -> dict[str, Any]:
        return {
            "id": item.id,
            "run_id": item.run_id,
            "source": item.source,
            "url": item.url or "",
            "title": item.title,
            "seller_name": item.seller_name or "",
            "starting_price": item.starting_price,
            "rating": item.rating,
            "reviews_count": item.reviews_count,
            "delivery_days": item.delivery_days,
            "badges": item.badges or [],
            "snippet": item.snippet,
            "matched_term": item.matched_term,
            "conversion_proxy_score": item.conversion_proxy_score,
            "win_reasons": item.win_reasons or [],
            "captured_at": self._iso(item.captured_at),
        }

    def _user_action_to_dict(self, item: UserActionORM) -> dict[str, Any]:
        return {
            "id": item.id,
            "gig_id": item.gig_id,
            "action": item.action or {},
            "approved": item.approved,
            "rejected": item.rejected,
            "timestamp": self._iso(item.timestamp),
        }

    def _comparison_history_to_dict(self, item: ComparisonHistoryORM) -> dict[str, Any]:
        return {
            "id": item.id,
            "gig_id": item.gig_id,
            "score_before": item.score_before,
            "score_after": item.score_after,
            "result_json": item.result_json or {},
            "created_at": self._iso(item.created_at),
        }

    def _assistant_message_to_dict(self, item: AssistantMessageORM) -> dict[str, Any]:
        return {
            "id": item.id,
            "gig_id": item.gig_id,
            "role": item.role,
            "content": item.content,
            "source": item.source,
            "metadata": item.metadata_json or {},
            "created_at": self._iso(item.created_at),
        }

    def _knowledge_document_to_dict(self, item: KnowledgeDocumentORM) -> dict[str, Any]:
        return {
            "id": item.id,
            "gig_id": item.gig_id,
            "filename": item.filename,
            "stored_path": item.stored_path,
            "content_type": item.content_type,
            "size_bytes": item.size_bytes,
            "checksum": item.checksum,
            "source": item.source,
            "status": item.status,
            "preview": item.preview,
            "metadata": item.metadata_json or {},
            "created_at": self._iso(item.created_at),
            "updated_at": self._iso(item.updated_at),
        }

    def _knowledge_chunk_to_dict(self, item: KnowledgeChunkORM) -> dict[str, Any]:
        return {
            "id": item.id,
            "document_id": item.document_id,
            "gig_id": item.gig_id,
            "chunk_index": item.chunk_index,
            "content": item.content,
            "char_count": item.char_count,
            "metadata": item.metadata_json or {},
            "created_at": self._iso(item.created_at),
        }

    def _coerce_datetime(self, value: str | datetime | None) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

    def _iso(self, value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None
