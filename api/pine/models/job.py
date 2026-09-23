from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pine.db import Base
from pine.models.base import TimestampMixin, new_id, utcnow


class JobKind(StrEnum):
    parse_document = "parse_document"
    classify_document = "classify_document"
    index_deal = "index_deal"
    extract_facts = "extract_facts"
    build_graph = "build_graph"
    detect_contradictions = "detect_contradictions"
    run_pipeline = "run_pipeline"
    generate_output = "generate_output"


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


# Per-kind execution timeouts (ARCHITECTURE §9).
JOB_TIMEOUTS_SECONDS: dict[JobKind, int] = {
    JobKind.parse_document: 10 * 60,
    JobKind.classify_document: 2 * 60,
    JobKind.index_deal: 30 * 60,
    JobKind.extract_facts: 30 * 60,
    JobKind.build_graph: 10 * 60,
    JobKind.detect_contradictions: 2 * 60,
    JobKind.run_pipeline: 40 * 60,
    JobKind.generate_output: 5 * 60,
}

STALE_LOCK_MINUTES = 15


class Job(TimestampMixin, Base):
    __tablename__ = "job"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    deal_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("deal.id"), nullable=True, index=True
    )
    kind: Mapped[JobKind] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        String(20), default=JobStatus.queued, nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    locked_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(120), unique=True, nullable=True
    )

    __table_args__ = (Index("ix_job_status_run_after", "status", "run_after"),)
