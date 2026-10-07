import uuid

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.models import ChatMessage, ChatThread, Problem, Review, Submission, User
from app.models.enums import ChatMessageStatus, ChatRole, SubmissionSource, SubmissionStatus
from app.worker.recovery import INTERRUPTED_REPLY, recover_interrupted, review_job_id
from tests.test_api import _login, _make_user, _paste, _with_key

NEON = (
    "postgresql://user:pw@ep-cool-1.ap-southeast-1.aws.neon.tech/neondb"
    "?sslmode=require&channel_binding=require"
)


def test_neon_url_is_adapted_for_asyncpg():
    settings = Settings(database_url=NEON)
    assert settings.database_url == (
        "postgresql+asyncpg://user:pw@ep-cool-1.ap-southeast-1.aws.neon.tech/neondb"
    )
    assert settings.engine_options["connect_args"] == {"ssl": "require"}


def test_local_url_is_untouched():
    url = "postgresql+asyncpg://honeybon:honeybon@localhost:5433/honeybon"
    settings = Settings(database_url=url)
    assert settings.database_url == url and "connect_args" not in settings.engine_options


def test_production_requires_secrets():
    with pytest.raises(RuntimeError, match="SESSION_SECRET, MASTER_KEY, FRONTEND_ORIGIN"):
        Settings(env="production", master_key="").check_production()
    Settings(
        env="production",
        master_key="k",
        session_secret="s" * 32,
        frontend_origin="https://honeybon.vercel.app",
    ).check_production()


async def test_api_responses_are_not_cacheable(client):
    response = await client.get("/api/health")
    assert response.headers["cache-control"] == "no-store"


async def test_review_enqueue_uses_a_stable_job_id(client, sessionmaker, queue):
    _login(client, await _make_user(sessionmaker, "alice"))
    await _with_key(client)
    body = await _paste(client)
    assert queue.job_ids == [review_job_id(body["review"]["id"])]


async def test_restart_requeues_reviews_and_closes_replies(sessionmaker, queue):
    async with sessionmaker() as session:
        user = User(github_id=1, github_login="alice")
        problem = Problem(platform="leetcode", slug="two-sum", topic_tags=[])
        session.add_all([user, problem])
        await session.flush()
        waiting = Submission(
            user_id=user.id,
            problem_id=problem.id,
            code="x",
            language="python",
            source=SubmissionSource.PASTE,
            status=SubmissionStatus.ANALYZING,
        )
        finished = Submission(
            user_id=user.id,
            problem_id=problem.id,
            code="y",
            language="python",
            source=SubmissionSource.PASTE,
            status=SubmissionStatus.REVIEWED,
        )
        session.add_all([waiting, finished])
        await session.flush()
        pending = Review(submission_id=waiting.id, provider="groq", model="m")
        session.add_all([pending, Review(submission_id=finished.id, provider="groq", model="m")])
        thread = ChatThread(user_id=user.id, problem_id=problem.id)
        session.add(thread)
        await session.flush()
        session.add(
            ChatMessage(
                thread_id=thread.id,
                role=ChatRole.ASSISTANT,
                content="half a rep",
                status=ChatMessageStatus.STREAMING,
            )
        )
        await session.commit()
        pending_id = pending.id

    await recover_interrupted(sessionmaker, queue)

    assert queue.jobs == [("review_submission", (str(pending_id),))]
    assert queue.job_ids == [review_job_id(pending_id)]
    async with sessionmaker() as session:
        reply = await session.scalar(select(ChatMessage))
        assert reply.status == ChatMessageStatus.FAILED and reply.error == INTERRUPTED_REPLY
    assert isinstance(pending_id, uuid.UUID)
