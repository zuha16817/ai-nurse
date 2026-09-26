"""Application configuration via environment variables."""

from functools import lru_cache
from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # App
    APP_ENV: str = "development"
    SECRET_KEY: str = "change-me-in-production-use-32-chars"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]
    ALLOWED_HOSTS: List[str] = ["*"]  # tighten in production deployments

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./ai_nurse.db"

    # AI Providers — swappable via env
    STT_PROVIDER: str = "openai_whisper"          # openai_whisper | azure_speech | mock
    LLM_PROVIDER: str = "openai_gpt4o"             # openai_gpt4o | azure_openai | mock
    TRANSLATION_PROVIDER: str = "openai"           # openai | deepl | mock
    EMBEDDING_PROVIDER: str = "openai"             # openai | local | mock

    # OpenAI / Compatible Providers (Groq, Gemini, OpenRouter, Ollama)
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = ""
    OPENAI_STT_MODEL: str = "whisper-1"
    OPENAI_LLM_MODEL: str = "gpt-4o"
    OPENAI_TRANSLATION_MODEL: str = "gpt-4o-mini"
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # Azure OpenAI (optional)
    AZURE_OPENAI_ENDPOINT: str = ""
    AZURE_OPENAI_API_KEY: str = ""
    AZURE_OPENAI_DEPLOYMENT: str = ""

    # ChromaDB
    CHROMA_PERSIST_DIR: str = "./chroma_db"

    # Triage rules
    TRIAGE_RULES_VERSION: str = "1.0.0"
    TRIAGE_RULES_DIR: str = "./app/rules"

    # Security
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    ALGORITHM: str = "HS256"

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
