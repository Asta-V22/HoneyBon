"""Shared fixtures. API tests need `docker compose up -d` (Postgres + Redis)."""

import asyncio
import copy
import json
import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

TEST_DB = "honeybon_test"
_BASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://honeybon:honeybon@localhost:5433/honeybon"
)
TEST_DATABASE_URL = _BASE_URL.rsplit("/", 1)[0] + f"/{TEST_DB}"
TEST_REDIS_URL = "redis://localhost:6379/15"

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["REDIS_URL"] = TEST_REDIS_URL
os.environ["ENV"] = "dev"
os.environ.setdefault("MASTER_KEY", Fernet.generate_key().decode())

from app.core.config import get_settings  # noqa: E402

get_settings.cache_clear()

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def valid_review() -> dict:
    return json.loads((FIXTURES / "review_valid.json").read_text(encoding="utf-8"))


@pytest.fixture
def part_a(valid_review) -> dict:
    return {"verdict": copy.deepcopy(valid_review["verdict"]), "tier1": valid_review["tier1"]}


@pytest.fixture
def part_b(valid_review) -> dict:
    return {k: copy.deepcopy(valid_review[k]) for k in ("tier2", "tier3", "tier4", "pattern")}


# ------------------------------------------------------------------ database


async def _prepare_database() -> None:
    import asyncpg
    from sqlalchemy.ext.asyncio import create_async_engine

    from app import models  # noqa: F401
    from app.db.base import Base

    admin_dsn = _BASE_URL.replace("postgresql+asyncpg", "postgresql")
    conn = await asyncpg.connect(admin_dsn)
    try:
        if not await conn.fetchval("select 1 from pg_database where datname = $1", TEST_DB):
            await conn.execute(f'create database "{TEST_DB}"')
    finally:
        await conn.close()

    engine = create_async_engine(TEST_DATABASE_URL)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture(scope="session")
def database() -> str:
    asyncio.run(_prepare_database())
    return TEST_DATABASE_URL


@pytest.fixture
async def sessionmaker(database) -> AsyncIterator:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db.base import Base

    engine = create_async_engine(database)
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    async with engine.begin() as connection:
        await connection.execute(text(f"truncate {tables} cascade"))
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def redis() -> AsyncIterator:
    from redis.asyncio import Redis

    client = Redis.from_url(TEST_REDIS_URL)
    await client.flushdb()
    yield client
    await client.aclose()


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple]] = []
        self.job_ids: list[str | None] = []

    async def enqueue_job(self, name: str, *args, _job_id: str | None = None) -> None:
        self.jobs.append((name, args))
        self.job_ids.append(_job_id)


@pytest.fixture
def queue() -> FakeQueue:
    return FakeQueue()


@pytest.fixture
async def client(sessionmaker, redis, queue) -> AsyncIterator:
    from httpx import ASGITransport, AsyncClient

    from app.api.deps import get_queue, get_redis
    from app.db.session import get_session
    from app.main import app

    async def _session():
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_session] = _session
    app.dependency_overrides[get_redis] = lambda: redis
    app.dependency_overrides[get_queue] = lambda: queue
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
