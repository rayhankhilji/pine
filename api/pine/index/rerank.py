"""Optional reranking of fused candidates (ARCHITECTURE §10, F-03).

`none` keeps RRF order; `llm` asks the configured LLM provider for a listwise
ranking over at most MAX_CANDIDATES hits; `cross-encoder` scores pairs with
sentence-transformers (optional extra — falls back to `none` when missing).
"""

import asyncio
import logging
from typing import Protocol, runtime_checkable

import numpy as np
from pydantic import BaseModel

from pine.config import Settings, get_settings
from pine.index.retrieval import SearchHit
from pine.llm.base import LLM, Message

logger = logging.getLogger(__name__)

MAX_CANDIDATES = 25
_CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

_SNIPPET_CHARS = 600


class RerankResult(BaseModel):
    """Listwise ranking: 1-based candidate positions, best first."""

    ranking: list[int]


@runtime_checkable
class Reranker(Protocol):
    def rerank(self, query: str, hits: list[SearchHit]) -> list[SearchHit]: ...


class NoReranker:
    def rerank(self, query: str, hits: list[SearchHit]) -> list[SearchHit]:
        return hits


class LLMReranker:
    """Listwise rerank via the LLM provider's structured output (purpose=rerank)."""

    def __init__(self, llm: LLM) -> None:
        self._llm = llm

    def rerank(self, query: str, hits: list[SearchHit]) -> list[SearchHit]:
        return asyncio.run(self._rerank(query, hits))

    async def _rerank(self, query: str, hits: list[SearchHit]) -> list[SearchHit]:
        candidates = hits[:MAX_CANDIDATES]
        if not candidates:
            return hits
        lines = [
            f"{i}. [{c.filename} p{c.page_no}] {c.text[:_SNIPPET_CHARS]}"
            for i, c in enumerate(candidates, start=1)
        ]
        messages: list[Message] = [
            Message(
                role="system",
                content="Rank the candidate passages by relevance to the query. "
                'Return {"ranking": [positions]} — 1-based positions, best first.',
            ),
            Message(
                role="user",
                content=f"Query: {query}\nCandidates: {len(candidates)}\n"
                + "\n".join(lines),
            ),
        ]
        result = await self._llm.complete_structured(
            messages=messages, schema=RerankResult, purpose="rerank"
        )
        parsed = result.parsed
        assert isinstance(parsed, RerankResult)
        seen: set[int] = set()
        order: list[int] = []
        for pos in parsed.ranking:
            idx = pos - 1
            if 0 <= idx < len(candidates) and idx not in seen:
                seen.add(idx)
                order.append(idx)
        order.extend(i for i in range(len(candidates)) if i not in seen)
        return [candidates[i] for i in order] + hits[MAX_CANDIDATES:]


class CrossEncoderReranker:
    """sentence-transformers cross-encoder (optional `rerank` extra)."""

    def __init__(self, model_name: str = _CROSS_ENCODER_MODEL) -> None:
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(model_name)

    def rerank(self, query: str, hits: list[SearchHit]) -> list[SearchHit]:
        candidates = hits[:MAX_CANDIDATES]
        if not candidates:
            return hits
        pairs = [(query, c.text[:_SNIPPET_CHARS]) for c in candidates]
        scores = np.asarray(self._model.predict(pairs))
        order = np.argsort(-scores)
        return [candidates[int(i)] for i in order] + hits[MAX_CANDIDATES:]


def get_reranker(settings: Settings | None = None) -> Reranker:
    """Select the reranker via `RERANKER` (default `none`)."""
    settings = settings or get_settings()
    name = settings.RERANKER
    if name == "none":
        return NoReranker()
    if name == "llm":
        from pine.llm.factory import get_llm

        return LLMReranker(get_llm(settings))
    if name == "cross-encoder":
        try:
            return CrossEncoderReranker()
        except ImportError:
            logger.warning(
                "RERANKER=cross-encoder but sentence-transformers is not "
                "installed; falling back to none"
            )
            return NoReranker()
    raise RuntimeError(f"unknown RERANKER: {name}")
