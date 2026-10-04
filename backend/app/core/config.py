from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"  # "dev" enables dev-login and non-secure cookies
    database_url: str = "postgresql+asyncpg://honeybon:honeybon@localhost:5433/honeybon"
    redis_url: str = "redis://localhost:6379/0"
    master_key: str = ""
    session_secret: str = "change-me"
    session_max_age_days: int = 30
    github_client_id: str = ""
    github_client_secret: str = ""
    # The browser-facing origin. The API is served under it at /api (Vite proxy in dev).
    frontend_origin: str = "http://localhost:5173"
    review_rate_limit_per_hour: int = 30
    # Groq charges prompt + max tokens against a per-minute limit (8K on the free tier).
    groq_request_token_limit: int = 8000
    chat_rate_limit_per_hour: int = 60
    # Recent chat turns kept verbatim; older ones are folded into a running summary.
    chat_history_char_budget: int = 12000

    @property
    def is_dev(self) -> bool:
        return self.env == "dev"

    @property
    def github_redirect_uri(self) -> str:
        return f"{self.frontend_origin}/api/auth/github/callback"


@lru_cache
def get_settings() -> Settings:
    return Settings()
