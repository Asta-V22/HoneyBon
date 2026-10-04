import pytest

from app.reviews.pipeline import CallStats, ReviewFailed, generate_review
from app.reviews.prompts import ReviewInput
from app.reviews.provider_schema import provider_schema
from app.reviews.schema import ReviewPartA, ReviewPartB
from tests.fakes import ScriptedAdapter

INPUT = ReviewInput(
    platform="leetcode",
    problem_title="Rotting Oranges",
    problem_slug="rotting-oranges",
    problem_url=None,
    difficulty="Medium",
    statement=None,
    language="cpp",
    code="int main() {}",
)


async def _run(adapter, stats=None):
    seen = []

    async def on_part_a(part):
        seen.append(part)

    stats = stats or CallStats()
    review = await generate_review(adapter, "claude-opus-5-5", INPUT, stats, on_part_a)
    return review, seen, stats


async def test_two_calls_produce_a_full_review(part_a, part_b):
    adapter = ScriptedAdapter([part_a, part_b])
    review, seen, stats = await _run(adapter)
    assert review.tier3 is not None and review.pattern.name == "Multi-source BFS"
    assert len(seen) == 1 and seen[0].verdict.used_technique == "simulation"
    assert stats.usage.input_tokens == 200 and not stats.repair_attempted
    assert "<user_code" in adapter.requests[0].messages[0].content


async def test_malformed_response_gets_one_repair(part_a, part_b):
    adapter = ScriptedAdapter(["{not json", part_a, part_b])
    review, _, stats = await _run(adapter)
    assert stats.repair_attempted
    repair_turn = adapter.requests[1].messages
    assert [m.role for m in repair_turn] == ["user", "assistant", "user"]
    assert "did not match" in repair_turn[-1].content
    assert review.verdict.correct


async def test_second_failure_marks_review_failed(part_a):
    bad = {**part_a, "verdict": {**part_a["verdict"], "used_technique": "bfs-ish"}}
    with pytest.raises(ReviewFailed):
        await _run(ScriptedAdapter([bad, bad]))


async def test_optimal_solution_skips_to_tier4(part_a, part_b):
    part_a["verdict"]["time"]["normalized"] = "n"
    review, _, _ = await _run(ScriptedAdapter([part_a, part_b]))
    assert review.tier2 is None and review.tier3 is None and review.tier4


async def test_missing_tiers_on_suboptimal_solution_trigger_repair(part_a, part_b):
    incomplete = {**part_b, "tier3": None}
    review, _, stats = await _run(ScriptedAdapter([part_a, incomplete, part_b]))
    assert stats.repair_attempted and review.tier3 is not None


def _walk(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _assert_covers(schema: dict, value, path: str = "$") -> None:
    """Every key in a real review must be a property the provider is asked for."""
    if "anyOf" in schema:
        branches = [b for b in schema["anyOf"] if b.get("type") != "null"]
        schema = branches[0] if value is not None else {"type": "null"}
    if isinstance(value, dict):
        assert set(value) <= set(schema["properties"]), (
            f"{path}: {set(value) - set(schema['properties'])}"
        )
        assert set(schema["required"]) == set(schema["properties"])
        for key, sub in value.items():
            _assert_covers(schema["properties"][key], sub, f"{path}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _assert_covers(schema["items"], item, f"{path}[{i}]")


def test_provider_schema_asks_for_every_field(part_a, part_b):
    # Regression: the keyword stripper once removed the "pattern" field along with the
    # "pattern" regex keyword, so providers were never asked for it.
    _assert_covers(provider_schema(ReviewPartA), part_a)
    _assert_covers(provider_schema(ReviewPartB), part_b)
    assert set(provider_schema(ReviewPartB)["properties"]) == set(ReviewPartB.model_fields)


@pytest.mark.parametrize("model", [ReviewPartA, ReviewPartB])
def test_provider_schema_uses_only_supported_keywords(model):
    schema = provider_schema(model)
    for node in _walk(schema):
        assert "$ref" not in node and "minLength" not in node and "maxItems" not in node
        if node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
