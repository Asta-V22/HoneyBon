import json
from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse
from redis.asyncio import Redis

TERMINAL = ("done", "failed")


def relay(redis: Redis, channel: str) -> StreamingResponse:
    """Relay a Redis channel as server-sent events until a done or failed event."""

    async def stream() -> AsyncIterator[str]:
        pubsub = redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            # Subscribed before announcing readiness, so a refetch on "ready" misses nothing.
            yield "event: ready\ndata: {}\n\n"
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=15)
                if message is None:
                    yield ": keepalive\n\n"
                    continue
                data = message["data"]
                data = data.decode() if isinstance(data, bytes) else data
                yield f"data: {data}\n\n"
                if json.loads(data).get("type") in TERMINAL:
                    break
        finally:
            await pubsub.unsubscribe()
            await pubsub.aclose()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
