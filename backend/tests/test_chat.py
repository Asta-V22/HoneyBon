import json
import uuid

from sqlalchemy import select

from app.chat.service import chat_channel, run_chat_reply
from app.core.config import get_settings
from app.models import ChatMessage, ChatThread
from app.providers.base import ProviderError
from tests.fakes import ChatAdapter
from tests.test_api import _login, _make_user, _paste, _with_key


def _factory(adapter):
    return lambda name, key, base_url: adapter


async def _setup(client, sessionmaker, login="alice"):
    _login(client, await _make_user(sessionmaker, login))
    await _with_key(client)
    return await _paste(client)


async def _send(client, sub_id, content="Why is this O(n)?", **extra):
    res = await client.post(f"/api/submissions/{sub_id}/chat", json={"content": content, **extra})
    assert res.status_code == 200, res.text
    return res.json()


async def test_empty_thread_before_first_message(client, sessionmaker):
    sub = await _setup(client, sessionmaker)
    res = await client.get(f"/api/submissions/{sub['id']}/chat")
    assert res.json() == {"thread_id": None, "summarized_messages": 0, "messages": []}


async def test_send_queues_a_streaming_reply(client, sessionmaker, queue):
    sub = await _setup(client, sessionmaker)
    thread = await _send(client, sub["id"], quoted_selection="for i in range(n):")
    user_msg, reply = thread["messages"]
    assert user_msg["role"] == "user" and user_msg["quoted_selection"] == "for i in range(n):"
    assert reply["role"] == "assistant" and reply["status"] == "streaming"
    assert reply["model"] == "claude-opus-5-5"
    assert queue.jobs[-1] == ("chat_reply", (reply["id"], sub["id"]))

    res = await client.post(f"/api/submissions/{sub['id']}/chat", json={"content": "again"})
    assert res.status_code == 409


async def test_reply_streams_and_is_saved(client, sessionmaker, redis):
    sub = await _setup(client, sessionmaker)
    reply_id = (await _send(client, sub["id"], quoted_selection="int x = 0;"))["messages"][1]["id"]
    pubsub = redis.pubsub()
    await pubsub.subscribe(chat_channel(reply_id))

    adapter = ChatAdapter(["Because each index is visited once."])
    await run_chat_reply(
        sessionmaker, redis, uuid.UUID(reply_id), uuid.UUID(sub["id"]), _factory(adapter)
    )

    request = adapter.requests[0]
    assert "<user_code" in request.system and "<review>" in request.system
    assert request.messages[-1].content.startswith("<selection>\nint x = 0;")
    events = []
    for _ in range(50):  # get_message returns None once for the subscribe confirmation
        msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
        if msg is not None:
            events.append(json.loads(msg["data"]))
        if events and events[-1]["type"] == "done":
            break
    assert events[-1] == {"type": "done", "text": "Because each index is visited once."}
    await pubsub.aclose()

    thread = (await client.get(f"/api/submissions/{sub['id']}/chat")).json()
    reply = thread["messages"][1]
    assert reply["status"] == "done" and reply["content"] == "Because each index is visited once."


async def test_failed_reply_is_marked_and_next_message_allowed(client, sessionmaker, redis):
    sub = await _setup(client, sessionmaker)
    reply_id = (await _send(client, sub["id"]))["messages"][1]["id"]
    adapter = ChatAdapter([ProviderError("Gemini is overloaded right now.")])
    await run_chat_reply(
        sessionmaker, redis, uuid.UUID(reply_id), uuid.UUID(sub["id"]), _factory(adapter)
    )
    thread = (await client.get(f"/api/submissions/{sub['id']}/chat")).json()
    assert thread["messages"][1]["status"] == "failed"
    assert "overloaded" in thread["messages"][1]["error"]
    await _send(client, sub["id"], "Try again")  # no 409 once the reply has failed


async def test_long_history_is_summarized(client, sessionmaker, redis, monkeypatch):
    monkeypatch.setattr(get_settings(), "chat_history_char_budget", 400)
    sub = await _setup(client, sessionmaker)
    for i in range(4):
        reply_id = (await _send(client, sub["id"], f"question {i} " + "x" * 80))["messages"][-1][
            "id"
        ]
        adapter = ChatAdapter(
            [f"answer {i} " + "y" * 80], summary="SUMMARY: they asked about complexity."
        )
        await run_chat_reply(
            sessionmaker, redis, uuid.UUID(reply_id), uuid.UUID(sub["id"]), _factory(adapter)
        )

    final_request = adapter.requests[-1]
    assert "SUMMARY: they asked about complexity." in final_request.system
    assert final_request.messages[0].role == "user"
    assert len(final_request.messages) < 7  # older turns were folded away
    async with sessionmaker() as session:
        thread = await session.scalar(select(ChatThread))
        assert thread.summarized_through > 0
        assert (
            await session.scalar(select(ChatMessage).where(ChatMessage.status == "streaming"))
            is None
        )


async def test_threads_are_private(client, sessionmaker):
    sub = await _setup(client, sessionmaker, "alice")
    reply_id = (await _send(client, sub["id"]))["messages"][1]["id"]
    _login(client, await _make_user(sessionmaker, "bob"))
    assert (await client.get(f"/api/submissions/{sub['id']}/chat")).status_code == 404
    res = await client.post(f"/api/submissions/{sub['id']}/chat", json={"content": "hi"})
    assert res.status_code == 404
    assert (await client.get(f"/api/chat/messages/{reply_id}/events")).status_code == 404
