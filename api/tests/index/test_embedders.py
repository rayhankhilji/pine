"""Embedder tests — determinism (F-03.AC3), packing roundtrip, fallback."""

import numpy as np
import pytest

from pine.config import Settings
from pine.index.embeddings import (
    FallbackEmbedder,
    HashEmbedder,
    OpenAIEmbedder,
    get_embedder,
    tokenize,
)
from pine.index.vectors import pack_vec, unpack_vec


async def test_hash_embedder_deterministic() -> None:
    """F-03.AC3: same input → byte-identical float32 output across runs."""
    texts = ["ARR reached $12.0M in Q4 2025", "net burn $450k/month"]
    first = await HashEmbedder().embed(texts)
    second = await HashEmbedder().embed(texts)
    assert first == second
    assert pack_vec(first[0]) == pack_vec(second[0])


async def test_hash_embedder_shape_and_norm() -> None:
    vecs = await HashEmbedder().embed(["hello world", "totally different text"])
    assert len(vecs[0]) == 256
    assert np.linalg.norm(np.asarray(vecs[0])) == pytest.approx(1.0)
    assert vecs[0] != vecs[1]
    empty = (await HashEmbedder().embed([""]))[0]
    assert all(v == 0.0 for v in empty)


async def test_similar_texts_score_higher_than_unrelated() -> None:
    vecs = await HashEmbedder().embed(
        ["annual recurring revenue", "recurring annual revenue", "zzz qqq"]
    )
    a, b, c = (np.asarray(v, dtype=np.float64) for v in vecs)
    assert float(a @ b) > float(a @ c)


def test_pack_unpack_roundtrip() -> None:
    vec = [0.25, -1.5, 3.125]
    out = unpack_vec(pack_vec(vec))
    assert out.dtype == np.dtype("<f4")
    np.testing.assert_allclose(out, vec, rtol=1e-6)
    assert len(pack_vec(vec)) == 3 * 4


def test_tokenize() -> None:
    assert tokenize("ARR $12.0M — Q4'25") == ["arr", "12", "0m", "q4", "25"]


def test_get_embedder_hash() -> None:
    emb = get_embedder(Settings(EMBEDDINGS_PROVIDER="hash"))
    assert isinstance(emb, HashEmbedder)


def test_get_embedder_openai_requires_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        get_embedder(Settings(EMBEDDINGS_PROVIDER="openai", OPENAI_API_KEY=None))


def test_get_embedder_openai_with_fallback() -> None:
    emb = get_embedder(
        Settings(
            EMBEDDINGS_PROVIDER="openai",
            OPENAI_API_KEY="sk-test",
            EMBEDDINGS_FALLBACK="hash",
        )
    )
    assert isinstance(emb, FallbackEmbedder)


async def test_fallback_switches_after_first_failure() -> None:
    class Boom:
        model = "boom"
        dim = 4

        async def embed(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("provider down")

    emb = FallbackEmbedder(Boom(), HashEmbedder())
    out = await emb.embed(["hello"])
    assert len(out[0]) == 256
    assert emb.model == "hash-256"
    # stays on fallback — Boom is not consulted again
    assert await emb.embed(["world"])


async def test_openai_embedder_batches_and_retries() -> None:
    """Stubbed AsyncOpenAI client: one transient failure, batching at 100."""
    calls: list[list[str]] = []
    failures_left = 1

    class StubEmbeddings:
        async def create(self, model: str, input: list[str]) -> object:  # noqa: A002
            nonlocal failures_left
            calls.append(list(input))
            if failures_left:
                failures_left -= 1
                raise RuntimeError("429 rate limited")

            class Item:
                def __init__(self, index: int) -> None:
                    self.index = index
                    self.embedding = [float(index)] * 3

            class Resp:
                data = [Item(i) for i in range(len(input))]

            return Resp()

    class StubClient:
        embeddings = StubEmbeddings()

    emb = OpenAIEmbedder.__new__(OpenAIEmbedder)
    # test stub stands in for AsyncOpenAI
    emb._client = StubClient()  # type: ignore[assignment]
    import asyncio

    emb._semaphore = asyncio.Semaphore(4)

    texts = [f"t{i}" for i in range(150)]
    out = await emb.embed(texts)
    assert len(out) == 150
    # 2 batches (100 + 50) + 1 retried batch
    assert sorted(len(c) for c in calls) == [50, 100, 100]
