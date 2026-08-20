"""Application settings loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets come from the environment, never source."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.6-flash"

    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    default_llm_provider: str = "gemini"

    database_url: str = "sqlite:///./data/careerpilot.db"
    backend_url: str = "http://localhost:8000"
    log_level: str = "INFO"


settings = Settings()
