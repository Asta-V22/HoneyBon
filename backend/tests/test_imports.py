import io
import tarfile

import httpx
import pytest
from sqlalchemy import select

from app.imports.github import RepoUnavailable, parse_archive, parse_repo
from app.imports.service import run_import, run_import_analysis
from app.models import ImportJob, Review, Submission
from app.models.enums import ImportStatus, ReviewKind, SubmissionSource, SubmissionStatus
from tests.conftest import FakeQueue
from tests.fakes import ScriptedAdapter
from tests.test_api import _login, _make_user, _with_key

README = (
    '<h2><a href="https://leetcode.com/problems/rotting-oranges">Rotting Oranges</a></h2> '
    "<img src='https://img.shields.io/badge/Difficulty-Medium-orange' alt='Difficulty: Medium' />"
    "<hr><p>You are given an <code>m x n</code> grid...</p>"
)
ORANGES = "class Solution {\npublic:\n    int orangesRotting(vector<vector<int>>& g) {}\n};\n"
TWO_SUM = "class Solution:\n    def twoSum(self, nums, target):\n        return []\n"


def _tarball(files: dict[str, str | bytes], links: tuple[str, ...] = ()) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for path, content in files.items():
            data = content.encode() if isinstance(content, str) else content
            info = tarfile.TarInfo(f"LeetCode-abc123/{path}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for path in links:
            info = tarfile.TarInfo(f"LeetCode-abc123/{path}")
            info.type = tarfile.SYMTYPE
            info.linkname = "/etc/passwd"
            tar.addfile(info)
    return buffer.getvalue()


REPO_FILES = {
    "README.md": "# My solutions",
    "1036-rotting-oranges/README.md": README,
    "1036-rotting-oranges/rotting-oranges.cpp": ORANGES,
    "1036-rotting-oranges/Notes.md": "BFS from every rotten orange.",
    "0001-two-sum/two-sum.py": TWO_SUM,
    "misc/my-sort.java": "class Sort {}",
    ".github/workflows/x.py": "print('not a solution')",
    "0002-add-two-numbers/add-two-numbers.cpp": b"\xff\xfe binary",
}


def _github(archive: bytes, status: int = 200):
    return httpx.MockTransport(lambda request: httpx.Response(status, content=archive))


# ---------------------------------------------------------------- parsing


@pytest.mark.parametrize(
    "text",
    [
        "https://github.com/Asta-V22/LeetCode",
        "github.com/Asta-V22/LeetCode/",
        "https://github.com/Asta-V22/LeetCode.git",
        "Asta-V22/LeetCode",
    ],
)
def test_parse_repo(text):
    assert parse_repo(text) == "Asta-V22/LeetCode"


@pytest.mark.parametrize(
    "text", ["https://gitlab.com/a/b", "https://github.com/a", "a/b/c", "https://github.com/a/.."]
)
def test_parse_repo_rejects_others(text):
    with pytest.raises(ValueError):
        parse_repo(text)


def test_parse_archive_reads_leethub_layout():
    contents = parse_archive(_tarball(REPO_FILES, links=("9-x/link.py",)))
    by_slug = {p.slug: p for p in contents.problems}
    assert set(by_slug) == {"two-sum", "rotting-oranges"}  # binary and linked files skipped

    oranges = by_slug["rotting-oranges"]
    # Folder numbers are LeetCode's internal IDs: 1036 is problem #994.
    assert (oranges.question_id, oranges.title, oranges.difficulty) == (
        "1036",
        "Rotting Oranges",
        "Medium",
    )
    assert [(f.language, f.code) for f in oranges.files] == [("cpp", ORANGES)]
    assert by_slug["two-sum"].question_id == "1"  # zero padding stripped
    assert by_slug["two-sum"].title is None  # no README

    assert contents.unmatched == [
        {
            "folder": "misc",
            "files": [{"path": "misc/my-sort.java", "language": "java", "code": "class Sort {}"}],
        }
    ]


def test_parse_archive_rejects_garbage():
    with pytest.raises(RepoUnavailable):
        parse_archive(b"<html>not a tarball</html>")


# ---------------------------------------------------------------- the import job


async def _job(sessionmaker, user, repository="Asta-V22/LeetCode") -> ImportJob:
    async with sessionmaker() as session:
        job = ImportJob(user_id=user.id, repository=repository, unmatched_folders=[])
        session.add(job)
        await session.commit()
        return job


async def _submissions(sessionmaker, user) -> list[Submission]:
    async with sessionmaker() as session:
        return list(
            (
                await session.scalars(
                    select(Submission)
                    .where(Submission.user_id == user.id)
                    .order_by(Submission.created_at)
                )
            ).all()
        )


async def test_import_creates_submissions_and_never_duplicates(sessionmaker):
    user = await _make_user(sessionmaker, "alice")
    archive = _tarball(REPO_FILES)
    queue = FakeQueue()
    job = await _job(sessionmaker, user)
    await run_import(sessionmaker, queue, job.id, _github(archive))

    async with sessionmaker() as session:
        job = await session.get(ImportJob, job.id)
        assert (job.status, job.total, job.imported, job.duplicates) == (
            ImportStatus.COMPLETED,
            2,
            2,
            0,
        )
        assert [u["folder"] for u in job.unmatched_folders] == ["misc"]
    subs = await _submissions(sessionmaker, user)
    assert {(s.source, s.status, s.import_job_id) for s in subs} == {
        (SubmissionSource.IMPORT, SubmissionStatus.IMPORTED, job.id)
    }
    assert {name for name, _ in queue.jobs} == {"fetch_problem_metadata"}

    # A re-sync imports nothing new.
    again = await _job(sessionmaker, user)
    await run_import(sessionmaker, FakeQueue(), again.id, _github(archive))
    async with sessionmaker() as session:
        again = await session.get(ImportJob, again.id)
        assert (again.imported, again.duplicates) == (0, 2)
    assert len(await _submissions(sessionmaker, user)) == 2


async def test_import_skips_code_the_extension_already_captured(client, sessionmaker):
    user = await _make_user(sessionmaker, "alice")
    _login(client, user)
    token = (await client.post("/api/me/tokens", json={"name": "t"})).json()["token"]
    await client.put("/api/me", json={"capture_mode": "capture"})
    res = await client.post(
        "/api/capture",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "slug": "two-sum",
            "submission_id": "99",
            "status": "Accepted",
            "language": "python3",
            "code": TWO_SUM.replace("\n", "\r\n") + "\n\n",  # same code, other line endings
        },
    )
    assert res.json()["result"] == "queued"

    job = await _job(sessionmaker, user)
    await run_import(sessionmaker, FakeQueue(), job.id, _github(_tarball(REPO_FILES)))
    async with sessionmaker() as session:
        job = await session.get(ImportJob, job.id)
        assert (job.imported, job.duplicates) == (1, 1)


async def test_import_reports_a_missing_repository(sessionmaker):
    user = await _make_user(sessionmaker, "alice")
    job = await _job(sessionmaker, user, "nobody/nothing")
    await run_import(sessionmaker, FakeQueue(), job.id, _github(b"Not Found", 404))
    async with sessionmaker() as session:
        job = await session.get(ImportJob, job.id)
        assert job.status == ImportStatus.FAILED
        assert "no public repository nobody/nothing" in job.error


# ---------------------------------------------------------------- analysis


def _tags(used="graph_bfs", optimal=("graph_bfs",), time="n", best_time="n") -> dict:
    return {
        "correct": True,
        "summary": "Multi-source BFS.",
        "time": {"display": f"O({time})", "normalized": time},
        "space": {"display": "O(n)", "normalized": "n"},
        "used_technique": used,
        "optimal_techniques": list(optimal),
        "optimal_time": {"display": f"O({best_time})", "normalized": best_time},
        "optimal_space": {"display": "O(n)", "normalized": "n"},
    }


async def _imported(client, sessionmaker) -> tuple:
    user = await _make_user(sessionmaker, "alice")
    _login(client, user)
    await _with_key(client)
    job = await _job(sessionmaker, user)
    await run_import(sessionmaker, FakeQueue(), job.id, _github(_tarball(REPO_FILES)))
    return user, job


async def test_tag_analysis_fills_the_matrix_fields(client, sessionmaker, redis, queue):
    user, job = await _imported(client, sessionmaker)

    estimate = (await client.get(f"/api/imports/{job.id}/estimate")).json()
    assert estimate["count"] == 2
    assert estimate["tags_only"]["input_tokens"] < estimate["full"]["input_tokens"]
    assert estimate["full"]["cost_usd"] is not None  # Anthropic models are priced

    res = await client.post(f"/api/imports/{job.id}/analysis", json={"mode": "tags_only"})
    assert res.status_code == 200, res.text
    assert (res.json()["analysis_status"], res.json()["analysis_total"]) == ("running", 2)
    assert queue.jobs[-1] == ("analyze_import", (str(job.id),))

    adapter = ScriptedAdapter([_tags(), _tags("brute_force", ("hashing",), "n^2", "n")])
    await run_import_analysis(sessionmaker, redis, FakeQueue(), job.id, lambda *a: adapter)

    async with sessionmaker() as session:
        job = await session.get(ImportJob, job.id)
        assert (job.analysis_status, job.analysis_done, job.analysis_failed) == (
            ImportStatus.COMPLETED,
            2,
            0,
        )
        reviews = (await session.scalars(select(Review))).all()
    assert {r.kind for r in reviews} == {ReviewKind.TAGS}
    assert {r.used_technique for r in reviews} == {"graph_bfs", "brute_force"}
    assert all(r.review_json["verdict"]["bugs"] == [] for r in reviews)
    statuses = {s.status for s in await _submissions(sessionmaker, user)}
    assert statuses == {SubmissionStatus.REVIEWED}

    # The Review screen gets a verdict-shaped review with no tiers.
    sub_id = reviews[0].submission_id
    body = (await client.get(f"/api/submissions/{sub_id}")).json()
    assert body["review"]["kind"] == "tags"
    assert body["review"]["review_json"]["verdict"]["used_technique"] in {
        "graph_bfs",
        "brute_force",
    }


async def test_analysis_stops_after_repeated_failures(client, sessionmaker, redis):
    from app.providers.base import ProviderError

    _, job = await _imported(client, sessionmaker)
    await client.post(f"/api/imports/{job.id}/analysis", json={"mode": "tags_only"})
    bad = ProviderError("Invalid API key")
    adapter = ScriptedAdapter([bad, bad, bad])
    import app.imports.service as service

    service.MAX_CONSECUTIVE_FAILURES, old = 2, service.MAX_CONSECUTIVE_FAILURES
    try:
        await run_import_analysis(sessionmaker, redis, FakeQueue(), job.id, lambda *a: adapter)
    finally:
        service.MAX_CONSECUTIVE_FAILURES = old
    async with sessionmaker() as session:
        job = await session.get(ImportJob, job.id)
    assert job.analysis_status == ImportStatus.FAILED
    assert "Invalid API key" in job.analysis_error
    assert job.analysis_failed == 2


async def test_analysis_continues_in_slices_and_can_be_cancelled(client, sessionmaker, redis):
    _, job = await _imported(client, sessionmaker)
    await client.post(f"/api/imports/{job.id}/analysis", json={"mode": "tags_only"})

    next_queue = FakeQueue()
    adapter = ScriptedAdapter([_tags()])
    await run_import_analysis(
        sessionmaker, redis, next_queue, job.id, lambda *a: adapter, slice_s=0
    )
    assert [name for name, _ in next_queue.jobs] == ["analyze_import"]  # one done, more to go

    res = await client.post(f"/api/imports/{job.id}/analysis/cancel")
    assert res.json()["analysis_status"] == "cancelled"
    assert res.json()["pending"] == 1
    later = FakeQueue()
    await run_import_analysis(sessionmaker, redis, later, job.id, lambda *a: adapter)
    assert later.jobs == []

    # Resuming keeps the earlier count.
    res = await client.post(f"/api/imports/{job.id}/analysis", json={"mode": "tags_only"})
    assert (res.json()["analysis_total"], res.json()["analysis_done"]) == (2, 1)


# ---------------------------------------------------------------- API


async def test_start_import_queues_a_job(client, sessionmaker, queue):
    _login(client, await _make_user(sessionmaker, "alice"))
    res = await client.post("/api/imports", json={"repository": "not a repo"})
    assert res.status_code == 400

    res = await client.post(
        "/api/imports", json={"repository": "https://github.com/Asta-V22/LeetCode"}
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert (body["repository"], body["status"]) == ("Asta-V22/LeetCode", "pending")
    assert queue.jobs == [("import_repository", (body["id"],))]

    again = await client.post("/api/imports", json={"repository": "Asta-V22/LeetCode"})
    assert again.status_code == 409
    assert [j["id"] for j in (await client.get("/api/imports")).json()] == [body["id"]]


async def test_imports_are_private(client, sessionmaker):
    _, job = await _imported(client, sessionmaker)
    _login(client, await _make_user(sessionmaker, "bob"))
    assert (await client.get(f"/api/imports/{job.id}")).status_code == 404
    assert (await client.get("/api/imports")).json() == []


async def test_unmatched_folders_can_be_mapped_or_skipped(client, sessionmaker):
    user, job = await _imported(client, sessionmaker)
    res = await client.post(
        f"/api/imports/{job.id}/unmatched",
        json={"folder": "misc", "link": "https://leetcode.com/problems/sort-an-array/"},
    )
    assert res.status_code == 200, res.text
    assert (res.json()["unmatched"], res.json()["imported"], res.json()["pending"]) == ([], 3, 3)
    subs = await _submissions(sessionmaker, user)
    assert "class Sort {}" in {s.code for s in subs}

    missing = await client.post(f"/api/imports/{job.id}/unmatched", json={"folder": "misc"})
    assert missing.status_code == 404


async def test_imported_submissions_stay_off_todays_queue(client, sessionmaker):
    await _imported(client, sessionmaker)
    queue = (await client.get("/api/submissions", params={"in_queue": True})).json()
    assert queue["total"] == 0
    recent = (await client.get("/api/submissions", params={"exclude_source": "import"})).json()
    assert recent["total"] == 0
    assert (await client.get("/api/submissions")).json()["total"] == 2
