import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from arq.worker import Worker
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api import auth, chat, health, me, submissions
from app.core.config import get_settings
from app.core.keep_awake import keep_awake, quiet_access_log


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.redis = Redis.from_url(settings.redis_url)
    app.state.queue = await create_pool(RedisSettings.from_dsn(settings.redis_url))

    background: list[asyncio.Task] = []
    if target := settings.keep_awake_target:
        quiet_access_log()
        background.append(asyncio.create_task(keep_awake(target, settings.keep_awake_interval_s)))

    worker = None
    if settings.run_worker_in_api:
        from app.worker.main import worker_options

        worker = Worker(**worker_options(), handle_signals=False)
        background.append(asyncio.create_task(worker.async_run()))
    try:
        yield
    finally:
        if worker is not None:
            await worker.close()
        for task in background:
            task.cancel()
        await app.state.queue.aclose()
        await app.state.redis.aclose()


class NoStoreAPI:
    """Mark every /api response uncacheable, so no CDN in front (e.g. a Vercel rewrite) caches
    one user's data for another. Pure ASGI so server-sent event streams pass through untouched."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/"):
            await self.app(scope, receive, send)
            return

        async def send_with_header(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k != b"cache-control"]
                message["headers"] = [*headers, (b"cache-control", b"no-store")]
            await send(message)

        await self.app(scope, receive, send_with_header)


def create_app() -> FastAPI:
    settings = get_settings()
    settings.check_production()

    app = FastAPI(title="Honeybon API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(NoStoreAPI)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    for module in (health, auth, me, submissions, chat):
        app.include_router(module.router, prefix="/api")
    app.include_router(health.root_router)
    return app


app = create_app()
