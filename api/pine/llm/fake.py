"""Deterministic offline LLM for tests/evals (ARCHITECTURE §10).

Only `purpose="rerank"` is scripted so far: it returns a stable permutation —
the top-3 candidates keep their order, the tail is reversed — so tests exercise
the reordering path without depending on model output quality. P3.T5 will add
YAML fixture scripting for extraction/agent purposes.
"""

import re

from pydantic import BaseModel

from pine.llm.base import Message, StructuredResult

_CANDIDATES_RE = re.compile(r"^Candidates:\s*(\d+)\s*$", re.M)


class FakeLLM:
    model = "fake-llm"

    async def complete_structured(
        self,
        *,
        messages: list[Message],
        schema: type[BaseModel],
        purpose: str,
        model: str | None = None,
        max_output_tokens: int = 4096,
    ) -> StructuredResult:
        if purpose == "rerank":
            return StructuredResult(parsed=self._rerank(messages, schema))
        raise RuntimeError(f"FakeLLM: no scripted response for purpose {purpose!r}")

    def _rerank(
        self, messages: list[Message], schema: type[BaseModel]
    ) -> BaseModel:
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        match = _CANDIDATES_RE.search(last_user)
        n = int(match.group(1)) if match else 0
        # 1-based positions: keep the top 3 stable, reverse the tail
        ranking = [1, 2, 3][:n] + list(range(n, 3, -1))
        return schema.model_validate({"ranking": ranking})
