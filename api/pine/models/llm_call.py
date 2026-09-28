"""LLMCall model (ARCHITECTURE §4/§10).

One row per provider call (or cache hit) for token accounting, caching and
audit. `request_hash` is sha256(model + messages + schema); when
`LLM_CACHE=1` a repeated request returns the stored `response` instead of
calling the provider again, and the new row records `cache_hit=True`.

Deviation: `agent_run_id` is a plain indexed string — the `agent_run` table
lands with the agent loop in P5; wiring the FK would require the table first.
"""

from typing import Any

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from pine.db import Base
from pine.models.base import TimestampMixin, new_id


class LLMCall(TimestampMixin, Base):
    __tablename__ = "llm_call"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    agent_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    deal_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("deal.id"), nullable=True
    )
    purpose: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(60), nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cache_hit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("ix_llm_call_agent_run_id", "agent_run_id"),
        Index("ix_llm_call_deal_id", "deal_id"),
        Index("ix_llm_call_request_hash", "request_hash"),
    )
