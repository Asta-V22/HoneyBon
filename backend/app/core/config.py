from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://honeybon:honeybon@localhost:5433/honeybon"
    redis_url: str = "redis://localhost:6379/0"
    master_key: str = ""
    session_secret: str = "change-me"
    github_client_id: str = ""
    github_client_secret: str = ""
    frontend_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()
