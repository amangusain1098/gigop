from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, JSON, String, Text, UniqueConstraint
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
