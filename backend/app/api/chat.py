import uuid
from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, QueueDep, RedisDep, Session, enforce_rate_limit
from app.api.sse import relay
from app.api.submissions import _owned_submission, _resolve_model
from app.chat.service import chat_channel
from app.core.config import get_settings
from app.models import ChatMessage, ChatThread
from app.models.enums import ChatMessageStatus, ChatRole

router = APIRouter(tags=["chat"])


class ChatMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: ChatRole
    content: str
    status: ChatMessageStatus
    error: str | None
    provider: str | None
    model: str | None
    quoted_selection: str | None
    created_at: datetime


class ThreadOut(BaseModel):
    thread_id: uuid.UUID | None
    summarized_messages: int
    messages: list[ChatMessageOut]


class ChatIn(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
    quoted_selection: str | None = Field(default=None, max_length=8000)
    provider: str | None = None
    model: str | None = Field(default=None, max_length=100)


async def _thread_out(session: Session, thread: ChatThread | None) -> ThreadOut:
    if thread is None:
        return ThreadOut(thread_id=None, summarized_messages=0, messages=[])
    messages = (
        await session.scalars(
            select(ChatMessage).where(ChatMessage.thread_id == thread.id).order_by(ChatMessage.seq)
        )
    ).all()
    return ThreadOut(
        thread_id=thread.id,
        summarized_messages=thread.summarized_through,
        messages=[ChatMessageOut.model_validate(m) for m in messages],
    )


async def _thread_for(session: Session, user_id: uuid.UUID, problem_id: uuid.UUID):
    return await session.scalar(
        select(ChatThread).where(ChatThread.user_id == user_id, ChatThread.problem_id == problem_id)
    )


@router.get("/submissions/{submission_id}/chat", response_model=ThreadOut)
async def get_thread(submission_id: uuid.UUID, user: CurrentUser, session: Session) -> ThreadOut:
    """The problem's discussion thread (one per user and problem)."""
    submission = await _owned_submission(session, user, submission_id)
    return await _thread_out(session, await _thread_for(session, user.id, submission.problem_id))


@router.post("/submissions/{submission_id}/chat", response_model=ThreadOut)
async def send_message(
    submission_id: uuid.UUID,
    body: ChatIn,
    user: CurrentUser,
    session: Session,
    queue: QueueDep,
    redis: RedisDep,
) -> ThreadOut:
    submission = await _owned_submission(session, user, submission_id)
    await enforce_rate_limit(
        redis, f"hb:rl:chat:{user.id}", get_settings().chat_rate_limit_per_hour, 3600
    )
    provider, model = await _resolve_model(session, user, body.provider, body.model)

    thread = await _thread_for(session, user.id, submission.problem_id)
    if thread is None:
        thread = ChatThread(user_id=user.id, problem_id=submission.problem_id)
        session.add(thread)
        await session.flush()
    elif await session.scalar(
        select(ChatMessage.id).where(
            ChatMessage.thread_id == thread.id, ChatMessage.status == ChatMessageStatus.STREAMING
        )
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Wait for the current reply to finish.")

    session.add(
        ChatMessage(
            thread_id=thread.id,
            role=ChatRole.USER,
            content=body.content.strip(),
            quoted_selection=(body.quoted_selection or "").strip() or None,
        )
    )
    await session.flush()  # the user turn gets its seq before the reply
    reply = ChatMessage(
        thread_id=thread.id,
        role=ChatRole.ASSISTANT,
        content="",
        status=ChatMessageStatus.STREAMING,
        provider=provider,
        model=model,
    )
    session.add(reply)
    await session.commit()
    await queue.enqueue_job("chat_reply", str(reply.id), str(submission.id))
    return await _thread_out(session, thread)


@router.get("/chat/messages/{message_id}/events")
async def message_events(
    message_id: uuid.UUID, user: CurrentUser, session: Session, redis: RedisDep
) -> StreamingResponse:
    """Server-sent events while a reply streams: `text` events carry the full text so far."""
    owned = await session.scalar(
        select(ChatMessage.id)
        .join(ChatThread, ChatThread.id == ChatMessage.thread_id)
        .where(ChatMessage.id == message_id, ChatThread.user_id == user.id)
    )
    if owned is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Message not found")
    return relay(redis, chat_channel(message_id))
