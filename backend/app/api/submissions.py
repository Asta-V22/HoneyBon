import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, QueueDep, RedisDep, Session, enforce_rate_limit
from app.api.schemas import (
    PasteIn,
    ProblemOut,
    ReviewOut,
    ReviewRequestIn,
    ReviewSummaryOut,
    SubmissionListItem,
    SubmissionOut,
    SubmissionPage,
)
from app.api.sse import relay
from app.core.config import get_settings
from app.core.events import channel
from app.models import Problem, ProviderCredential, Review, Submission, User
from app.models.enums import SubmissionSource, SubmissionStatus
from app.problems import detect_language, parse_problem_link, ref_from_statement
from app.providers import DEFAULT_MODELS, PROVIDERS

router = APIRouter(prefix="/submissions", tags=["submissions"])


# ---------------------------------------------------------------- helpers


async def _owned_submission(session: Session, user: User, submission_id: uuid.UUID) -> Submission:
    submission = await session.scalar(
        select(Submission)
        .where(Submission.id == submission_id, Submission.user_id == user.id)
        .options(selectinload(Submission.problem))
    )
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    return submission


def _latest_reviews(submission_ids: list[uuid.UUID]) -> Select[tuple[Review]]:
    return (
        select(Review)
        .where(Review.submission_id.in_(submission_ids))
        .order_by(Review.submission_id, Review.created_at.desc())
        .ext(distinct_on(Review.submission_id))
    )


async def _detail(session: Session, submission: Submission) -> SubmissionOut:
    review = await session.scalar(_latest_reviews([submission.id]))
    out = SubmissionOut.model_validate(submission)
    out.review = ReviewOut.model_validate(review) if review else None
    return out


async def _resolve_model(
    session: Session, user: User, provider: str | None, model: str | None
) -> tuple[str, str]:
    saved = set(
        (
            await session.scalars(
                select(ProviderCredential.provider).where(ProviderCredential.user_id == user.id)
            )
        ).all()
    )
    provider = provider or user.default_provider or (min(saved) if saved else None)
    if provider is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Add an API key in Settings first.")
    if provider not in PROVIDERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown provider: {provider}")
    if provider not in saved:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"No {provider} API key saved.")
    if not model and provider == user.default_provider:
        model = user.default_model
    model = model or DEFAULT_MODELS.get(provider)
    if not model:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Choose a {provider} model in Settings.")
    return provider, model


async def _queue_review(
    session: Session,
    queue: QueueDep,
    redis: RedisDep,
    user: User,
    submission: Submission,
    provider: str | None,
    model: str | None,
) -> None:
    await enforce_rate_limit(
        redis, f"hb:rl:review:{user.id}", get_settings().review_rate_limit_per_hour, 3600
    )
    provider, model = await _resolve_model(session, user, provider, model)
    review = Review(submission_id=submission.id, provider=provider, model=model)
    session.add(review)
    submission.status = SubmissionStatus.QUEUED
    await session.commit()
    await queue.enqueue_job("review_submission", str(review.id))


async def _get_or_create_problem(session: Session, body: PasteIn) -> Problem:
    ref = parse_problem_link(body.link) if body.link and body.link.strip() else None
    ref = ref or ref_from_statement(body.statement or "")
    platform = (body.platform or ref.platform).lower()
    problem = await session.scalar(
        select(Problem).where(Problem.platform == platform, Problem.slug == ref.slug)
    )
    if problem is None:
        problem = Problem(platform=platform, slug=ref.slug, url=ref.url, topic_tags=[])
        session.add(problem)
    if body.title and not problem.title:
        problem.title = body.title
    if problem.title is None and platform == "leetcode":
        problem.title = ref.slug.replace("-", " ").title()
    await session.flush()
    return problem


# ---------------------------------------------------------------- routes


@router.post("", response_model=SubmissionOut, status_code=status.HTTP_201_CREATED)
async def paste_submission(
    body: PasteIn, user: CurrentUser, session: Session, queue: QueueDep, redis: RedisDep
) -> SubmissionOut:
    problem = await _get_or_create_problem(session, body)
    submission = Submission(
        user_id=user.id,
        problem_id=problem.id,
        code=body.code,
        statement=body.statement.strip() if body.statement and body.statement.strip() else None,
        language=(body.language or detect_language(body.code)).lower(),
        source=SubmissionSource.PASTE,
    )
    session.add(submission)
    await session.flush()
    await _queue_review(session, queue, redis, user, submission, body.provider, body.model)
    await session.refresh(submission, ["problem"])
    return await _detail(session, submission)


@router.get("", response_model=SubmissionPage)
async def list_submissions(
    user: CurrentUser,
    session: Session,
    q: str | None = None,
    platform: str | None = None,
    difficulty: str | None = None,
    technique: str | None = None,
    suboptimal: bool = False,
    status_: Annotated[SubmissionStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> SubmissionPage:
    latest = _latest_reviews_subquery()
    query = (
        select(Submission)
        .join(Submission.problem)
        .outerjoin(latest, latest.c.submission_id == Submission.id)
        .where(Submission.user_id == user.id)
    )
    if q:
        like = f"%{q.strip()}%"
        query = query.where(or_(Problem.title.ilike(like), Problem.slug.ilike(like)))
    if platform:
        query = query.where(Problem.platform == platform)
    if difficulty:
        query = query.where(Problem.difficulty == difficulty)
    if status_:
        query = query.where(Submission.status == status_)
    if technique:
        query = query.where(
            or_(
                latest.c.used_technique == technique,
                latest.c.optimal_techniques.contains([technique]),
            )
        )
    if suboptimal:
        # A worse time or space class than the optimum. A different technique in the same
        # classes is a style choice, not a weakness.
        query = query.where(
            (latest.c.time_class != latest.c.optimal_time_class)
            | (latest.c.space_class != latest.c.optimal_space_class)
        )

    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await session.scalars(
            query.options(selectinload(Submission.problem))
            .order_by(Submission.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    reviews = {
        r.submission_id: r
        for r in (await session.scalars(_latest_reviews([s.id for s in rows]))).all()
    }
    items = []
    for s in rows:
        item = SubmissionListItem(
            id=s.id,
            problem=ProblemOut.model_validate(s.problem),
            language=s.language,
            source=s.source,
            status=s.status,
            created_at=s.created_at,
        )
        if (r := reviews.get(s.id)) is not None and r.used_technique:
            item.review = ReviewSummaryOut.model_validate(r)
        items.append(item)
    return SubmissionPage(items=items, total=total or 0)


def _latest_reviews_subquery():
    return (
        select(
            Review.submission_id,
            Review.used_technique,
            Review.optimal_techniques,
            Review.time_class,
            Review.space_class,
            Review.optimal_time_class,
            Review.optimal_space_class,
        )
        .order_by(Review.submission_id, Review.created_at.desc())
        .ext(distinct_on(Review.submission_id))
        .subquery()
    )


@router.get("/{submission_id}", response_model=SubmissionOut)
async def get_submission(
    submission_id: uuid.UUID, user: CurrentUser, session: Session
) -> SubmissionOut:
    return await _detail(session, await _owned_submission(session, user, submission_id))


@router.post("/{submission_id}/reviews", response_model=SubmissionOut)
async def request_review(
    submission_id: uuid.UUID,
    body: ReviewRequestIn,
    user: CurrentUser,
    session: Session,
    queue: QueueDep,
    redis: RedisDep,
) -> SubmissionOut:
    """Retry a failed review, or re-review with a different provider or model."""
    submission = await _owned_submission(session, user, submission_id)
    if submission.status in (SubmissionStatus.QUEUED, SubmissionStatus.ANALYZING):
        latest = await session.scalar(_latest_reviews([submission.id]))
        if latest is not None and latest.completed_at is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "A review is already running")
    await _queue_review(session, queue, redis, user, submission, body.provider, body.model)
    return await _detail(session, submission)


@router.get("/{submission_id}/events")
async def submission_events(
    submission_id: uuid.UUID, user: CurrentUser, session: Session, redis: RedisDep
) -> StreamingResponse:
    """Server-sent events while a review runs. Clients refetch the submission on each event."""
    await _owned_submission(session, user, submission_id)
    return relay(redis, channel(submission_id))
