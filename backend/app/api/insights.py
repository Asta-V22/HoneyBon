"""The Insights screen and the insight card on Today."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import distinct_on

from app.api.deps import CurrentUser, Session
from app.core.config import get_settings
from app.insights import ProblemRow, matrix, strongest_avoidance
from app.models import Problem, Review, Submission

router = APIRouter(prefix="/insights", tags=["insights"])

RANGES = {"30d": 30, "90d": 90, "1y": 365}


class CellOut(BaseModel):
    needed: str
    used: str
    count: int
    worse: int


class ItemOut(BaseModel):
    submission_id: uuid.UUID
    title: str
    difficulty: str | None
    platform: str
    used: str
    optimal: list[str]
    needed: str
    match: bool
    worse: bool
    low_confidence: bool | None  # None: no LeetCode tags to check against
    solved_at: datetime | None  # imports carry the import time, not when it was solved
    source: str  # extension, paste or import


class CardOut(BaseModel):
    technique: str
    avoided: int
    worse: int
    out_of: int
    usual_instead: str
    submission_ids: list[uuid.UUID]


class InsightsOut(BaseModel):
    problems: int
    matched: int
    style_mismatches: int  # another technique, same complexity
    worse_mismatches: int  # another technique and a worse complexity
    checked: int  # problems with LeetCode tags to cross-check
    disagreements: int  # of those, where the AI's optimal set contradicts the tags
    needed: list[str]
    used: list[str]
    cells: list[CellOut]
    items: list[ItemOut]
    card: CardOut | None
    min_problems: int


@router.get("", response_model=InsightsOut)
async def insights(
    user: CurrentUser,
    session: Session,
    range_: Annotated[Literal["all", "30d", "90d", "1y"], Query(alias="range")] = "all",
    difficulty: str | None = None,
    platform: str | None = None,
) -> InsightsOut:
    # One row per problem: its latest submission with a successful analysis (full or tags).
    query = (
        select(Submission, Review, Problem)
        .join(Problem, Problem.id == Submission.problem_id)
        .join(Review, Review.submission_id == Submission.id)
        .where(
            Submission.user_id == user.id,
            Review.used_technique.is_not(None),
            Review.error.is_(None),
            func.cardinality(Review.optimal_techniques) > 0,
        )
        .order_by(Submission.problem_id, Submission.created_at.desc(), Review.created_at.desc())
        .ext(distinct_on(Submission.problem_id))
    )
    if range_ != "all":
        since = datetime.now(UTC) - timedelta(days=RANGES[range_])
        query = query.where(func.coalesce(Submission.submitted_at, Submission.created_at) >= since)
    if difficulty:
        query = query.where(Problem.difficulty == difficulty)
    if platform:
        query = query.where(Problem.platform == platform)

    rows = [
        ProblemRow(
            submission_id=str(s.id),
            title=p.title or p.slug,
            difficulty=p.difficulty,
            platform=p.platform,
            used=r.used_technique,
            optimal=list(r.optimal_techniques),
            time_class=r.time_class,
            space_class=r.space_class,
            optimal_time_class=r.optimal_time_class,
            optimal_space_class=r.optimal_space_class,
            topic_tags=list(p.topic_tags or []),
            solved_at=s.submitted_at or s.created_at,
            source=str(s.source),
        )
        for s, r, p in (await session.execute(query)).all()
    ]
    needed, used, cells = matrix(rows)
    min_problems = get_settings().insight_min_problems
    card = strongest_avoidance(rows, min_problems)
    checked = [r for r in rows if r.low_confidence is not None]
    return InsightsOut(
        problems=len(rows),
        matched=sum(r.match for r in rows),
        style_mismatches=sum(not r.match and not r.worse for r in rows),
        worse_mismatches=sum(not r.match and r.worse for r in rows),
        checked=len(checked),
        disagreements=sum(bool(r.low_confidence) for r in checked),
        needed=needed,
        used=used,
        cells=[CellOut(**c.__dict__) for c in cells],
        items=[
            ItemOut(
                submission_id=r.submission_id,
                title=r.title,
                difficulty=r.difficulty,
                platform=r.platform,
                used=r.used,
                optimal=r.optimal,
                needed=r.needed,
                match=r.match,
                worse=r.worse,
                low_confidence=r.low_confidence,
                solved_at=r.solved_at,
                source=r.source,
            )
            for r in sorted(rows, key=lambda r: r.title.lower())
        ],
        card=CardOut(**card.__dict__) if card else None,
        min_problems=min_problems,
    )
