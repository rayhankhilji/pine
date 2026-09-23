from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite:///./pine.db"
    PINE_API_KEY: str | None = None
    OPENAI_API_KEY: str | None = None
    LLM_PROVIDER: str = "fake"
    EMBEDDINGS_PROVIDER: str = "hash"
    RERANKER: str = "none"
    OCR_ENABLED: bool = False
    STORAGE_DIR: str = "./storage"
    MAX_FILE_MB: int = 200
    LOG_LEVEL: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
