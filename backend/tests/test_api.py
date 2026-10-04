import uuid

import pytest
from sqlalchemy import select

from app.core.crypto import decrypt_secret
from app.core.sessions import SESSION_COOKIE, _serializer
from app.models import ProviderCredential, Review, Submission, User
from app.reviews.service import run_review
from tests.fakes import ScriptedAdapter

LEETCODE = "https://leetcode.com/problems/rotting-oranges/description/"
CODE = "class Solution {\npublic:\n  int orangesRotting(vector<vector<int>>& g) { return 0; }\n};"


async def _make_user(sessionmaker, login: str) -> User:
    async with sessionmaker() as session:
        user = User(github_id=abs(hash(login)) % 10**9, github_login=login)
        session.add(user)
        await session.commit()
        return user


def _login(client, user: User) -> None:
    client.cookies.set(SESSION_COOKIE, _serializer().dumps(str(user.id)))


async def _with_key(client) -> None:
    res = await client.put("/api/me/providers/anthropic", json={"api_key": "sk-ant-test-1234"})
    assert res.status_code == 200


async def _paste(client, **extra) -> dict:
    res = await client.post("/api/submissions", json={"code": CODE, "link": LEETCODE, **extra})
    assert res.status_code == 201, res.text
    return res.json()


async def test_requires_login(client):
    assert (await client.get("/api/me")).status_code == 401
    assert (await client.get("/api/submissions")).status_code == 401


async def test_dev_login_sets_session(client):
    assert (await client.post("/api/auth/dev-login")).status_code == 204
    me = (await client.get("/api/me")).json()
    assert me["github_login"] == "dev" and me["capture_mode"] == "analyze"
    await client.post("/api/auth/logout")
    client.cookies.clear()
    assert (await client.get("/api/me")).status_code == 401


async def test_provider_key_is_encrypted_and_never_returned(client, sessionmaker):
    _login(client, await _make_user(sessionmaker, "alice"))
    res = await client.put("/api/me/providers/anthropic", json={"api_key": "sk-ant-secret-9876"})
    body = res.json()
    assert "sk-ant-secret" not in res.text
    assert body["providers"] == [{"provider": "anthropic", "last_four": "9876", "base_url": None}]
    assert body["default_provider"] == "anthropic"
    async with sessionmaker() as session:
        cred = await session.scalar(select(ProviderCredential))
        assert b"sk-ant-secret" not in cred.encrypted_key
        assert decrypt_secret(cred.encrypted_key) == "sk-ant-secret-9876"


async def test_paste_needs_a_key(client, sessionmaker):
    _login(client, await _make_user(sessionmaker, "alice"))
    res = await client.post("/api/submissions", json={"code": CODE, "link": LEETCODE})
    assert res.status_code == 400 and "API key" in res.json()["detail"]


async def test_paste_needs_link_or_statement(client, sessionmaker):
    _login(client, await _make_user(sessionmaker, "alice"))
    await _with_key(client)
    assert (await client.post("/api/submissions", json={"code": CODE})).status_code == 422


async def test_paste_queues_a_review(client, sessionmaker, queue):
    _login(client, await _make_user(sessionmaker, "alice"))
    await _with_key(client)
    body = await _paste(client)
    assert body["status"] == "queued" and body["language"] == "cpp"
    assert body["problem"]["platform"] == "leetcode"
    assert body["problem"]["slug"] == "rotting-oranges"
    assert body["review"]["model"] == "claude-opus-5-5"
    assert queue.jobs == [("review_submission", (body["review"]["id"],))]


async def test_statement_paste_for_other_platforms(client, sessionmaker):
    _login(client, await _make_user(sessionmaker, "alice"))
    await _with_key(client)
    body = await _paste(client, link=None, statement="Given n, print n.", language="python")
    assert body["problem"]["platform"] == "other" and body["statement"] == "Given n, print n."


async def test_users_cannot_see_each_others_data(client, sessionmaker):
    alice = await _make_user(sessionmaker, "alice")
    bob = await _make_user(sessionmaker, "bob")
    _login(client, alice)
    await _with_key(client)
    sub_id = (await _paste(client))["id"]

    _login(client, bob)
    await _with_key(client)
    assert (await client.get(f"/api/submissions/{sub_id}")).status_code == 404
    assert (await client.get(f"/api/submissions/{sub_id}/events")).status_code == 404
    assert (await client.post(f"/api/submissions/{sub_id}/reviews", json={})).status_code == 404
    assert (await client.get("/api/submissions")).json() == {"items": [], "total": 0}
    assert (await client.get("/api/me/export")).json()["submissions"] == []


def _factory(adapter):
    return lambda name, key, base_url: adapter


async def test_worker_stores_a_review(client, sessionmaker, redis, part_a, part_b):
    _login(client, await _make_user(sessionmaker, "alice"))
    await _with_key(client)
    body = await _paste(client)

    await run_review(
        sessionmaker,
        redis,
        uuid.UUID(body["review"]["id"]),
        _factory(ScriptedAdapter([part_a, part_b])),
    )

    detail = (await client.get(f"/api/submissions/{body['id']}")).json()
    review = detail["review"]
    assert detail["status"] == "reviewed"
    assert review["review_json"]["tier3"]["insight"]
    assert review["used_technique"] == "simulation"
    assert review["optimal_techniques"] == ["graph_bfs"]
    assert review["input_tokens"] == 200 and review["cost_usd"] is not None

    library = (await client.get("/api/submissions", params={"suboptimal": True})).json()
    assert library["total"] == 1 and library["items"][0]["review"]["used_technique"] == "simulation"
    by_technique = await client.get("/api/submissions", params={"technique": "graph_bfs"})
    assert by_technique.json()["total"] == 1
    assert (await client.get("/api/submissions", params={"q": "zzz"})).json()["total"] == 0


async def test_failed_review_can_be_retried(client, sessionmaker, redis, queue, part_a):
    _login(client, await _make_user(sessionmaker, "alice"))
    await _with_key(client)
    body = await _paste(client)

    await run_review(
        sessionmaker, redis, uuid.UUID(body["review"]["id"]), _factory(ScriptedAdapter(["x", "y"]))
    )
    detail = (await client.get(f"/api/submissions/{body['id']}")).json()
    assert detail["status"] == "failed" and "validation" in detail["review"]["error"]

    res = await client.post(
        f"/api/submissions/{body['id']}/reviews", json={"model": "claude-sonnet-5-5"}
    )
    assert res.status_code == 200
    assert res.json()["status"] == "queued" and res.json()["review"]["model"] == "claude-sonnet-5-5"
    assert len(queue.jobs) == 2


async def test_delete_account_removes_everything(client, sessionmaker):
    _login(client, await _make_user(sessionmaker, "alice"))
    await _with_key(client)
    await _paste(client)
    assert (await client.delete("/api/me")).status_code == 204
    async with sessionmaker() as session:
        assert await session.scalar(select(User)) is None
        assert await session.scalar(select(Submission)) is None
        assert await session.scalar(select(Review)) is None


@pytest.mark.parametrize(
    ("link", "platform", "slug"),
    [
        ("https://leetcode.com/problems/two-sum/", "leetcode", "two-sum"),
        ("https://codeforces.com/contest/1850/problem/C", "codeforces", "1850C"),
        ("https://codeforces.com/problemset/problem/4/A", "codeforces", "4A"),
    ],
)
def test_parse_problem_link(link, platform, slug):
    from app.problems import parse_problem_link

    ref = parse_problem_link(link)
    assert (ref.platform, ref.slug) == (platform, slug)
