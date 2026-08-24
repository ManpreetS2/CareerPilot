"""Application settings loaded from environment variables."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    """Runtime configuration. Secrets come from the environment, never source."""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE) if _ENV_FILE.exists() else ".env",
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

    # Headless in normal (server-triggered) operation. Set to false only for
    # local interactive debugging of the form-fill agent, where watching the
    # browser is the point — the deployed app always runs headless.
    form_fill_headless: bool = True
    form_fill_timeout_ms: int = 20_000

    # --- Auth ---
    session_cookie_name: str = "careerpilot_session"
    # Accepted only on the extension autofill route. Ordinary web routes
    # authenticate exclusively from the HttpOnly session cookie.
    session_header_name: str = "X-CareerPilot-Session"
    session_ttl_days: int = 30
    # False for local http. Production (APP_ENV=production) refuses to start
    # unless COOKIE_SECURE=true.
    cookie_secure: bool = False
    app_env: str = "development"
    # Comma-separated frontend origins. Never use "*" with credentials.
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Exact chrome-extension://<id> origin. Empty disables extension CORS.
    extension_origin: str = ""

    @property
    def cors_allow_origins(self) -> list[str]:
        origins = [item.strip() for item in self.allowed_origins.split(",") if item.strip()]
        if self.extension_origin.strip():
            origins.append(self.extension_origin.strip())
        return origins

    @property
    def cors_origin_regex(self) -> str | None:
        # Exact configured extension origin is listed in allow_origins.
        # Do not match arbitrary chrome-extension://* origins.
        return None


def validate_runtime_settings() -> None:
    env = settings.app_env.strip().lower()
    if env in {"production", "prod"} and not settings.cookie_secure:
        raise RuntimeError(
            "Production refuses insecure session cookies. Set COOKIE_SECURE=true."
        )


settings = Settings()
