"""Run one queued review end to end: load, call the provider, store, publish progress."""

import logging
import uuid
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.core.crypto import decrypt_secret
from app.core.events import publish
from app.models import ProviderCredential, Submission
from app.models import Review as ReviewRow
from app.models.enums import SubmissionStatus
from app.providers import get_adapter
from app.providers.base import ProviderAdapter, ProviderError
from app.reviews.pipeline import CallStats, ReviewFailed, generate_review
from app.reviews.pricing import estimate_cost
from app.reviews.prompts import ReviewInput
from app.reviews.schema import Review, ReviewPartA

log = logging.getLogger(__name__)


async def _load(session: AsyncSession, review_id: uuid.UUID) -> ReviewRow | None:
    return await session.scalar(
        select(ReviewRow)
        .where(ReviewRow.id == review_id)
        .options(selectinload(ReviewRow.submission).selectinload(Submission.problem))
    )


def _input(submission: Submission) -> ReviewInput:
    problem = submission.problem
    return ReviewInput(
        platform=problem.platform,
        problem_title=problem.title,
        problem_slug=problem.slug,
        problem_url=problem.url,
        difficulty=problem.difficulty,
        statement=submission.statement,
        language=submission.language,
        code=submission.code,
    )


async def run_review(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    review_id: uuid.UUID,
    adapter_factory=get_adapter,
) -> None:
    async with sessionmaker() as session:
        row = await _load(session, review_id)
        if row is None:
            log.warning("review %s vanished before it ran", review_id)
            return
        submission = row.submission
        sub_id = submission.id

        submission.status = SubmissionStatus.ANALYZING
        row.error = None
        await session.commit()
        await publish(redis, sub_id, "status", status=SubmissionStatus.ANALYZING.value)

        stats = CallStats()
        try:
            credential = await session.scalar(
                select(ProviderCredential).where(
                    ProviderCredential.user_id == submission.user_id,
                    ProviderCredential.provider == row.provider,
                )
            )
            if credential is None:
                raise ProviderError(f"No {row.provider} API key saved. Add one in Settings.")
            adapter: ProviderAdapter = adapter_factory(
                row.provider, decrypt_secret(credential.encrypted_key), credential.base_url
            )

            async def on_part_a(part: ReviewPartA) -> None:
                row.review_json = part.model_dump(mode="json")
                await session.commit()
                await publish(redis, sub_id, "part", part="a")

            review = await generate_review(adapter, row.model, _input(submission), stats, on_part_a)
        except (ProviderError, ReviewFailed) as exc:
            await _fail(session, redis, row, stats, str(exc))
            return
        except Exception:
            log.exception("review %s crashed", review_id)
            await _fail(session, redis, row, stats, "Something went wrong running this review.")
            return

        _store(row, review, stats)
        submission.status = SubmissionStatus.REVIEWED
        await session.commit()
        await publish(redis, sub_id, "done")
        log.info(
            "review %s done model=%s tokens=%s/%s latency_ms=%s cost=%s",
            review_id,
            row.served_model,
            row.input_tokens,
            row.output_tokens,
            row.latency_ms,
            row.cost_usd,
        )


def _record_stats(row: ReviewRow, stats: CallStats) -> None:
    row.served_model = stats.served_model
    row.input_tokens = stats.usage.input_tokens
    row.output_tokens = stats.usage.output_tokens
    row.latency_ms = stats.latency_ms
    row.repair_attempted = stats.repair_attempted
    row.cost_usd = estimate_cost(
        stats.served_model or row.model, stats.usage.input_tokens, stats.usage.output_tokens
    )
    row.completed_at = datetime.now(UTC)


def _store(row: ReviewRow, review: Review, stats: CallStats) -> None:
    verdict = review.verdict
    row.review_json = review.model_dump(mode="json")
    row.used_technique = verdict.used_technique.value
    row.optimal_techniques = [t.value for t in verdict.optimal_techniques]
    row.time_class = verdict.time.normalized.value
    row.space_class = verdict.space.normalized.value
    row.optimal_time_class = verdict.optimal_time.normalized.value
    row.optimal_space_class = verdict.optimal_space.normalized.value
    _record_stats(row, stats)


async def _fail(
    session: AsyncSession, redis: Redis, row: ReviewRow, stats: CallStats, error: str
) -> None:
    row.error = error
    _record_stats(row, stats)
    row.submission.status = SubmissionStatus.FAILED
    await session.commit()
    await publish(redis, row.submission_id, "failed", error=error)
