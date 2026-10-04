"""Generate one assistant reply in a discussion thread, streaming it to Redis as it arrives."""

import json
import logging
import time
import uuid

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from app.chat.prompts import SUMMARY_SYSTEM_PROMPT, chat_system, summary_request, user_turn
from app.core.config import get_settings
from app.core.crypto import decrypt_secret
from app.models import ChatMessage, ChatThread, ProviderCredential, Review, Submission
from app.models.enums import ChatMessageStatus, ChatRole
from app.providers import get_adapter
from app.providers.base import ChatRequest, Message, ProviderAdapter, ProviderError, Usage
from app.reviews.service import _input

log = logging.getLogger(__name__)

PUBLISH_INTERVAL_S = 0.15
KEEP_RECENT = 4  # turns never folded into the summary


def chat_channel(message_id: uuid.UUID | str) -> str:
    return f"hb:chat:{message_id}"


async def _publish(redis: Redis, message_id: uuid.UUID, type_: str, **data) -> None:
    await redis.publish(chat_channel(message_id), json.dumps({"type": type_, **data}))


async def _collect(adapter: ProviderAdapter, request: ChatRequest) -> tuple[str, Usage]:
    text, usage = [], Usage()
    async for chunk in adapter.chat(request):
        text.append(chunk.text)
        if chunk.usage:
            usage = chunk.usage
    return "".join(text), usage


def _as_message(m: ChatMessage) -> Message:
    content = user_turn(m.content, m.quoted_selection) if m.role == ChatRole.USER else m.content
    return Message(m.role.value, content)


async def _fold_history(
    adapter: ProviderAdapter, model: str, thread: ChatThread, history: list[ChatMessage]
) -> list[ChatMessage]:
    """Summarize older turns once the verbatim history passes the budget. Returns recent turns."""
    budget = get_settings().chat_history_char_budget
    recent = history[thread.summarized_through :]
    if sum(len(m.content) + len(m.quoted_selection or "") for m in recent) <= budget:
        return recent

    keep = len(recent)
    size = 0
    for i in range(len(recent) - 1, -1, -1):
        size += len(recent[i].content) + len(recent[i].quoted_selection or "")
        if size > budget // 2 and len(recent) - i > KEEP_RECENT:
            break
        keep = i
    # Start the verbatim part on a user turn so no reply is cut off from its question.
    while keep < len(recent) - 1 and recent[keep].role != ChatRole.USER:
        keep += 1
    folded, recent = recent[:keep], recent[keep:]
    if not folded:
        return recent

    transcript = "\n\n".join(f"{m.role.value}: {_as_message(m).content}" for m in folded)
    summary, _ = await _collect(
        adapter,
        ChatRequest(
            model=model,
            system=SUMMARY_SYSTEM_PROMPT,
            messages=[Message("user", summary_request(thread.summary, transcript))],
            max_tokens=1000,
        ),
    )
    thread.summary = summary.strip() or thread.summary
    thread.summarized_through += len(folded)
    return recent


async def run_chat_reply(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    message_id: uuid.UUID,
    submission_id: uuid.UUID,
    adapter_factory=get_adapter,
) -> None:
    async with sessionmaker() as session:
        reply = await session.get(ChatMessage, message_id)
        if reply is None or reply.status != ChatMessageStatus.STREAMING:
            return
        thread = await session.get(ChatThread, reply.thread_id)
        submission = await session.scalar(
            select(Submission)
            .where(Submission.id == submission_id, Submission.user_id == thread.user_id)
            .options(selectinload(Submission.problem))
        )
        try:
            if submission is None:
                raise ProviderError("That submission no longer exists.")
            review = await session.scalar(
                select(Review)
                .where(Review.submission_id == submission.id, Review.review_json.is_not(None))
                .order_by(Review.created_at.desc())
                .limit(1)
            )
            credential = await session.scalar(
                select(ProviderCredential).where(
                    ProviderCredential.user_id == thread.user_id,
                    ProviderCredential.provider == reply.provider,
                )
            )
            if credential is None:
                raise ProviderError(f"No {reply.provider} API key saved. Add one in Settings.")
            adapter = adapter_factory(
                reply.provider, decrypt_secret(credential.encrypted_key), credential.base_url
            )

            history = (
                await session.scalars(
                    select(ChatMessage)
                    .where(
                        ChatMessage.thread_id == thread.id,
                        ChatMessage.seq < reply.seq,
                        ChatMessage.status == ChatMessageStatus.DONE,
                    )
                    .order_by(ChatMessage.seq)
                )
            ).all()
            recent = await _fold_history(adapter, reply.model, thread, list(history))
            messages = [_as_message(m) for m in recent]
            while messages and messages[0].role != "user":
                messages.pop(0)

            request = ChatRequest(
                model=reply.model,
                system=chat_system(
                    _input(submission), review.review_json if review else None, thread.summary
                ),
                messages=messages,
            )
            text, usage, last_publish = "", Usage(), 0.0
            async for chunk in adapter.chat(request):
                if chunk.usage:
                    usage = chunk.usage
                if chunk.text:
                    text += chunk.text
                    if time.monotonic() - last_publish >= PUBLISH_INTERVAL_S:
                        # Full text each time: a late subscriber never misses anything.
                        await _publish(redis, reply.id, "text", text=text)
                        last_publish = time.monotonic()
            if not text.strip():
                raise ProviderError("The model returned an empty reply. Try again.")
        except Exception as exc:
            if not isinstance(exc, ProviderError):
                log.exception("chat reply %s crashed", message_id)
            error = str(exc) if isinstance(exc, ProviderError) else "Something went wrong."
            reply.status, reply.error = ChatMessageStatus.FAILED, error
            await session.commit()
            await _publish(redis, reply.id, "failed", error=error)
            return

        reply.content = text
        reply.status = ChatMessageStatus.DONE
        reply.input_tokens, reply.output_tokens = usage.input_tokens, usage.output_tokens
        await session.commit()
        await _publish(redis, reply.id, "done", text=text)
