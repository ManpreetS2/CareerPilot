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

    adzuna_app_id: str | None = None
    adzuna_app_key: str | None = None
    adzuna_country: str = "us"

    scout_results_per_source: int = 25
    http_timeout_seconds: float = 15.0
    http_user_agent: str = "CareerPilotAI/0.1 (job search assistant; +https://github.com/ManpreetS2/CareerPilot)"


settings = Settings()
