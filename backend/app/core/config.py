from functools import lru_cache
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# libpq-style query options that asyncpg rejects; SSL is passed via connect_args instead.
_LIBPQ_ONLY = {"sslmode", "channel_binding"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"  # "dev" enables dev-login and non-secure cookies; anything else is production
    database_url: str = "postgresql+asyncpg://honeybon:honeybon@localhost:5433/honeybon"
    database_ssl: bool = False  # set automatically when the URL asks for sslmode=require
    redis_url: str = "redis://localhost:6379/0"
    master_key: str = ""
    session_secret: str = "change-me"
    session_max_age_days: int = 30
    github_client_id: str = ""
    github_client_secret: str = ""
    # The browser-facing origin. The API is served under it at /api (Vite proxy in dev,
    # a Vercel rewrite in production).
    frontend_origin: str = "http://localhost:5173"
    # Free hosting has no separate worker service: run the arq worker inside the API process.
    run_worker_in_api: bool = False
    # Ping our own public /healthz so a free host that sleeps on idle (Render) stays awake.
    # The URL defaults to RENDER_EXTERNAL_URL, which Render sets on every web service.
    keep_awake: bool = False
    keep_awake_url: str = ""
    keep_awake_interval_s: float = 50
    render_external_url: str = ""
    review_rate_limit_per_hour: int = 30
    # Groq charges prompt + max tokens against a per-minute limit (8K on the free tier).
    groq_request_token_limit: int = 8000
    chat_rate_limit_per_hour: int = 60
    # Recent chat turns kept verbatim; older ones are folded into a running summary.
    chat_history_char_budget: int = 12000

    @field_validator("database_url", mode="before")
    @classmethod
    def _asyncpg_url(cls, url: str) -> str:
        """Accept the plain postgres:// URLs hosts like Neon hand out."""
        if url.startswith("postgres://"):
            url = "postgresql://" + url.removeprefix("postgres://")
        if url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url.removeprefix("postgresql://")
        return url

    def model_post_init(self, _context: Any) -> None:
        parts = urlsplit(self.database_url)
        query = dict(parse_qsl(parts.query))
        if query.get("sslmode") in {"require", "verify-ca", "verify-full"}:
            self.database_ssl = True
        if _LIBPQ_ONLY & query.keys():
            kept = {k: v for k, v in query.items() if k not in _LIBPQ_ONLY}
            self.database_url = urlunsplit(parts._replace(query=urlencode(kept)))

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"

    @property
    def github_redirect_uri(self) -> str:
        return f"{self.frontend_origin}/api/auth/github/callback"

    @property
    def keep_awake_target(self) -> str | None:
        if not self.keep_awake:
            return None
        if self.keep_awake_url:
            return self.keep_awake_url
        if self.render_external_url:
            return self.render_external_url.rstrip("/") + "/healthz"
        return None

    @property
    def engine_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {"pool_pre_ping": True}
        if self.database_ssl:
            options["connect_args"] = {"ssl": "require"}
        return options

    def check_production(self) -> None:
        if self.is_dev:
            return
        missing = [
            name
            for name, ok in [
                ("SESSION_SECRET", self.session_secret not in ("", "change-me")),
                ("MASTER_KEY", bool(self.master_key)),
                ("FRONTEND_ORIGIN", self.frontend_origin.startswith("https://")),
            ]
            if not ok
        ]
        if missing:
            raise RuntimeError(f"Set these for production: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
