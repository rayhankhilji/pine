"""OpenAI provider — chat.completions structured outputs (ARCHITECTURE §10).

Minimal implementation covering the `complete_structured` contract used by
rerank; P3.T5 extends with tool calls, usage accounting and caching.
"""

import json
from typing import Any, cast

from pydantic import BaseModel

from pine.llm.base import Message, StructuredResult
from pine.llm.factory import model_for

_TIMEOUT_SECONDS = 60.0


class OpenAILLM:
    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url,
                                   timeout=_TIMEOUT_SECONDS)

    async def complete_structured(
        self,
        *,
        messages: list[Message],
        schema: type[BaseModel],
        purpose: str,
        model: str | None = None,
        max_output_tokens: int = 4096,
    ) -> StructuredResult:
        from openai.types.chat import ChatCompletionMessageParam

        msgs = cast(
            "list[ChatCompletionMessageParam]", [dict(m) for m in messages]
        )
        response = await self._client.chat.completions.create(
            model=model or model_for(purpose),
            messages=msgs,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "schema": schema.model_json_schema(),
                    "strict": True,
                },
            },
            max_completion_tokens=max_output_tokens,
        )
        content = response.choices[0].message.content or "{}"
        parsed = schema.model_validate(json.loads(content))
        usage: Any = response.usage
        return StructuredResult(
            parsed=parsed,
            tokens_in=getattr(usage, "prompt_tokens", 0) or 0,
            tokens_out=getattr(usage, "completion_tokens", 0) or 0,
        )
