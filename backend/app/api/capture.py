"""Extension tokens (managed from Settings) and the capture endpoints the extension calls.

A token authenticates only the /api/capture routes; it is never accepted anywhere else.
"""

import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.deps import CurrentUser, QueueDep, RedisDep, Session, enforce_rate_limit
from app.api.submissions import _queue_review, queue_metadata
from app.core.config import get_settings
from app.core.crypto import generate_extension_token, hash_token
from app.models import ExtensionToken, Problem, Submission, User
from app.models.enums import CaptureMode, SubmissionSource, SubmissionStatus
from app.problems import get_or_create_problem

router = APIRouter(tags=["capture"])

MAX_ACTIVE_TOKENS = 10

# LeetCode's language slugs mapped to the names the rest of the app uses.
_LANGUAGES = {"python3": "python", "golang": "go", "c++": "cpp"}


# ---------------------------------------------------------------- tokens (cookie auth)


class TokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    last_four: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class TokenCreated(TokenOut):
    token: str  # shown once, never stored


class TokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


@router.get("/me/tokens", response_model=list[TokenOut])
async def list_tokens(user: CurrentUser, session: Session) -> list[ExtensionToken]:
    return list(
        (
            await session.scalars(
                select(ExtensionToken)
                .where(ExtensionToken.user_id == user.id)
                .order_by(ExtensionToken.created_at.desc())
            )
        ).all()
    )


@router.post("/me/tokens", response_model=TokenCreated, status_code=status.HTTP_201_CREATED)
async def create_token(body: TokenIn, user: CurrentUser, session: Session) -> TokenCreated:
    active = await session.scalar(
        select(func.count()).where(
            ExtensionToken.user_id == user.id, ExtensionToken.revoked_at.is_(None)
        )
    )
    if active >= MAX_ACTIVE_TOKENS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Revoke an old token first.")
    token = generate_extension_token()
    row = ExtensionToken(
        user_id=user.id, name=body.name.strip(), token_hash=hash_token(token), last_four=token[-4:]
    )
    session.add(row)
    await session.commit()
    return TokenCreated(**TokenOut.model_validate(row).model_dump(), token=token)


@router.delete("/me/tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(token_id: uuid.UUID, user: CurrentUser, session: Session) -> None:
    row = await session.scalar(
        select(ExtensionToken).where(
            ExtensionToken.id == token_id, ExtensionToken.user_id == user.id
        )
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Token not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        await session.commit()


# ---------------------------------------------------------------- capture (token auth)


async def token_user(request: Request, session: Session) -> User:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing extension token")
    row = await session.scalar(
        select(ExtensionToken).where(
            ExtensionToken.token_hash == hash_token(token.strip()),
            ExtensionToken.revoked_at.is_(None),
        )
    )
    user = await session.get(User, row.user_id) if row else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or revoked extension token")
    row.last_used_at = datetime.now(UTC)
    return user


TokenUser = Annotated[User, Depends(token_user)]

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ProblemMetadataIn(BaseModel):
    """Metadata the extension read from LeetCode in the user's browser. The server's own fetch
    is often blocked from cloud IPs; these values only fill fields that are still empty."""

    title: str | None = Field(default=None, max_length=300)
    difficulty: str | None = Field(default=None, max_length=16)
    topic_tags: list[Annotated[str, Field(max_length=64, pattern=r"^[a-z0-9-]+$")]] = Field(
        default_factory=list, max_length=30
    )
    frontend_id: str | None = Field(default=None, max_length=16, pattern=r"^\d+$")
    question_id: str | None = Field(default=None, max_length=16, pattern=r"^\d+$")


def _check_slug(slug: str) -> str:
    slug = slug.strip().lower()
    if not _SLUG.match(slug):
        raise ValueError("not a LeetCode problem slug")
    return slug


class CaptureIn(ProblemMetadataIn):
    slug: str = Field(max_length=200)
    submission_id: str = Field(min_length=1, max_length=64, pattern=r"^\d+$")
    status: str = Field(max_length=50)  # LeetCode's status_msg, e.g. "Accepted"
    language: str = Field(min_length=1, max_length=32)
    code: str = Field(min_length=1, max_length=100_000)
    runtime_ms: int | None = Field(default=None, ge=0)
    memory_kb: int | None = Field(default=None, ge=0)
    submitted_at: datetime | None = None

    _valid_slug = field_validator("slug")(_check_slug)


class CaptureOut(BaseModel):
    result: Literal["reviewing", "queued", "duplicate", "ignored"]
    message: str
    submission_id: uuid.UUID | None = None
    url: str | None = None


class ModeOut(BaseModel):
    capture_mode: CaptureMode
    github_login: str


class ModeIn(BaseModel):
    capture_mode: CaptureMode


def _url(submission_id: uuid.UUID) -> str:
    return f"{get_settings().frontend_origin}/review/{submission_id}"


@router.post("/capture", response_model=CaptureOut)
async def capture(
    body: CaptureIn, user: TokenUser, session: Session, queue: QueueDep, redis: RedisDep
) -> CaptureOut:
    await enforce_rate_limit(
        redis, f"hb:rl:capture:{user.id}", get_settings().capture_rate_limit_per_hour, 3600
    )
    if user.capture_mode == CaptureMode.OFF:
        await session.commit()  # keep the token's last-used time
        return CaptureOut(result="ignored", message="Capture is off.")
    if body.status.strip().lower() != "accepted":
        await session.commit()
        return CaptureOut(result="ignored", message="Only accepted submissions are captured.")

    existing = await session.scalar(
        select(Submission).where(
            Submission.user_id == user.id, Submission.external_id == body.submission_id
        )
    )
    if existing is not None:
        await session.commit()
        return CaptureOut(
            result="duplicate",
            message="Already captured.",
            submission_id=existing.id,
            url=_url(existing.id),
        )

    problem = await get_or_create_problem(
        session,
        "leetcode",
        body.slug,
        f"https://leetcode.com/problems/{body.slug}/",
        body.title,
        body.difficulty,
        body.topic_tags,
        body.frontend_id,
        body.question_id,
    )
    language = body.language.strip().lower()
    submission = Submission(
        user_id=user.id,
        problem_id=problem.id,
        code=body.code,
        language=_LANGUAGES.get(language, language),
        source=SubmissionSource.EXTENSION,
        status=SubmissionStatus.QUEUED,
        external_id=body.submission_id,
        runtime_ms=body.runtime_ms,
        memory_kb=body.memory_kb,
        submitted_at=body.submitted_at,
    )
    session.add(submission)
    try:
        await session.commit()
    except IntegrityError:  # the same submission raced in twice
        await session.rollback()
        return CaptureOut(result="duplicate", message="Already captured.")
    await queue_metadata(queue, problem)
    submission_id = submission.id  # a rollback below would expire the object

    result: Literal["reviewing", "queued"] = "queued"
    message = "Saved to your review queue."
    if user.capture_mode == CaptureMode.ANALYZE:
        try:
            await _queue_review(session, queue, redis, user, submission, None, None)
            result, message = "reviewing", "Captured. Review started."
        except HTTPException as exc:  # no API key, or the review rate limit
            await session.rollback()
            message = f"Saved to your review queue. Not reviewed: {exc.detail}"
    return CaptureOut(
        result=result, message=message, submission_id=submission_id, url=_url(submission_id)
    )


@router.get("/capture/mode", response_model=ModeOut)
async def get_mode(user: TokenUser, session: Session) -> ModeOut:
    await session.commit()
    return ModeOut(capture_mode=user.capture_mode, github_login=user.github_login)


@router.put("/capture/mode", response_model=ModeOut)
async def set_mode(body: ModeIn, user: TokenUser, session: Session) -> ModeOut:
    user.capture_mode = body.capture_mode
    await session.commit()
    return ModeOut(capture_mode=user.capture_mode, github_login=user.github_login)


# ---------------------------------------------------------------- metadata backfill (token auth)

METADATA_BATCH = 50


class MissingOut(BaseModel):
    slugs: list[str]


class BackfillItem(ProblemMetadataIn):
    slug: str = Field(max_length=200)

    _valid_slug = field_validator("slug")(_check_slug)


class BackfillIn(BaseModel):
    problems: list[BackfillItem] = Field(max_length=METADATA_BATCH)


class BackfillOut(BaseModel):
    updated: int


def _missing_metadata(user: User):
    return (
        select(Problem)
        .where(
            Problem.platform == "leetcode",
            Problem.metadata_fetched_at.is_(None),
            select(Submission.id)
            .where(Submission.user_id == user.id, Submission.problem_id == Problem.id)
            .exists(),
        )
        .order_by(Problem.slug)
    )


@router.get("/capture/metadata/missing", response_model=MissingOut)
async def missing_metadata(user: TokenUser, session: Session) -> MissingOut:
    """LeetCode problems of this user that still lack metadata, for the extension to look up."""
    problems = (await session.scalars(_missing_metadata(user).limit(METADATA_BATCH))).all()
    await session.commit()  # keep the token's last-used time
    return MissingOut(slugs=[p.slug for p in problems])


@router.post("/capture/metadata", response_model=BackfillOut)
async def backfill_metadata(
    body: BackfillIn, user: TokenUser, session: Session, redis: RedisDep
) -> BackfillOut:
    await enforce_rate_limit(redis, f"hb:rl:metadata:{user.id}", 60, 3600)
    wanted = {p.slug: p for p in (await session.scalars(_missing_metadata(user))).all()}
    updated = 0
    for item in body.problems:
        problem = wanted.get(item.slug)  # only this user's problems that still need it
        if problem is None:
            continue
        await get_or_create_problem(
            session,
            "leetcode",
            item.slug,
            problem.url,
            item.title,
            item.difficulty,
            item.topic_tags,
            item.frontend_id,
            item.question_id,
        )
        problem.metadata_fetched_at = datetime.now(UTC)
        updated += 1
    await session.commit()
    return BackfillOut(updated=updated)
