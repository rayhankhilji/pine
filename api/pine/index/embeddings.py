"""Embedding providers (ARCHITECTURE §10, F-03.AC3).

`HashEmbedder` is a deterministic offline provider — identical text always
produces byte-identical float32 output. `OpenAIEmbedder` batches at 100 texts,
retries with exponential backoff + jitter and caps concurrency at 4 in-flight
requests. `get_embedder()` selects via `EMBEDDINGS_PROVIDER` and honours
`EMBEDDINGS_FALLBACK` (one permanent fallback after the first failure).
"""

import asyncio
import hashlib
import logging
import random
import re
from typing import Protocol, runtime_checkable

import numpy as np

from pine.config import Settings, get_settings

logger = logging.getLogger(__name__)

HASH_DIM = 256
OPENAI_MODEL = "text-embedding-3-small"
OPENAI_BATCH = 100
OPENAI_MAX_CONCURRENT = 4
OPENAI_RETRIES = 3
OPENAI_TIMEOUT_SECONDS = 60.0

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokens — shared by embeddings and BM25."""
    return _TOKEN_RE.findall(text.lower())


@runtime_checkable
class Embedder(Protocol):
    """Embedding provider interface (ARCHITECTURE §10)."""

    @property
    def model(self) -> str: ...

    @property
    def dim(self) -> int: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder:
    """Deterministic 256-d embedder: per-token sha256 → index+sign accumulators."""

    model = "hash-256"
    dim = HASH_DIM

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = np.zeros(self.dim, dtype=np.float64)
        for tok in tokenize(text):
            digest = hashlib.sha256(tok.encode()).digest()
            idx = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[idx] += sign
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec.tolist()


class OpenAIEmbedder:
    """OpenAI `text-embedding-3-small` with batching, retries and a 60 s timeout."""

    model = OPENAI_MODEL
    dim = 1536

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(
            api_key=api_key, base_url=base_url, timeout=OPENAI_TIMEOUT_SECONDS
        )
        self._semaphore = asyncio.Semaphore(OPENAI_MAX_CONCURRENT)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        batches = [texts[i : i + OPENAI_BATCH] for i in range(0, len(texts), OPENAI_BATCH)]
        results = await asyncio.gather(*(self._embed_batch(b) for b in batches))
        return [vec for batch in results for vec in batch]

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        async with self._semaphore:
            last_error: Exception | None = None
            for attempt in range(OPENAI_RETRIES):
                try:
                    response = await self._client.embeddings.create(
                        model=self.model, input=batch
                    )
                    data = sorted(response.data, key=lambda d: d.index)
                    return [list(d.embedding) for d in data]
                except Exception as exc:  # noqa: BLE001 — retried, then raised
                    last_error = exc
                    delay = 2.0**attempt + random.random()
                    logger.warning(
                        "embedding batch failed (attempt %d/%d): %s",
                        attempt + 1,
                        OPENAI_RETRIES,
                        exc,
                    )
                    await asyncio.sleep(delay)
            assert last_error is not None
            raise last_error


class FallbackEmbedder:
    """Wrap a primary embedder; on its first failure switch permanently."""

    def __init__(self, primary: Embedder, fallback: Embedder) -> None:
        self._primary = primary
        self._fallback = fallback
        self._active = primary

    @property
    def model(self) -> str:
        return self._active.model

    @property
    def dim(self) -> int:
        return self._active.dim

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self._active is not self._primary:
            return await self._fallback.embed(texts)
        try:
            return await self._primary.embed(texts)
        except Exception as exc:  # noqa: BLE001 — documented fallback path
            logger.warning(
                "embedding provider %s failed (%s); falling back to %s",
                self._primary.model,
                exc,
                self._fallback.model,
            )
            self._active = self._fallback
            return await self._fallback.embed(texts)


def get_embedder(settings: Settings | None = None) -> Embedder:
    """Select the embedder from settings (ARCHITECTURE §12)."""
    settings = settings or get_settings()
    provider = settings.EMBEDDINGS_PROVIDER
    if provider == "hash":
        return HashEmbedder()
    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY required for EMBEDDINGS_PROVIDER=openai")
        primary: Embedder = OpenAIEmbedder(
            settings.OPENAI_API_KEY, settings.OPENAI_BASE_URL
        )
        if settings.EMBEDDINGS_FALLBACK == "hash":
            return FallbackEmbedder(primary, HashEmbedder())
        return primary
    raise RuntimeError(f"unknown EMBEDDINGS_PROVIDER: {provider}")
