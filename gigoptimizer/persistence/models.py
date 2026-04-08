from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class GigStateORM(Base):
    __tablename__ = "gig_states"
    __table_args__ = (UniqueConstraint("gig_key", name="uq_gig_states_gig_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gig_key: Mapped[str] = mapped_column(String(120), default="primary", index=True)
    gig_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    latest_report: Mapped[dict] = mapped_column(JSON, default=dict)
    latest_state: Mapped[dict] = mapped_column(JSON, default=dict)
    gig_comparison: Mapped[dict] = mapped_column(JSON, default=dict)
    optimization_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recommended_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_tags: Mapped[list] = mapped_column(JSON, default=list)
    last_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class AgentRunORM(Base):
    __tablename__ = "agent_runs"

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    run_type: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    current_agent: Mapped[str | None] = mapped_column(String(120), nullable=True)
    current_stage: Mapped[str | None] = mapped_column(String(120), nullable=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    input_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class HITLItemORM(Base):
    __tablename__ = "hitl_items"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    agent_name: Mapped[str] = mapped_column(String(120))
    action_type: Mapped[str] = mapped_column(String(80), index=True)
    current_value: Mapped[str] = mapped_column(Text)
    proposed_value: Mapped[str] = mapped_column(Text)
    confidence_score: Mapped[int] = mapped_column(Integer)
    validator_issues: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_notes: Mapped[str] = mapped_column(Text, default="")


class CompetitorSnapshotORM(Base):
    __tablename__ = "competitor_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    gig_key: Mapped[str] = mapped_column(String(120), default="primary", index=True)
    source: Mapped[str] = mapped_column(String(60), default="marketplace")
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str] = mapped_column(Text)
    seller_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    starting_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviews_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    delivery_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    badges: Mapped[list] = mapped_column(JSON, default=list)
    snippet: Mapped[str] = mapped_column(Text, default="")
    matched_term: Mapped[str] = mapped_column(String(120), default="")
    conversion_proxy_score: Mapped[float] = mapped_column(Float, default=0.0)
    win_reasons: Mapped[list] = mapped_column(JSON, default=list)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class UserActionORM(Base):
    __tablename__ = "user_actions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    gig_id: Mapped[str] = mapped_column(String(255), index=True)
    action: Mapped[dict] = mapped_column(JSON, default=dict)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    rejected: Mapped[bool] = mapped_column(Boolean, default=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class ComparisonHistoryORM(Base):
    __tablename__ = "comparison_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gig_id: Mapped[str] = mapped_column(String(255), index=True)
    score_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_after: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class AssistantMessageORM(Base):
    __tablename__ = "assistant_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gig_id: Mapped[str] = mapped_column(String(255), index=True)
    role: Mapped[str] = mapped_column(String(24), index=True)
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(48), default="assistant")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class KnowledgeDocumentORM(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (UniqueConstraint("gig_id", "checksum", name="uq_knowledge_documents_gig_checksum"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    gig_id: Mapped[str] = mapped_column(String(255), index=True)
    filename: Mapped[str] = mapped_column(Text)
    stored_path: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(48), default="upload")
    status: Mapped[str] = mapped_column(String(32), default="ready", index=True)
    preview: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class KnowledgeChunkORM(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = (UniqueConstraint("document_id", "chunk_index", name="uq_knowledge_chunks_document_index"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    document_id: Mapped[str] = mapped_column(String(64), index=True)
    gig_id: Mapped[str] = mapped_column(String(255), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)


class FeedSourceORM(Base):
    __tablename__ = "content_feed_sources"
    __table_args__ = (UniqueConstraint("slug", name="uq_content_feed_sources_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), default="manga", index=True)
    feed_url: Mapped[str] = mapped_column(Text)
    site_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(24), default="en")
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    fetch_interval_minutes: Mapped[int] = mapped_column(Integer, default=30)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class FeedEntryORM(Base):
    __tablename__ = "content_feed_entries"
    __table_args__ = (
        UniqueConstraint("external_id", name="uq_content_feed_entries_external_id"),
        UniqueConstraint("slug", name="uq_content_feed_entries_slug"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_slug: Mapped[str] = mapped_column(String(120), index=True)
    category: Mapped[str] = mapped_column(String(40), default="manga", index=True)
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    slug: Mapped[str] = mapped_column(String(180), index=True)
    title: Mapped[str] = mapped_column(Text)
    canonical_url: Mapped[str] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_html: Mapped[str] = mapped_column(Text, default="")
    summary_text: Mapped[str] = mapped_column(Text, default="")
    content_html: Mapped[str] = mapped_column(Text, default="")
    content_text: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)


class FeedSyncRunORM(Base):
    __tablename__ = "content_feed_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope: Mapped[str] = mapped_column(String(120), default="all", index=True)
    status: Mapped[str] = mapped_column(String(32), default="completed", index=True)
    total_sources: Mapped[int] = mapped_column(Integer, default=0)
    total_entries: Mapped[int] = mapped_column(Integer, default=0)
    total_new_entries: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
