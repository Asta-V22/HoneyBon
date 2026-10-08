"""Problem metadata from LeetCode's public GraphQL endpoint (no login needed).

Only metadata is stored (title, difficulty, topic tags, IDs); problem statements never are.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Problem

log = logging.getLogger(__name__)

GRAPHQL_URL = "https://leetcode.com/graphql"
REFRESH_AFTER = timedelta(days=30)

_QUERY = """
query question($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    questionFrontendId
    title
    difficulty
    topicTags { slug }
  }
}
"""


@dataclass(frozen=True)
class LeetCodeQuestion:
    question_id: str
    frontend_id: str
    title: str
    difficulty: str
    topic_tags: list[str]  # tag slugs, e.g. "dynamic-programming"


class LeetCodeUnavailable(Exception):
    """LeetCode could not be reached or refused the request (it sometimes blocks cloud IPs)."""


async def fetch_question(
    slug: str, transport: httpx.AsyncBaseTransport | None = None
) -> LeetCodeQuestion | None:
    """The question for a slug, or None if LeetCode has no such problem."""
    try:
        async with httpx.AsyncClient(timeout=15, transport=transport) as client:
            response = await client.post(
                GRAPHQL_URL,
                json={"query": _QUERY, "variables": {"titleSlug": slug}},
                headers={
                    "Referer": f"https://leetcode.com/problems/{slug}/",
                    "User-Agent": "Mozilla/5.0 (compatible; Honeybon)",
                },
            )
            response.raise_for_status()
            question = response.json()["data"]["question"]
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise LeetCodeUnavailable(str(exc)) from exc
    if question is None:
        return None
    return LeetCodeQuestion(
        question_id=str(question["questionId"]),
        frontend_id=str(question["questionFrontendId"]),
        title=question["title"],
        difficulty=question["difficulty"],
        topic_tags=[t["slug"] for t in question.get("topicTags") or []],
    )


def needs_metadata(problem: Problem) -> bool:
    if problem.platform != "leetcode":
        return False
    fetched = problem.metadata_fetched_at
    return fetched is None or fetched < datetime.now(UTC) - REFRESH_AFTER


async def ensure_metadata(
    session: AsyncSession, problem: Problem, transport: httpx.AsyncBaseTransport | None = None
) -> bool:
    """Fill a LeetCode problem's metadata if missing or stale. Never raises; returns success."""
    if not needs_metadata(problem):
        return True
    if not get_settings().leetcode_metadata:
        return False
    try:
        question = await fetch_question(problem.slug, transport)
    except LeetCodeUnavailable as exc:
        log.warning("LeetCode metadata for %s unavailable: %s", problem.slug, exc)
        return False
    if question is not None:
        problem.title = question.title
        problem.difficulty = question.difficulty
        problem.topic_tags = question.topic_tags
        problem.frontend_id = question.frontend_id
        problem.platform_question_id = question.question_id
    problem.metadata_fetched_at = datetime.now(UTC)
    return True
