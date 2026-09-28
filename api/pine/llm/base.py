"""LLM provider interface (ARCHITECTURE §10).

Minimal surface needed by P2 (rerank); P3.T5 extends this with tool calls,
YAML-scripted FakeLLM fixtures and LLMCall accounting.
"""

from dataclasses import dataclass
from typing import Protocol, TypedDict, runtime_checkable

from pydantic import BaseModel


class Message(TypedDict):
    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass(frozen=True)
class StructuredResult:
    parsed: BaseModel
    tokens_in: int = 0
    tokens_out: int = 0


@runtime_checkable
class LLM(Protocol):
    async def complete_structured(
        self,
        *,
        messages: list[Message],
        schema: type[BaseModel],
        purpose: str,
        model: str | None = None,
        max_output_tokens: int = 4096,
    ) -> StructuredResult: ...
