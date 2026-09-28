"""Recorded + cached LLM calls (ARCHITECTURE §10).

`call_llm` is the single entry point for structured LLM work. Every call —
hit or miss — writes an `LLMCall` row with `request_hash =
sha256(model, messages, schema)`. When `LLM_CACHE=1` (default), a request
hash that already has a stored `response` short-circuits the provider and
the new row records `cache_hit=True`.

Cost accounting uses a small static price table; unknown models record
`cost_usd=None` (never guess a price).
"""

import hashlib
import json
import logging
import time
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from pine.config import Settings, get_settings
from pine.llm.base import LLM, Message, StructuredResult
from pine.llm.factory import get_llm, model_for
from pine.models.llm_call import LLMCall

logger = logging.getLogger(__name__)

# USD per 1M tokens (input, output) — indicative list prices, not authoritative.
_PRICE_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5": (1.25, 10.00),
    "fake-llm": (0.0, 0.0),
}


def request_hash(
    model: str, messages: list[Message], schema: type[BaseModel]
) -> str:
    """Stable hash of everything that determines the response."""
    payload = {
        "model": model,
        "messages": messages,
        "schema": schema.model_json_schema(),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()


def _cost_usd(model: str, tokens_in: int, tokens_out: int) -> float | None:
    price = _PRICE_PER_1M.get(model)
    if price is None:
        return None
    return (tokens_in * price[0] + tokens_out * price[1]) / 1_000_000


def _record(
    session: Session,
    *,
    deal_id: str | None,
    purpose: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    cache_hit: bool,
    req_hash: str,
    response: dict[str, Any] | None,
) -> LLMCall:
    row = LLMCall(
        deal_id=deal_id,
        purpose=purpose,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=_cost_usd(model, tokens_in, tokens_out),
        latency_ms=latency_ms,
        cache_hit=cache_hit,
        request_hash=req_hash,
        response=response,
    )
    session.add(row)
    session.flush()
    return row


def _cached(
    session: Session, req_hash: str, schema: type[BaseModel]
) -> LLMCall | None:
    """Most recent call with the same hash whose response was stored."""
    return session.scalar(
        select(LLMCall)
        .where(LLMCall.request_hash == req_hash)
        .where(LLMCall.response.isnot(None))
        .order_by(LLMCall.created_at.desc())
        .limit(1)
    )


async def call_llm(
    session: Session,
    *,
    purpose: str,
    messages: list[Message],
    schema: type[BaseModel],
    deal_id: str | None = None,
    model: str | None = None,
    max_output_tokens: int = 4096,
    llm: LLM | None = None,
    settings: Settings | None = None,
) -> StructuredResult:
    """Provider call with LLMCall accounting + LLM_CACHE short-circuit."""
    settings = settings or get_settings()
    model = model or model_for(purpose, settings)
    req_hash = request_hash(model, messages, schema)

    if settings.LLM_CACHE:
        hit = _cached(session, req_hash, schema)
        if hit is not None and hit.response is not None:
            parsed = schema.model_validate(hit.response)
            _record(
                session,
                deal_id=deal_id,
                purpose=purpose,
                model=model,
                tokens_in=0,
                tokens_out=0,
                latency_ms=0,
                cache_hit=True,
                req_hash=req_hash,
                response=None,
            )
            return StructuredResult(parsed=parsed, tokens_in=0, tokens_out=0)

    llm = llm or get_llm(settings)
    started = time.perf_counter()
    result = await llm.complete_structured(
        messages=messages,
        schema=schema,
        purpose=purpose,
        model=model,
        max_output_tokens=max_output_tokens,
    )
    latency_ms = int((time.perf_counter() - started) * 1000)
    _record(
        session,
        deal_id=deal_id,
        purpose=purpose,
        model=model,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
        latency_ms=latency_ms,
        cache_hit=False,
        req_hash=req_hash,
        response=(
            result.parsed.model_dump(mode="json") if settings.LLM_CACHE else None
        ),
    )
    return result
