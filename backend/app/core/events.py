"""Submission progress events: the worker publishes to Redis, the API relays them over SSE."""

import json
import uuid
from typing import Any, Literal

from redis.asyncio import Redis

EventType = Literal["status", "part", "done", "failed"]


def channel(submission_id: uuid.UUID | str) -> str:
    return f"hb:submission:{submission_id}"


async def publish(
    redis: Redis, submission_id: uuid.UUID | str, type_: EventType, **data: Any
) -> None:
    await redis.publish(channel(submission_id), json.dumps({"type": type_, **data}))
