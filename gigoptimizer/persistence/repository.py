from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, select

from ..models import ApprovalRecord, MarketplaceGig, ValidationIssue
from ..utils import build_gig_key
from .database import DatabaseManager
from .models import (
    AgentRunORM,
    AssistantMessageORM,
    ComparisonHistoryORM,
    CompetitorSnapshotORM,
    FeedEntryORM,
    FeedSourceORM,
    FeedSyncRunORM,
    GigStateORM,
    HITLItemORM,
    KnowledgeChunkORM,
    KnowledgeDocumentORM,
    LoginAttemptORM,
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

    def count_recent_failed_login_attempts(self, *, client_key: str, window_minutes: int = 30) -> int:
        cutoff = utc_now() - timedelta(minutes=max(1, window_minutes))
        with self.database.session() as session:
            latest_success_at = session.scalar(
                select(LoginAttemptORM.created_at)
                .where(LoginAttemptORM.client_key == client_key)
                .where(LoginAttemptORM.success.is_(True))
                .order_by(LoginAttemptORM.created_at.desc())
                .limit(1)
            )
            if latest_success_at is not None and latest_success_at.tzinfo is None:
                latest_success_at = latest_success_at.replace(tzinfo=timezone.utc)
            effective_cutoff = max(cutoff, latest_success_at) if latest_success_at is not None else cutoff
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(LoginAttemptORM)
                    .where(LoginAttemptORM.client_key == client_key)
                    .where(LoginAttemptORM.success.is_(False))
                    .where(LoginAttemptORM.created_at >= effective_cutoff)
                )
                or 0
            )

    def clear_failed_login_attempts(self, *, client_key: str) -> None:
        with self.database.session() as session:
            session.execute(
                delete(LoginAttemptORM)
                .where(LoginAttemptORM.client_key == client_key)
                .where(LoginAttemptORM.success.is_(False))
            )

    def record_login_attempt(
        self,
        *,
        username: str,
        client_key: str,
        remote_addr: str = "",
        user_agent: str = "",
        success: bool = False,
        failure_count: int = 1,
        capture_required: bool = False,
        capture_status: str = "not_requested",
    ) -> dict[str, Any]:
        attempt_id = uuid.uuid4().hex
        with self.database.session() as session:
            item = LoginAttemptORM(
                id=attempt_id,
                username=str(username).strip(),
                client_key=str(client_key).strip(),
                remote_addr=str(remote_addr).strip(),
                user_agent=str(user_agent).strip(),
                success=success,
                failure_count=(max(0, int(failure_count or 0)) if success else max(1, int(failure_count or 1))),
                capture_required=capture_required,
                capture_status=str(capture_status).strip() or "not_requested",
            )
            session.add(item)
        return self.get_login_attempt(attempt_id) or {}

    def get_login_attempt(self, attempt_id: str) -> dict[str, Any] | None:
        with self.database.session() as session:
            item = session.get(LoginAttemptORM, attempt_id)
            return self._login_attempt_to_dict(item) if item is not None else None

    def attach_login_attempt_capture(
        self,
        *,
        attempt_id: str,
        photo_path: str | None = None,
        photo_content_type: str | None = None,
        capture_status: str = "captured",
        capture_error: str = "",
    ) -> dict[str, Any]:
        with self.database.session() as session:
            item = session.get(LoginAttemptORM, attempt_id)
            if item is None:
                raise KeyError(attempt_id)
            item.capture_status = str(capture_status).strip() or item.capture_status
            item.capture_error = str(capture_error).strip() or None
            if photo_path:
                item.photo_path = str(photo_path).strip()
                item.photo_content_type = str(photo_content_type or "").strip() or item.photo_content_type
                item.photo_captured_at = utc_now()
            item.updated_at = utc_now()
        return self.get_login_attempt(attempt_id) or {}

    def list_login_attempts(self, *, failed_only: bool = True, limit: int = 20) -> list[dict[str, Any]]:
        with self.database.session() as session:
            query = select(LoginAttemptORM).order_by(LoginAttemptORM.created_at.desc()).limit(limit)
            if failed_only:
                query = query.where(LoginAttemptORM.success.is_(False))
            rows = session.scalars(query).all()
            return [self._login_attempt_to_dict(item) for item in rows]

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

    def ensure_feed_sources(self, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized_sources: list[dict[str, Any]] = []
        with self.database.session() as session:
            existing_map = {
                item.slug: item
                for item in session.scalars(select(FeedSourceORM)).all()
            }
            for source in sources:
                slug = str(source.get("slug", "")).strip()
                if not slug:
                    continue
                item = existing_map.get(slug)
                if item is None:
                    item = FeedSourceORM(slug=slug)
                    session.add(item)
                item.title = str(source.get("title", slug)).strip() or slug
                item.category = str(source.get("category", "manga")).strip() or "manga"
                item.feed_url = str(source.get("feed_url", "")).strip()
                item.site_url = str(source.get("site_url", "")).strip() or None
                item.language = str(source.get("language", "en")).strip() or "en"
                item.active = bool(source.get("active", True))
                item.fetch_interval_minutes = max(5, int(source.get("fetch_interval_minutes", 30) or 30))
                item.metadata_json = source.get("metadata") or {}
                item.updated_at = utc_now()
            session.flush()
            rows = session.scalars(select(FeedSourceORM).order_by(FeedSourceORM.title.asc())).all()
            normalized_sources = [self._feed_source_to_dict(item) for item in rows]
        return normalized_sources

    def list_feed_sources(self, *, active_only: bool = False, limit: int = 50) -> list[dict[str, Any]]:
        with self.database.session() as session:
            query = select(FeedSourceORM).order_by(FeedSourceORM.title.asc()).limit(limit)
            if active_only:
                query = query.where(FeedSourceORM.active.is_(True))
            rows = session.scalars(query).all()
            return [self._feed_source_to_dict(item) for item in rows]

    def update_feed_source_status(
        self,
        slug: str,
        *,
        last_error: str | None = None,
        success: bool = False,
        checked_at: datetime | None = None,
    ) -> dict[str, Any] | None:
        checked_time = checked_at or utc_now()
        with self.database.session() as session:
            item = session.scalar(select(FeedSourceORM).where(FeedSourceORM.slug == slug))
            if item is None:
                return None
            item.last_checked_at = checked_time
            item.last_error = (last_error or "").strip() or None
            if success:
                item.last_success_at = checked_time
            item.updated_at = checked_time
        with self.database.session() as session:
            item = session.scalar(select(FeedSourceORM).where(FeedSourceORM.slug == slug))
            return self._feed_source_to_dict(item) if item is not None else None

    def upsert_feed_entry(
        self,
        *,
        source_slug: str,
        category: str,
        external_id: str,
        slug: str,
        title: str,
        canonical_url: str,
        author: str = "",
        summary_html: str = "",
        summary_text: str = "",
        content_html: str = "",
        content_text: str = "",
        image_url: str = "",
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        published_at: datetime | None = None,
    ) -> tuple[dict[str, Any], bool]:
        created = False
        with self.database.session() as session:
            item = session.scalar(
                select(FeedEntryORM).where(FeedEntryORM.external_id == external_id)
            )
            if item is None:
                item = FeedEntryORM(external_id=external_id)
                session.add(item)
                created = True
            item.source_slug = source_slug
            item.category = category
            item.slug = slug
            item.title = title
            item.canonical_url = canonical_url
            item.author = author or None
            item.summary_html = summary_html
            item.summary_text = summary_text
            item.content_html = content_html
            item.content_text = content_text
            item.image_url = image_url or None
            item.tags = tags or []
            item.metadata_json = metadata or {}
            item.published_at = published_at
            item.updated_at = utc_now()
            session.flush()
            item_id = item.id
        with self.database.session() as session:
            refreshed = session.get(FeedEntryORM, item_id)
            return self._feed_entry_to_dict(refreshed), created

    def list_feed_entries(
        self,
        *,
        category: str | None = None,
        source_slug: str | None = None,
        limit: int = 60,
    ) -> list[dict[str, Any]]:
        with self.database.session() as session:
            query = (
                select(FeedEntryORM)
                .order_by(FeedEntryORM.published_at.desc(), FeedEntryORM.id.desc())
                .limit(limit)
            )
            if category:
                query = query.where(FeedEntryORM.category == category)
            if source_slug:
                query = query.where(FeedEntryORM.source_slug == source_slug)
            rows = session.scalars(query).all()
            return [self._feed_entry_to_dict(item) for item in rows]

    def get_feed_entry(self, slug: str) -> dict[str, Any] | None:
        with self.database.session() as session:
            item = session.scalar(select(FeedEntryORM).where(FeedEntryORM.slug == slug))
            return self._feed_entry_to_dict(item) if item is not None else None

    def record_feed_sync_run(
        self,
        *,
        scope: str,
        status: str,
        total_sources: int,
        total_entries: int,
        total_new_entries: int,
        error_count: int,
        result_json: dict[str, Any] | None = None,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
    ) -> dict[str, Any]:
        with self.database.session() as session:
            item = FeedSyncRunORM(
                scope=scope,
                status=status,
                total_sources=total_sources,
                total_entries=total_entries,
                total_new_entries=total_new_entries,
                error_count=error_count,
                result_json=result_json or {},
                started_at=started_at or utc_now(),
                finished_at=finished_at or utc_now(),
            )
            session.add(item)
            session.flush()
            item_id = item.id
        with self.database.session() as session:
            item = session.get(FeedSyncRunORM, item_id)
            return self._feed_sync_run_to_dict(item)

    def list_feed_sync_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self.database.session() as session:
            rows = session.scalars(
                select(FeedSyncRunORM).order_by(FeedSyncRunORM.started_at.desc()).limit(limit)
            ).all()
            return [self._feed_sync_run_to_dict(item) for item in rows]

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

    def _login_attempt_to_dict(self, item: LoginAttemptORM) -> dict[str, Any]:
        return {
            "id": item.id,
            "username": item.username,
            "client_key": item.client_key,
            "remote_addr": item.remote_addr,
            "user_agent": item.user_agent,
            "success": item.success,
            "failure_count": item.failure_count,
            "capture_required": item.capture_required,
            "capture_status": item.capture_status,
            "capture_error": item.capture_error or "",
            "photo_path": item.photo_path or "",
            "photo_content_type": item.photo_content_type or "",
            "photo_captured_at": self._iso(item.photo_captured_at),
            "created_at": self._iso(item.created_at),
            "updated_at": self._iso(item.updated_at),
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

    def _feed_source_to_dict(self, item: FeedSourceORM) -> dict[str, Any]:
        return {
            "id": item.id,
            "slug": item.slug,
            "title": item.title,
            "category": item.category,
            "feed_url": item.feed_url,
            "site_url": item.site_url or "",
            "language": item.language,
            "active": item.active,
            "fetch_interval_minutes": item.fetch_interval_minutes,
            "last_checked_at": self._iso(item.last_checked_at),
            "last_success_at": self._iso(item.last_success_at),
            "last_error": item.last_error or "",
            "metadata": item.metadata_json or {},
            "created_at": self._iso(item.created_at),
            "updated_at": self._iso(item.updated_at),
        }

    def _feed_entry_to_dict(self, item: FeedEntryORM) -> dict[str, Any]:
        return {
            "id": item.id,
            "source_slug": item.source_slug,
            "category": item.category,
            "external_id": item.external_id,
            "slug": item.slug,
            "title": item.title,
            "canonical_url": item.canonical_url,
            "author": item.author or "",
            "summary_html": item.summary_html,
            "summary_text": item.summary_text,
            "content_html": item.content_html,
            "content_text": item.content_text,
            "image_url": item.image_url or "",
            "tags": item.tags or [],
            "metadata": item.metadata_json or {},
            "published_at": self._iso(item.published_at),
            "fetched_at": self._iso(item.fetched_at),
            "updated_at": self._iso(item.updated_at),
        }

    def _feed_sync_run_to_dict(self, item: FeedSyncRunORM) -> dict[str, Any]:
        return {
            "id": item.id,
            "scope": item.scope,
            "status": item.status,
            "total_sources": item.total_sources,
            "total_entries": item.total_entries,
            "total_new_entries": item.total_new_entries,
            "error_count": item.error_count,
            "result_json": item.result_json or {},
            "started_at": self._iso(item.started_at),
            "finished_at": self._iso(item.finished_at),
        }

    def _coerce_datetime(self, value: str | datetime | None) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value))

    def _iso(self, value: datetime | None) -> str | None:
        return value.isoformat() if value is not None else None
