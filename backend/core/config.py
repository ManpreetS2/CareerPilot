"""Application settings loaded from environment variables."""

import re
from pathlib import Path
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPO_ROOT / ".env"

_WEB_SCHEMES = {"http", "https"}
_EXTENSION_ORIGIN_RE = re.compile(r"^chrome-extension://[a-p]{32}$")
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_TS_NET_HOST_RE = re.compile(
    r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.ts\.net$",
    re.IGNORECASE,
)
_KEEP_ALIVE_RE = re.compile(r"^([1-9]\d*)([smh])$")
SUPPORTED_LLM_PROVIDERS = ("ollama", "gemini", "anthropic", "openai")


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

    # Local/private Ollama. HTTP is loopback-only; remote URLs must be HTTPS.
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:14b"
    ollama_connect_timeout_seconds: float = 3.0
    ollama_read_timeout_seconds: float = 180.0
    ollama_keep_alive: str = "30m"
    ollama_num_ctx: int = 8192
    ollama_num_predict: int = 4096
    # Blank preserves historical Gemini-only production behavior.
    llm_provider_order: str = ""

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
        if self.extension_origin:
            origins.append(self.extension_origin)
        return origins

    @property
    def cors_origin_regex(self) -> str | None:
        # Exact configured extension origin is listed in allow_origins.
        # Do not match arbitrary chrome-extension://* origins.
        return None


def validate_origin_settings(cfg: Settings | None = None) -> None:
    """Reject wildcard or non-exact origins for credentialed CORS."""

    cfg = cfg or settings
    raw_allowed = cfg.allowed_origins or ""
    raw_extension = cfg.extension_origin or ""
    if "*" in raw_allowed or "*" in raw_extension:
        raise RuntimeError(
            "Wildcard origins are not allowed in ALLOWED_ORIGINS or EXTENSION_ORIGIN."
        )
    for origin in [item.strip() for item in raw_allowed.split(",") if item.strip()]:
        _validate_web_origin(origin)
    if raw_extension:
        _validate_extension_origin(raw_extension)
    if "*" in cfg.cors_allow_origins:
        raise RuntimeError("Credentialed CORS cannot use a wildcard origin.")


def _validate_web_origin(origin: str) -> None:
    parsed = urlparse(origin)
    if parsed.scheme not in _WEB_SCHEMES or not parsed.netloc:
        raise RuntimeError(
            "ALLOWED_ORIGINS entries must be exact http:// or https:// origins."
        )
    if parsed.username or parsed.password:
        raise RuntimeError("ALLOWED_ORIGINS entries must not include credentials.")
    if parsed.path not in {"",} or parsed.params or parsed.query or parsed.fragment:
        raise RuntimeError(
            "ALLOWED_ORIGINS entries must not include a path, query, or fragment."
        )


def _validate_extension_origin(origin: str) -> None:
    if _EXTENSION_ORIGIN_RE.fullmatch(origin):
        return
    raise RuntimeError(
        "EXTENSION_ORIGIN must be blank or one exact chrome-extension:// origin "
        "with a 32-character id using only lowercase a-p."
    )


def parse_llm_provider_order(raw: str | None) -> list[str]:
    """Return the sequential provider list. Blank/absent keeps Gemini-only behavior."""

    if raw is None:
        return ["gemini"]
    text = str(raw).strip()
    if not text:
        return ["gemini"]
    parts = [item.strip().lower() for item in text.split(",")]
    if any(not item for item in parts):
        raise RuntimeError("LLM provider order is invalid.")
    seen: set[str] = set()
    for name in parts:
        if name not in SUPPORTED_LLM_PROVIDERS or name in seen:
            raise RuntimeError("LLM provider order is invalid.")
        seen.add(name)
    return parts


def validate_ollama_base_url(url: str) -> str:
    """Accept loopback HTTP(S) or an exact Tailscale Serve HTTPS hostname."""

    raw = (url or "").strip()
    if not raw or "*" in raw:
        raise RuntimeError("Ollama base URL is invalid.")
    parsed = urlparse(raw)
    if parsed.username or parsed.password:
        raise RuntimeError("Ollama base URL is invalid.")
    if parsed.params or parsed.query or parsed.fragment:
        raise RuntimeError("Ollama base URL is invalid.")
    if parsed.path not in {"", "/"}:
        raise RuntimeError("Ollama base URL is invalid.")
    host = (parsed.hostname or "").lower()
    if not host or "*" in host:
        raise RuntimeError("Ollama base URL is invalid.")
    if parsed.scheme == "http":
        if host not in _LOOPBACK_HOSTS:
            raise RuntimeError("Ollama base URL is invalid.")
    elif parsed.scheme == "https":
        if host not in _LOOPBACK_HOSTS and not _TS_NET_HOST_RE.fullmatch(host):
            raise RuntimeError("Ollama base URL is invalid.")
    else:
        raise RuntimeError("Ollama base URL is invalid.")
    return raw[:-1] if parsed.path == "/" and raw.endswith("/") else raw


def _has_control_characters(value: str) -> bool:
    return any(ord(char) < 32 or char == "\x7f" for char in value)


def validate_llm_settings(cfg: Settings | None = None) -> None:
    """Validate LLM settings without probing provider availability."""

    cfg = cfg or settings
    parse_llm_provider_order(cfg.llm_provider_order)
    validate_ollama_base_url(cfg.ollama_base_url)
    model = (cfg.ollama_model or "").strip()
    if not model or _has_control_characters(cfg.ollama_model or ""):
        raise RuntimeError("Ollama model is invalid.")
    connect = float(cfg.ollama_connect_timeout_seconds)
    read = float(cfg.ollama_read_timeout_seconds)
    if not 0.1 <= connect <= 60:
        raise RuntimeError("Ollama connect timeout is invalid.")
    if not 1 <= read <= 600:
        raise RuntimeError("Ollama read timeout is invalid.")
    if int(cfg.ollama_num_ctx) < 256 or int(cfg.ollama_num_ctx) > 131072:
        raise RuntimeError("Ollama context size is invalid.")
    if int(cfg.ollama_num_predict) < 1 or int(cfg.ollama_num_predict) > 32768:
        raise RuntimeError("Ollama output limit is invalid.")
    keep_alive = (cfg.ollama_keep_alive or "").strip()
    match = _KEEP_ALIVE_RE.fullmatch(keep_alive)
    if match is None:
        raise RuntimeError("Ollama keep-alive is invalid.")
    amount = int(match.group(1))
    seconds = amount * {"s": 1, "m": 60, "h": 3600}[match.group(2)]
    if seconds > 24 * 3600:
        raise RuntimeError("Ollama keep-alive is invalid.")


def validate_runtime_settings() -> None:
    env = settings.app_env.strip().lower()
    if env in {"production", "prod"} and not settings.cookie_secure:
        raise RuntimeError(
            "Production refuses insecure session cookies. Set COOKIE_SECURE=true."
        )
    validate_origin_settings(settings)
    validate_llm_settings(settings)


settings = Settings()
