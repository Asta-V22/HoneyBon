"""Pick up work a restart interrupted.

Free Redis hosting does not persist the queue, so jobs can vanish on a restart. Reviews and
imports still running are queued again (job IDs and a lock make this a no-op if the job
survived); chat replies that were mid-stream are marked failed so the author can resend.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import ChatMessage, ImportJob, Review, Submission
from app.models.enums import ChatMessageStatus, ImportStatus, SubmissionStatus

log = logging.getLogger(__name__)

RECOVERY_WINDOW = timedelta(days=1)
INTERRUPTED_REPLY = "Interrupted by a server restart. Send your message again."


def review_job_id(review_id: object) -> str:
    return f"review:{review_id}"


def chat_job_id(message_id: object) -> str:
    return f"chat:{message_id}"


def metadata_job_id(problem_id: object) -> str:
    return f"meta:{problem_id}"


def import_job_id(job_id: object) -> str:
    return f"import:{job_id}"


def analysis_job_id(job_id: object) -> str:
    # Unique per slice: the import's own lock stops two slices running at once.
    return f"import-analysis:{job_id}:{uuid.uuid4().hex[:12]}"


async def recover_interrupted(sessionmaker: async_sessionmaker[AsyncSession], queue) -> None:
    async with sessionmaker() as session:
        pending = (
            await session.scalars(
                select(Review.id)
                .join(Submission, Submission.id == Review.submission_id)
                .where(
                    Review.completed_at.is_(None),
                    Review.created_at > datetime.now(UTC) - RECOVERY_WINDOW,
                    Submission.status.in_([SubmissionStatus.QUEUED, SubmissionStatus.ANALYZING]),
                )
            )
        ).all()
        for review_id in pending:
            await queue.enqueue_job(
                "review_submission", str(review_id), _job_id=review_job_id(review_id)
            )

        recent = ImportJob.updated_at > datetime.now(UTC) - RECOVERY_WINDOW
        fetching = (
            await session.scalars(
                select(ImportJob.id).where(ImportJob.status == ImportStatus.RUNNING, recent)
            )
        ).all()
        for job_id in fetching:
            await queue.enqueue_job("import_repository", str(job_id), _job_id=import_job_id(job_id))
        analysing = (
            await session.scalars(
                select(ImportJob.id).where(
                    ImportJob.analysis_status == ImportStatus.RUNNING, recent
                )
            )
        ).all()
        for job_id in analysing:
            await queue.enqueue_job("analyze_import", str(job_id), _job_id=analysis_job_id(job_id))

        result = await session.execute(
            update(ChatMessage)
            .where(ChatMessage.status == ChatMessageStatus.STREAMING)
            .values(status=ChatMessageStatus.FAILED, error=INTERRUPTED_REPLY)
        )
        await session.commit()
    if pending or result.rowcount or fetching or analysing:
        log.info(
            "recovered %d reviews and %d imports, closed %d chat replies",
            len(pending),
            len(fetching) + len(analysing),
            result.rowcount,
        )
