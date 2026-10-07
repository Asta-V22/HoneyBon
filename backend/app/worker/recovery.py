"""Pick up work a restart interrupted.

Free Redis hosting does not persist the queue, so jobs can vanish on a restart. Reviews still
waiting are queued again (job IDs make this a no-op if the job survived); chat replies that were
mid-stream are marked failed so the author can resend.
"""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import ChatMessage, Review, Submission
from app.models.enums import ChatMessageStatus, SubmissionStatus

log = logging.getLogger(__name__)

RECOVERY_WINDOW = timedelta(days=1)
INTERRUPTED_REPLY = "Interrupted by a server restart. Send your message again."


def review_job_id(review_id: object) -> str:
    return f"review:{review_id}"


def chat_job_id(message_id: object) -> str:
    return f"chat:{message_id}"


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

        result = await session.execute(
            update(ChatMessage)
            .where(ChatMessage.status == ChatMessageStatus.STREAMING)
            .values(status=ChatMessageStatus.FAILED, error=INTERRUPTED_REPLY)
        )
        await session.commit()
    if pending or result.rowcount:
        log.info("recovered %d reviews, closed %d chat replies", len(pending), result.rowcount)
