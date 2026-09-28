"""Provider selection + model routing (ARCHITECTURE §10, §12)."""

from pine.config import Settings, get_settings
from pine.llm.base import LLM
from pine.llm.fake import FakeLLM

_PURPOSE_MODEL = {
    "rerank": "MODEL_RERANK",
    "extract_facts": "MODEL_EXTRACT",
    "financial": "MODEL_FINANCIAL",
    "investment_committee": "MODEL_IC",
}


def model_for(purpose: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    env_name = _PURPOSE_MODEL.get(purpose, "MODEL_DEFAULT")
    return str(getattr(settings, env_name))


def get_llm(settings: Settings | None = None) -> LLM:
    settings = settings or get_settings()
    provider = settings.LLM_PROVIDER
    if provider == "fake":
        return FakeLLM()
    if provider == "openai":
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY required for LLM_PROVIDER=openai")
        from pine.llm.openai import OpenAILLM

        return OpenAILLM(settings.OPENAI_API_KEY, settings.OPENAI_BASE_URL)
    raise RuntimeError(f"unknown LLM_PROVIDER: {provider}")
