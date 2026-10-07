"""arq worker: every LLM call, import and analysis runs here, never in an API request.

Run standalone with `uv run arq app.worker.main.WorkerSettings`, or set RUN_WORKER_IN_API=true
to run it inside the API process (free hosting without a separate worker service).
"""

import logging
import uuid
from typing import Any

from arq.connections import RedisSettings
from redis.asyncio import Redis

from app.chat.service import run_chat_reply
from app.core.config import get_settings
from app.db.session import SessionLocal
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


def worker_options() -> dict[str, Any]:
    return {
        "functions": [review_submission, chat_reply],
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
