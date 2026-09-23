from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All environment configuration (ARCHITECTURE §12)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite:///./pine.db"
    STORAGE_DIR: str = "./storage"

    PINE_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str | None = None

    LLM_PROVIDER: str = "fake"
    EMBEDDINGS_PROVIDER: str = "hash"
    EMBEDDINGS_FALLBACK: str | None = None
    RERANKER: str = "none"

    MODEL_DEFAULT: str = "gpt-5-mini"
    MODEL_FINANCIAL: str = "gpt-5"
    MODEL_IC: str = "gpt-5"
    MODEL_EXTRACT: str = "gpt-5-mini"
    MODEL_RERANK: str = "gpt-5-mini"
    LLM_CACHE: bool = True

    RUN_MAX_TOKENS: int = 1_500_000
    RUN_MAX_COST_USD: float = 10.0

    OCR_ENABLED: bool = False
    TESSERACT_CMD: str | None = None

    WORKER_ENABLED: bool = True
    WORKER_CONCURRENCY: int = 4

    MAX_FILE_MB: int = 200
    MAX_DEAL_GB: int = 2

    WEB_ORIGIN: str = "http://localhost:3000"
    LOG_LEVEL: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
