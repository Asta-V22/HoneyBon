"""GitHub import jobs: fetch a repository into submissions, then analyse them one at a time.

Analysis runs in slices: each `analyze_import` job works for about `ANALYSIS_SLICE_S` seconds and
queues the next slice, so no single job outlives the worker's timeout and a restart loses at most
one submission's work. A Redis lock keeps two slices of the same import from running at once.
"""

import hashlib
import logging
import time
import uuid
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.crypto import decrypt_secret
from app.imports.github import (
    ProblemFolder,
    RepoUnavailable,
    SolutionFile,
    download_archive,
    parse_archive,
)
from app.leetcode import ensure_metadata, needs_metadata
from app.models import ImportJob, Problem, ProviderCredential, Review, Submission
from app.models.enums import (
    ImportAnalysisMode,
    ImportStatus,
    ReviewKind,
    SubmissionSource,
    SubmissionStatus,
)
from app.problems import get_or_create_problem
from app.providers import get_adapter
from app.providers.base import ProviderAdapter, ProviderError
from app.reviews.pipeline import CallStats, ReviewFailed, generate_tags
from app.reviews.service import record_stats, review_input, run_review, store_verdict
from app.worker.recovery import analysis_job_id, metadata_job_id

log = logging.getLogger(__name__)

ANALYSIS_SLICE_S = 240
LOCK_TTL_S = 900
MAX_CONSECUTIVE_FAILURES = 3


def normalize_code(code: str) -> str:
    lines = code.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(line.rstrip() for line in lines).strip()


def import_external_id(repository: str, path: str, code: str) -> str:
    """Same file, same contents -> same ID, so a re-sync never imports a solution twice."""
    digest = hashlib.sha256(f"{repository}/{path}\n{normalize_code(code)}".encode()).hexdigest()
    return f"gh:{digest[:40]}"


async def add_solution(
    session: AsyncSession, job: ImportJob, problem: Problem, file: SolutionFile
) -> bool:
    """Store one solution file. False if the user already has it (from any source)."""
    external_id = import_external_id(job.repository, file.path, file.code)
    if await session.scalar(
        select(Submission.id).where(
            Submission.user_id == job.user_id, Submission.external_id == external_id
        )
    ):
        return False
    code = normalize_code(file.code)
    existing = (
        await session.scalars(
            select(Submission.code).where(
                Submission.user_id == job.user_id, Submission.problem_id == problem.id
            )
        )
    ).all()
    if any(normalize_code(c) == code for c in existing):
        return False  # the extension (or an earlier import) already captured this code
    session.add(
        Submission(
            user_id=job.user_id,
            problem_id=problem.id,
            code=file.code,
            language=file.language,
            source=SubmissionSource.IMPORT,
            status=SubmissionStatus.IMPORTED,
            external_id=external_id,
            import_job_id=job.id,
        )
    )
    await session.flush()
    return True


async def import_folder(session: AsyncSession, job: ImportJob, folder: ProblemFolder) -> Problem:
    problem = await get_or_create_problem(
        session,
        "leetcode",
        folder.slug,
        f"https://leetcode.com/problems/{folder.slug}/",
        folder.title,
        folder.difficulty,
        platform_question_id=folder.question_id,
    )
    for file in folder.files:
        if await add_solution(session, job, problem, file):
            job.imported += 1
        else:
            job.duplicates += 1
        job.processed += 1
    return problem


async def run_import(
    sessionmaker: async_sessionmaker[AsyncSession], queue: Any, job_id: uuid.UUID, transport=None
) -> None:
    async with sessionmaker() as session:
        job = await session.get(ImportJob, job_id)
        if job is None or job.status not in (ImportStatus.PENDING, ImportStatus.RUNNING):
            return
        job.status = ImportStatus.RUNNING
        job.error = None
        await session.commit()

        try:
            contents = parse_archive(await download_archive(job.repository, transport))
        except RepoUnavailable as exc:
            job.status = ImportStatus.FAILED
            job.error = str(exc)
            await session.commit()
            return

        job.total = sum(len(f.files) for f in contents.problems)
        job.processed = job.imported = job.duplicates = 0
        job.unmatched_folders = contents.unmatched
        await session.commit()

        wanted: list[uuid.UUID] = []
        try:
            for i, folder in enumerate(contents.problems):
                problem = await import_folder(session, job, folder)
                if needs_metadata(problem):
                    wanted.append(problem.id)
                if i % 20 == 19:
                    await session.commit()  # progress the UI can poll
        except Exception:
            log.exception("import %s crashed", job_id)
            await session.rollback()
            job.status = ImportStatus.FAILED
            job.error = "Something went wrong saving the imported solutions. Try again."
            await session.commit()
            return
        job.status = ImportStatus.COMPLETED
        await session.commit()
        log.info(
            "import %s: %d imported, %d duplicates, %d unmatched folders",
            job_id,
            job.imported,
            job.duplicates,
            len(job.unmatched_folders),
        )
    for problem_id in wanted:
        await queue.enqueue_job(
            "fetch_problem_metadata", str(problem_id), _job_id=metadata_job_id(problem_id)
        )


# ---------------------------------------------------------------- analysis


def _next_submission(job: ImportJob):
    return (
        select(Submission)
        .where(
            Submission.user_id == job.user_id,
            Submission.import_job_id == job.id,
            Submission.status == SubmissionStatus.IMPORTED,
        )
        .order_by(Submission.created_at, Submission.id)
        .limit(1)
        .options(selectinload(Submission.problem))
    )


async def _tag_one(
    session: AsyncSession,
    adapter: ProviderAdapter,
    job: ImportJob,
    submission: Submission,
    fetch_metadata: bool,
) -> str | None:
    """The cheap pass for one submission. Returns an error message, or None on success."""
    if fetch_metadata:
        await ensure_metadata(session, submission.problem)
    stats = CallStats()
    row = Review(
        submission_id=submission.id,
        kind=ReviewKind.TAGS,
        provider=job.analysis_provider,
        model=job.analysis_model,
    )
    error = None
    try:
        verdict = await generate_tags(adapter, job.analysis_model, review_input(submission), stats)
    except (ProviderError, ReviewFailed) as exc:
        error = str(exc)
    except Exception:
        log.exception("tag analysis of %s crashed", submission.id)
        error = "Something went wrong analysing this solution."
    if error is None:
        row.review_json = {"kind": "tags", "verdict": verdict.model_dump(mode="json")}
        store_verdict(row, verdict)
        submission.status = SubmissionStatus.REVIEWED
    else:
        row.error = error
        submission.status = SubmissionStatus.FAILED
    record_stats(row, stats)
    session.add(row)
    return error


async def _review_one(
    sessionmaker: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    redis: Redis,
    job: ImportJob,
    submission: Submission,
    adapter_factory,
) -> str | None:
    """A full review for one submission, run in-line so reviews never pile up in the queue."""
    row = Review(
        submission_id=submission.id, provider=job.analysis_provider, model=job.analysis_model
    )
    session.add(row)
    submission.status = SubmissionStatus.QUEUED
    await session.commit()
    await run_review(sessionmaker, redis, row.id, adapter_factory)
    await session.refresh(row)
    await session.refresh(submission)
    return None if submission.status == SubmissionStatus.REVIEWED else (row.error or "failed")


async def run_import_analysis(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    queue: Any,
    job_id: uuid.UUID,
    adapter_factory=get_adapter,
    slice_s: float = ANALYSIS_SLICE_S,
) -> None:
    lock = f"hb:lock:import-analysis:{job_id}"
    if not await redis.set(lock, "1", nx=True, ex=LOCK_TTL_S):
        return  # another slice of this import is running
    more = False
    try:
        more = await _analyse_slice(sessionmaker, redis, job_id, adapter_factory, slice_s)
    finally:
        await redis.delete(lock)
    if more:
        await queue.enqueue_job("analyze_import", str(job_id), _job_id=analysis_job_id(job_id))


async def _analyse_slice(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    job_id: uuid.UUID,
    adapter_factory,
    slice_s: float,
) -> bool:
    """Analyse submissions until the slice runs out. True if another slice is needed."""
    started = time.monotonic()
    async with sessionmaker() as session:
        job = await session.get(ImportJob, job_id)
        if job is None or job.analysis_status != ImportStatus.RUNNING:
            return False

        adapter = None
        if job.analysis_mode == ImportAnalysisMode.TAGS_ONLY:
            credential = await session.scalar(
                select(ProviderCredential).where(
                    ProviderCredential.user_id == job.user_id,
                    ProviderCredential.provider == job.analysis_provider,
                )
            )
            if credential is None:
                job.analysis_status = ImportStatus.FAILED
                job.analysis_error = f"No {job.analysis_provider} API key saved."
                await session.commit()
                return False
            adapter = adapter_factory(
                job.analysis_provider, decrypt_secret(credential.encrypted_key), credential.base_url
            )

        fetch_metadata = True
        consecutive_failures = 0
        while True:
            await session.refresh(job)  # sees a cancel from the API
            if job.analysis_status != ImportStatus.RUNNING:
                return False
            submission = await session.scalar(_next_submission(job))
            if submission is None:
                job.analysis_status = ImportStatus.COMPLETED
                await session.commit()
                return False

            if adapter is not None:
                error = await _tag_one(session, adapter, job, submission, fetch_metadata)
                # LeetCode often blocks cloud IPs; don't wait on it for every submission.
                fetch_metadata = fetch_metadata and not needs_metadata(submission.problem)
            else:
                error = await _review_one(
                    sessionmaker, session, redis, job, submission, adapter_factory
                )

            job.analysis_done += 1
            if error is None:
                consecutive_failures = 0
            else:
                job.analysis_failed += 1
                consecutive_failures += 1
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    job.analysis_status = ImportStatus.FAILED
                    job.analysis_error = (
                        f"Stopped after {MAX_CONSECUTIVE_FAILURES} failures in a row. "
                        f"Last error: {error}"
                    )
            await session.commit()
            if time.monotonic() - started > slice_s:
                return job.analysis_status == ImportStatus.RUNNING
