"""GitHub import: start an import, follow its progress, map unmatched folders, choose analysis."""

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.deps import CurrentUser, QueueDep, RedisDep, Session, enforce_rate_limit
from app.api.submissions import _resolve_model, queue_metadata
from app.imports.github import SolutionFile, parse_repo
from app.imports.service import add_solution
from app.models import ImportJob, Review, Submission, User
from app.models.enums import ImportAnalysisMode, ImportStatus, ReviewKind, SubmissionStatus
from app.problems import get_or_create_problem, parse_problem_link
from app.reviews.pricing import estimate_cost
from app.worker.recovery import analysis_job_id, import_job_id

router = APIRouter(prefix="/imports", tags=["imports"])

IMPORTS_PER_HOUR = 10
# Typical tokens per submission (input, output) until the user has reviews of their own.
DEFAULT_TOKENS = {ReviewKind.FULL: (9000, 6000), ReviewKind.TAGS: (1800, 500)}


class UnmatchedFileOut(BaseModel):
    path: str
    language: str


class UnmatchedFolderOut(BaseModel):
    folder: str
    files: list[UnmatchedFileOut]


class ImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    repository: str
    status: ImportStatus
    total: int
    processed: int
    imported: int
    duplicates: int
    unmatched: list[UnmatchedFolderOut]
    error: str | None
    analysis_mode: ImportAnalysisMode | None
    analysis_status: ImportStatus | None
    analysis_provider: str | None
    analysis_model: str | None
    analysis_total: int
    analysis_done: int
    analysis_failed: int
    analysis_error: str | None
    pending: int  # imported submissions not analysed yet
    created_at: datetime
    updated_at: datetime


class ImportIn(BaseModel):
    repository: str = Field(min_length=1, max_length=300)


class AnalysisIn(BaseModel):
    mode: ImportAnalysisMode
    provider: str | None = None
    model: str | None = Field(default=None, max_length=100)


class ModeEstimate(BaseModel):
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal | None  # None when the model has no price on file (e.g. free tiers)


class EstimateOut(BaseModel):
    count: int
    provider: str
    model: str
    tags_only: ModeEstimate
    full: ModeEstimate


class ResolveIn(BaseModel):
    folder: str = Field(min_length=1, max_length=500)
    link: str | None = Field(default=None, max_length=500)  # None skips the folder


async def _owned(session: Session, user: User, job_id: uuid.UUID) -> ImportJob:
    job = await session.scalar(
        select(ImportJob).where(ImportJob.id == job_id, ImportJob.user_id == user.id)
    )
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Import not found")
    return job


async def _pending(session: Session, job: ImportJob) -> int:
    return await session.scalar(
        select(func.count()).where(
            Submission.user_id == job.user_id,
            Submission.import_job_id == job.id,
            Submission.status == SubmissionStatus.IMPORTED,
        )
    )


async def _out(session: Session, job: ImportJob) -> ImportOut:
    await session.refresh(job)  # updated_at is set by the database on every update
    return ImportOut(
        **{
            name: getattr(job, name)
            for name in ImportOut.model_fields
            if name not in ("unmatched", "pending")
        },
        unmatched=[
            UnmatchedFolderOut(
                folder=u["folder"],
                files=[
                    UnmatchedFileOut(path=f["path"], language=f["language"]) for f in u["files"]
                ],
            )
            for u in job.unmatched_folders or []
        ],
        pending=await _pending(session, job),
    )


@router.get("", response_model=list[ImportOut])
async def list_imports(user: CurrentUser, session: Session) -> list[ImportOut]:
    jobs = (
        await session.scalars(
            select(ImportJob)
            .where(ImportJob.user_id == user.id)
            .order_by(ImportJob.created_at.desc())
            .limit(10)
        )
    ).all()
    return [await _out(session, j) for j in jobs]


@router.post("", response_model=ImportOut, status_code=status.HTTP_201_CREATED)
async def start_import(
    body: ImportIn, user: CurrentUser, session: Session, queue: QueueDep, redis: RedisDep
) -> ImportOut:
    try:
        repository = parse_repo(body.repository)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from None
    busy = await session.scalar(
        select(ImportJob.id).where(
            ImportJob.user_id == user.id,
            ImportJob.status.in_([ImportStatus.PENDING, ImportStatus.RUNNING]),
        )
    )
    if busy:
        raise HTTPException(status.HTTP_409_CONFLICT, "An import is already running.")
    await enforce_rate_limit(redis, f"hb:rl:import:{user.id}", IMPORTS_PER_HOUR, 3600)
    job = ImportJob(user_id=user.id, repository=repository, unmatched_folders=[])
    session.add(job)
    await session.commit()
    await queue.enqueue_job("import_repository", str(job.id), _job_id=import_job_id(job.id))
    return await _out(session, job)


@router.get("/{job_id}", response_model=ImportOut)
async def get_import(job_id: uuid.UUID, user: CurrentUser, session: Session) -> ImportOut:
    return await _out(session, await _owned(session, user, job_id))


async def _average_tokens(session: Session, user: User, kind: ReviewKind) -> tuple[int, int]:
    row = (
        await session.execute(
            select(func.avg(Review.input_tokens), func.avg(Review.output_tokens))
            .join(Submission, Submission.id == Review.submission_id)
            .where(
                Submission.user_id == user.id,
                Review.kind == kind,
                Review.error.is_(None),
                Review.input_tokens > 0,
            )
        )
    ).one()
    if row[0] is None:
        return DEFAULT_TOKENS[kind]
    return int(row[0]), int(row[1])


@router.get("/{job_id}/estimate", response_model=EstimateOut)
async def estimate(
    job_id: uuid.UUID,
    user: CurrentUser,
    session: Session,
    provider: str | None = None,
    model: str | None = None,
) -> EstimateOut:
    """What analysing the not-yet-analysed solutions would take, before the user commits."""
    job = await _owned(session, user, job_id)
    provider, model = await _resolve_model(session, user, provider, model)
    count = await _pending(session, job)

    async def mode(kind: ReviewKind) -> ModeEstimate:
        per_in, per_out = await _average_tokens(session, user, kind)
        tokens_in, tokens_out = per_in * count, per_out * count
        return ModeEstimate(
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            cost_usd=estimate_cost(model, tokens_in, tokens_out),
        )

    return EstimateOut(
        count=count,
        provider=provider,
        model=model,
        tags_only=await mode(ReviewKind.TAGS),
        full=await mode(ReviewKind.FULL),
    )


@router.post("/{job_id}/analysis", response_model=ImportOut)
async def start_analysis(
    job_id: uuid.UUID, body: AnalysisIn, user: CurrentUser, session: Session, queue: QueueDep
) -> ImportOut:
    job = await _owned(session, user, job_id)
    if job.status != ImportStatus.COMPLETED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Wait for the import to finish first.")
    if job.analysis_status == ImportStatus.RUNNING:
        raise HTTPException(status.HTTP_409_CONFLICT, "Analysis is already running.")
    job.analysis_mode = body.mode
    job.analysis_error = None
    if body.mode == ImportAnalysisMode.NONE:
        job.analysis_status = ImportStatus.COMPLETED
        await session.commit()
        return await _out(session, job)

    job.analysis_provider, job.analysis_model = await _resolve_model(
        session, user, body.provider, body.model
    )
    pending = await _pending(session, job)
    if pending == 0:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Nothing left to analyse.")
    # A resumed analysis keeps its earlier counts.
    job.analysis_total = job.analysis_done + pending
    job.analysis_status = ImportStatus.RUNNING
    await session.commit()
    await queue.enqueue_job("analyze_import", str(job.id), _job_id=analysis_job_id(job.id))
    return await _out(session, job)


@router.post("/{job_id}/analysis/cancel", response_model=ImportOut)
async def cancel_analysis(job_id: uuid.UUID, user: CurrentUser, session: Session) -> ImportOut:
    """Stops after the submission in progress; resume later with the same or another model."""
    job = await _owned(session, user, job_id)
    if job.analysis_status == ImportStatus.RUNNING:
        job.analysis_status = ImportStatus.CANCELLED
        await session.commit()
    return await _out(session, job)


@router.post("/{job_id}/unmatched", response_model=ImportOut)
async def resolve_unmatched(
    job_id: uuid.UUID, body: ResolveIn, user: CurrentUser, session: Session, queue: QueueDep
) -> ImportOut:
    """Map a folder the importer couldn't match to a problem link, or skip it."""
    job = await _owned(session, user, job_id)
    folders = list(job.unmatched_folders or [])
    entry = next((u for u in folders if u["folder"] == body.folder), None)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That folder is not waiting to be mapped.")

    problem = None
    if body.link and body.link.strip():
        ref = parse_problem_link(body.link)
        if ref.platform == "other" and not ref.url.startswith(("http://", "https://")):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Paste the problem's link.")
        problem = await get_or_create_problem(session, ref.platform, ref.slug, ref.url)
        for f in entry["files"]:
            file = SolutionFile(path=f["path"], language=f["language"], code=f["code"])
            if await add_solution(session, job, problem, file):
                job.imported += 1
            else:
                job.duplicates += 1
    job.unmatched_folders = [u for u in folders if u["folder"] != body.folder]
    await session.commit()
    if problem is not None:
        await queue_metadata(queue, problem)
    return await _out(session, job)
