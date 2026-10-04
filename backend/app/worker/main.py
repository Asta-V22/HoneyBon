"""arq worker: every LLM call, import and analysis runs here, never in the API process.

Run with: uv run arq app.worker.main.WorkerSettings
"""

import logging
from typing import Any

from arq.connections import RedisSettings

from app.core.config import get_settings

log = logging.getLogger(__name__)


async def review_submission(ctx: dict[str, Any], submission_id: str) -> None:
    # Phase 1: load submission + credential, call the adapter, validate with one repair
    # retry, store the review, and publish tier progress to Redis for the SSE relay.
    log.info("review_submission queued for %s (pipeline not implemented yet)", submission_id)


class WorkerSettings:
    functions = [review_submission]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 10
    job_timeout = 180
