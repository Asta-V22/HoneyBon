from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis

from app.api import auth, chat, health, me, submissions
from app.core.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.redis = Redis.from_url(settings.redis_url)
    app.state.queue = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    yield
    await app.state.queue.aclose()
    await app.state.redis.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    if not settings.is_dev and settings.session_secret == "change-me":
        raise RuntimeError("SESSION_SECRET must be set outside development")

    app = FastAPI(title="Honeybon API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (health, auth, me, submissions, chat):
        app.include_router(module.router, prefix="/api")
    return app


app = create_app()
