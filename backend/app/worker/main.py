"""arq worker: every LLM call, import and analysis runs here, never in an API request.

Run standalone with `uv run arq app.worker.main.WorkerSettings`, or set RUN_WORKER_IN_API=true
to run it inside the API process (free hosting without a separate worker service).
"""

import logging
import uuid
from typing import Any

from arq import func
from arq.connections import RedisSettings
from redis.asyncio import Redis

from app.chat.service import run_chat_reply
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.imports.service import run_import, run_import_analysis
from app.leetcode import ensure_metadata
from app.models import Problem
from app.reviews.service import run_review
from app.worker.recovery import recover_interrupted


async def startup(ctx: dict[str, Any]) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ctx["events"] = Redis.from_url(get_settings().redis_url)
    await recover_interrupted(SessionLocal, ctx["redis"])


async def shutdown(ctx: dict[str, Any]) -> None:
    await ctx["events"].aclose()


async def review_submission(ctx: dict[str, Any], review_id: str) -> None:
    await run_review(SessionLocal, ctx["events"], uuid.UUID(review_id))


async def chat_reply(ctx: dict[str, Any], message_id: str, submission_id: str) -> None:
    await run_chat_reply(
        SessionLocal, ctx["events"], uuid.UUID(message_id), uuid.UUID(submission_id)
    )


async def fetch_problem_metadata(ctx: dict[str, Any], problem_id: str) -> None:
    async with SessionLocal() as session:
        problem = await session.get(Problem, uuid.UUID(problem_id))
        if problem is not None and await ensure_metadata(session, problem):
            await session.commit()


async def import_repository(ctx: dict[str, Any], job_id: str) -> None:
    await run_import(SessionLocal, ctx["redis"], uuid.UUID(job_id))


async def analyze_import(ctx: dict[str, Any], job_id: str) -> None:
    await run_import_analysis(SessionLocal, ctx["events"], ctx["redis"], uuid.UUID(job_id))


def worker_options() -> dict[str, Any]:
    return {
        "functions": [
            review_submission,
            chat_reply,
            fetch_problem_metadata,
            import_repository,
            # One slice is about 4 minutes, plus the submission in progress when it ends.
            func(analyze_import, timeout=900),
        ],
        "on_startup": startup,
        "on_shutdown": shutdown,
        "redis_settings": RedisSettings.from_dsn(get_settings().redis_url),
        "max_jobs": 10,
        "job_timeout": 300,
    }


class WorkerSettings:
    """Read by the arq CLI."""

    _options = worker_options()
    functions = _options["functions"]
    on_startup = _options["on_startup"]
    on_shutdown = _options["on_shutdown"]
    redis_settings = _options["redis_settings"]
    max_jobs = _options["max_jobs"]
    job_timeout = _options["job_timeout"]
