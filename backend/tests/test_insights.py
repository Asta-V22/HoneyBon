from app.insights import ProblemRow, matrix, strongest_avoidance, tag_techniques
from app.models import Problem, Review, Submission
from app.models.enums import ReviewKind, SubmissionSource, SubmissionStatus
from tests.test_api import _login, _make_user


def _row(n=0, used="brute_force", optimal=("hashing",), time="n^2", best="n", tags=()):
    return ProblemRow(
        submission_id=str(n),
        title=f"p{n}",
        difficulty="Easy",
        platform="leetcode",
        used=used,
        optimal=list(optimal),
        time_class=time,
        space_class="1",
        optimal_time_class=best,
        optimal_space_class="1",
        topic_tags=list(tags),
    )


def test_any_equally_optimal_technique_is_a_match():
    bfs = _row(used="graph_bfs", optimal=("graph_dfs", "graph_bfs"), time="n", best="n")
    assert bfs.match and not bfs.worse and bfs.needed == "graph_bfs"


def test_mismatches_split_into_style_and_worse():
    style = _row(used="intervals_and_sorting", optimal=("hashing",), time="n", best="n")
    worse = _row(used="brute_force", optimal=("hashing",), time="n^2", best="n")
    assert (style.match, style.worse, style.needed) == (False, False, "hashing")
    assert (worse.match, worse.worse) == (False, True)
    # Worse space alone also counts.
    hungry = ProblemRow(**{**worse.__dict__, "time_class": "n", "space_class": "n"})
    assert hungry.worse


def test_tag_cross_check():
    assert tag_techniques(["array", "hash-table"]) == {"hashing"}
    assert _row(tags=("array", "matrix")).low_confidence is None  # nothing to check against
    assert _row(tags=("hash-table",)).low_confidence is False
    assert _row(tags=("dynamic-programming",)).low_confidence is True


def test_insight_card_needs_five_problems():
    rows = [_row(i) for i in range(4)] + [_row(9, used="hashing", time="n")]
    assert strongest_avoidance(rows, 5) is None

    rows.append(_row(4, used="intervals_and_sorting", time="n log n"))
    card = strongest_avoidance(rows, 5)
    assert card is not None
    assert (card.technique, card.avoided, card.worse, card.out_of) == ("hashing", 5, 5, 6)
    assert card.usual_instead == "brute_force"
    assert "9" not in card.submission_ids


def test_insight_card_ignores_low_confidence_problems():
    rows = [_row(i, tags=("dynamic-programming",)) for i in range(5)]
    assert strongest_avoidance(rows, 5) is None


def test_matrix_cells():
    rows = [
        _row(1),
        _row(2),
        _row(3, used="hashing", time="n"),
        _row(4, used="graph_bfs", optimal=("graph_bfs",), time="n"),
    ]
    needed, used, cells = matrix(rows)
    assert needed == ["hashing", "graph_bfs"]  # taxonomy order
    assert used == ["hashing", "graph_bfs", "brute_force"]
    by = {(c.needed, c.used): (c.count, c.worse) for c in cells}
    assert by == {
        ("hashing", "brute_force"): (2, 2),
        ("hashing", "hashing"): (1, 0),
        ("graph_bfs", "graph_bfs"): (1, 0),
    }


async def test_insights_endpoint(client, sessionmaker):
    user = await _make_user(sessionmaker, "alice")
    other = await _make_user(sessionmaker, "bob")
    async with sessionmaker() as session:
        for i, owner in enumerate([user] * 6 + [other]):
            problem = Problem(
                platform="leetcode",
                slug=f"p-{i}",
                title=f"P{i}",
                difficulty="Medium" if i else "Hard",
                topic_tags=["hash-table"],
            )
            session.add(problem)
            await session.flush()
            # The first problem's older, optimal attempt is superseded by the latest one.
            for used in ["hashing", "brute_force"] if i == 0 else ["brute_force"]:
                sub = Submission(
                    user_id=owner.id,
                    problem_id=problem.id,
                    code="x",
                    language="python",
                    source=SubmissionSource.IMPORT,
                    status=SubmissionStatus.REVIEWED,
                )
                session.add(sub)
                await session.flush()
                session.add(
                    Review(
                        submission_id=sub.id,
                        kind=ReviewKind.TAGS,
                        provider="groq",
                        model="m",
                        used_technique=used,
                        optimal_techniques=["hashing"],
                        time_class="n" if used == "hashing" else "n^2",
                        space_class="1",
                        optimal_time_class="n",
                        optimal_space_class="1",
                    )
                )
                await session.commit()

    _login(client, user)
    body = (await client.get("/api/insights")).json()
    assert body["problems"] == 6  # bob's problem is not counted
    assert (body["matched"], body["worse_mismatches"], body["style_mismatches"]) == (0, 6, 0)
    assert (body["checked"], body["disagreements"]) == (6, 0)
    assert body["card"]["technique"] == "hashing"
    assert body["card"]["avoided"] == 6
    assert body["cells"] == [{"needed": "hashing", "used": "brute_force", "count": 6, "worse": 6}]

    hard = (await client.get("/api/insights", params={"difficulty": "Hard"})).json()
    assert hard["problems"] == 1 and hard["card"] is None
