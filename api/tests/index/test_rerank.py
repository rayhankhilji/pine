"""Reranker tests — none/llm/cross-encoder selection and FakeLLM rerank."""

import importlib.util

import pytest
from pydantic import BaseModel

from pine.config import Settings
from pine.index.rerank import (
    MAX_CANDIDATES,
    CrossEncoderReranker,
    LLMReranker,
    NoReranker,
    RerankResult,
    get_reranker,
)
from pine.index.retrieval import SearchHit
from pine.llm.base import Message, StructuredResult
from pine.llm.fake import FakeLLM


def _hit(i: int, text: str | None = None) -> SearchHit:
    return SearchHit(
        chunk_id=f"c{i}",
        document_id="d",
        filename="f.txt",
        page_no=1,
        text=text or f"passage {i}",
        score=1.0 / (60 + i),
        bm25_rank=i + 1,
        dense_rank=None,
    )


def test_no_reranker_identity() -> None:
    hits = [_hit(i) for i in range(5)]
    assert NoReranker().rerank("q", hits) is hits


def test_llm_reranker_fake_keeps_top3_reverses_tail() -> None:
    hits = [_hit(i) for i in range(6)]
    out = LLMReranker(FakeLLM()).rerank("q", hits)
    # FakeLLM ranking = [1,2,3] + reversed tail → order 0,1,2,5,4,3
    assert [h.chunk_id for h in out] == ["c0", "c1", "c2", "c5", "c4", "c3"]


def test_llm_reranker_caps_candidates() -> None:
    hits = [_hit(i) for i in range(MAX_CANDIDATES + 5)]
    out = LLMReranker(FakeLLM()).rerank("q", hits)
    assert len(out) == len(hits)
    # first MAX_CANDIDATES reranked (top-3 stable, rest of the window reversed),
    # the tail passes through untouched
    assert [h.chunk_id for h in out[:3]] == ["c0", "c1", "c2"]
    assert [h.chunk_id for h in out[MAX_CANDIDATES:]] == [
        f"c{i}" for i in range(MAX_CANDIDATES, len(hits))
    ]


class _ScriptedLLM:
    def __init__(self, ranking: list[int]) -> None:
        self._ranking = ranking

    async def complete_structured(
        self,
        *,
        messages: list[Message],
        schema: type[BaseModel],
        purpose: str,
        model: str | None = None,
        max_output_tokens: int = 4096,
    ) -> StructuredResult:
        return StructuredResult(parsed=RerankResult(ranking=self._ranking))


def test_llm_reranker_filters_invalid_positions() -> None:
    hits = [_hit(i) for i in range(4)]
    out = LLMReranker(_ScriptedLLM([99, 2, 2, -1])).rerank("q", hits)
    # only valid unique positions honoured; unmentioned candidates keep order
    assert [h.chunk_id for h in out] == ["c1", "c0", "c2", "c3"]


def test_llm_reranker_empty() -> None:
    assert LLMReranker(FakeLLM()).rerank("q", []) == []


def test_get_reranker_none() -> None:
    assert isinstance(get_reranker(Settings(RERANKER="none")), NoReranker)


def test_get_reranker_llm_fake_provider() -> None:
    r = get_reranker(Settings(RERANKER="llm", LLM_PROVIDER="fake"))
    assert isinstance(r, LLMReranker)


def test_get_reranker_cross_encoder() -> None:
    r = get_reranker(Settings(RERANKER="cross-encoder"))
    if importlib.util.find_spec("sentence_transformers") is None:
        assert isinstance(r, NoReranker)  # graceful fallback (with warning)
    else:
        assert isinstance(r, CrossEncoderReranker)


def test_get_reranker_unknown() -> None:
    with pytest.raises(RuntimeError, match="unknown RERANKER"):
        get_reranker(Settings(RERANKER="bogus"))
