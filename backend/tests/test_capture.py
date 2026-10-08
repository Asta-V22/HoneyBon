import httpx
import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.leetcode import ensure_metadata, fetch_question
from app.models import Problem
from tests.test_api import _login, _make_user, _with_key

CODE = "class Solution:\n    def checkValidString(self, s):\n        return True"


def _capture_body(**overrides) -> dict:
    return {
        "slug": "valid-parenthesis-string",
        "submission_id": "1234567890",
        "status": "Accepted",
        "language": "python3",
        "code": CODE,
        "runtime_ms": 31,
        "memory_kb": 17900,
        "title": "Valid Parenthesis String",
        "difficulty": "Medium",
    } | overrides


async def _token(client, sessionmaker, login="alice") -> str:
    _login(client, await _make_user(sessionmaker, login))
    res = await client.post("/api/me/tokens", json={"name": "Chrome"})
    assert res.status_code == 201
    return res.json()["token"]


async def _capture(client, token, **overrides):
    return await client.post(
        "/api/capture",
        json=_capture_body(**overrides),
        headers={"Authorization": f"Bearer {token}"},
    )


# ---------------------------------------------------------------- LeetCode metadata


def _leetcode(payload):
    return httpx.MockTransport(lambda request: httpx.Response(200, json=payload))


QUESTION = {
    "questionId": "678",
    "questionFrontendId": "678",
    "title": "Valid Parenthesis String",
    "difficulty": "Medium",
    "topicTags": [{"slug": "greedy"}, {"slug": "stack"}],
}


async def test_fetch_question_parses_metadata():
    q = await fetch_question(
        "valid-parenthesis-string", _leetcode({"data": {"question": QUESTION}})
    )
    assert (q.title, q.difficulty, q.topic_tags, q.frontend_id) == (
        "Valid Parenthesis String",
        "Medium",
        ["greedy", "stack"],
        "678",
    )
    assert await fetch_question("nope", _leetcode({"data": {"question": None}})) is None


async def test_ensure_metadata_fills_a_problem(sessionmaker, monkeypatch):
    monkeypatch.setattr(get_settings(), "leetcode_metadata", True)
    async with sessionmaker() as session:
        problem = Problem(platform="leetcode", slug="valid-parenthesis-string", topic_tags=[])
        session.add(problem)
        assert await ensure_metadata(session, problem, _leetcode({"data": {"question": QUESTION}}))
        assert problem.topic_tags == ["greedy", "stack"] and problem.metadata_fetched_at
        # Fresh metadata is not fetched again.
        blocked = httpx.MockTransport(lambda r: httpx.Response(403))
        assert await ensure_metadata(session, problem, blocked)


async def test_blocked_leetcode_is_not_fatal(sessionmaker, monkeypatch):
    monkeypatch.setattr(get_settings(), "leetcode_metadata", True)
    async with sessionmaker() as session:
        problem = Problem(platform="leetcode", slug="two-sum", topic_tags=[])
        blocked = httpx.MockTransport(lambda r: httpx.Response(403, text="cloudflare"))
        assert await ensure_metadata(session, problem, blocked) is False
        assert problem.metadata_fetched_at is None  # retried next time


# ---------------------------------------------------------------- tokens


async def test_tokens_are_shown_once_and_stored_hashed(client, sessionmaker):
    token = await _token(client, sessionmaker)
    assert token.startswith("hb_")
    listed = (await client.get("/api/me/tokens")).json()
    assert len(listed) == 1 and listed[0]["last_four"] == token[-4:]
    assert token not in str(listed)


async def test_revoked_token_stops_working(client, sessionmaker):
    token = await _token(client, sessionmaker)
    token_id = (await client.get("/api/me/tokens")).json()[0]["id"]
    assert (await client.delete(f"/api/me/tokens/{token_id}")).status_code == 204
    assert (await _capture(client, token)).status_code == 401


async def test_token_only_works_for_capture(client, sessionmaker):
    token = await _token(client, sessionmaker)
    client.cookies.clear()
    headers = {"Authorization": f"Bearer {token}"}
    assert (await client.get("/api/me", headers=headers)).status_code == 401
    assert (await client.get("/api/submissions", headers=headers)).status_code == 401
    assert (await client.get("/api/capture/mode", headers=headers)).status_code == 200


async def test_users_cannot_revoke_each_others_tokens(client, sessionmaker):
    await _token(client, sessionmaker, "alice")
    token_id = (await client.get("/api/me/tokens")).json()[0]["id"]
    _login(client, await _make_user(sessionmaker, "bob"))
    assert (await client.delete(f"/api/me/tokens/{token_id}")).status_code == 404


# ---------------------------------------------------------------- capture


async def test_analyze_mode_reviews_immediately(client, sessionmaker, queue):
    token = await _token(client, sessionmaker)
    await _with_key(client)
    body = (await _capture(client, token)).json()
    assert body["result"] == "reviewing" and body["url"].endswith(body["submission_id"])
    assert "review_submission" in [name for name, _ in queue.jobs]

    detail = (await client.get(f"/api/submissions/{body['submission_id']}")).json()
    assert detail["source"] == "extension" and detail["language"] == "python"
    assert detail["problem"]["title"] == "Valid Parenthesis String"
    assert detail["problem"]["difficulty"] == "Medium"


async def test_analyze_mode_without_a_key_keeps_it_queued(client, sessionmaker):
    token = await _token(client, sessionmaker)
    body = (await _capture(client, token)).json()
    assert body["result"] == "queued" and "API key" in body["message"]


async def test_capture_mode_fills_the_review_queue(client, sessionmaker, queue):
    token = await _token(client, sessionmaker)
    await _with_key(client)
    await client.patch("/api/me", json={"capture_mode": "capture"})
    body = (await _capture(client, token)).json()
    assert body["result"] == "queued"
    assert "review_submission" not in [name for name, _ in queue.jobs]

    in_queue = (await client.get("/api/submissions", params={"in_queue": True})).json()
    assert [i["id"] for i in in_queue["items"]] == [body["submission_id"]]

    res = await client.post("/api/submissions/analyze-all", json={})
    assert res.json() == {"queued": 1, "remaining": 0}
    assert (await client.get("/api/submissions", params={"in_queue": True})).json()["total"] == 0


async def test_off_mode_and_failed_submissions_are_ignored(client, sessionmaker):
    token = await _token(client, sessionmaker)
    rejected = (await _capture(client, token, status="Wrong Answer")).json()
    assert rejected["result"] == "ignored"
    await client.patch("/api/me", json={"capture_mode": "off"})
    assert (await _capture(client, token)).json()["result"] == "ignored"
    assert (await client.get("/api/submissions")).json()["total"] == 0


async def test_same_submission_is_never_captured_twice(client, sessionmaker):
    token = await _token(client, sessionmaker)
    first = (await _capture(client, token)).json()
    again = (await _capture(client, token)).json()
    assert again["result"] == "duplicate" and again["submission_id"] == first["submission_id"]
    # A new accepted submission on the same problem is a new attempt.
    second = (await _capture(client, token, submission_id="1234567891")).json()
    assert second["result"] in ("queued", "reviewing")
    async with sessionmaker() as session:
        assert len((await session.scalars(select(Problem))).all()) == 1


async def test_popup_reads_and_sets_the_capture_mode(client, sessionmaker):
    token = await _token(client, sessionmaker)
    headers = {"Authorization": f"Bearer {token}"}
    res = await client.put("/api/capture/mode", json={"capture_mode": "capture"}, headers=headers)
    assert res.json()["capture_mode"] == "capture"
    assert (await client.get("/api/me")).json()["capture_mode"] == "capture"  # in sync
    tokens = (await client.get("/api/me/tokens")).json()
    assert tokens[0]["last_used_at"] is not None


@pytest.mark.parametrize("slug", ["../etc", "Two Sum", "a--b", ""])
async def test_bad_slugs_are_rejected(client, sessionmaker, slug):
    token = await _token(client, sessionmaker)
    assert (await _capture(client, token, slug=slug)).status_code == 422
