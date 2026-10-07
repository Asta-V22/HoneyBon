"""Keep a free web service from sleeping by requesting our own public URL on a timer.

Render puts a free service to sleep after 15 minutes without inbound traffic, and only traffic
arriving through its public URL counts, so the ping must go there rather than to localhost.
"""

import asyncio
import logging

import httpx

log = logging.getLogger(__name__)


async def keep_awake(
    url: str, interval_s: float, transport: httpx.AsyncBaseTransport | None = None
):
    async with httpx.AsyncClient(timeout=10, transport=transport) as client:
        while True:
            await asyncio.sleep(interval_s)
            try:
                response = await client.get(url)
                if response.status_code != 200:
                    log.warning("keep-awake ping to %s returned %s", url, response.status_code)
            except httpx.HTTPError as exc:
                log.warning("keep-awake ping to %s failed: %s", url, exc)


class _SkipHealthz(logging.Filter):
    """Keep the every-50-seconds ping out of the access log."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "/healthz" not in record.getMessage()


def quiet_access_log() -> None:
    logging.getLogger("uvicorn.access").addFilter(_SkipHealthz())
