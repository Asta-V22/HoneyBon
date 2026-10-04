import copy
import json
from pathlib import Path

import pytest

from app.reviews.taxonomy import ComplexityClass
from app.reviews.validation import validate_review

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def valid() -> dict:
    return json.loads((FIXTURES / "review_valid.json").read_text(encoding="utf-8"))


def test_valid_fixture_passes(valid):
    outcome = validate_review(valid)
    assert outcome.ok, outcome.error
    assert outcome.review.verdict.used_technique == "simulation"


def test_accepts_raw_json_text(valid):
    assert validate_review(json.dumps(valid)).ok


def test_optimal_review_skips_tiers_2_and_3(valid):
    data = copy.deepcopy(valid)
    data["verdict"]["is_optimal"] = True
    del data["tier2"], data["tier3"]
    assert validate_review(data).ok


def _break(valid: dict, mutate) -> dict:
    data = copy.deepcopy(valid)
    mutate(data)
    return data


MALFORMED = {
    "not_json": "{verdict: oops",
    "free_text_technique": lambda d: d["verdict"].update(used_technique="BFS-ish"),
    "unknown_complexity_class": lambda d: d["verdict"]["time"].update(normalized="m*n"),
    "duplicate_optimal": lambda d: d["verdict"].update(optimal_techniques=["graph_bfs"] * 2),
    "empty_optimal": lambda d: d["verdict"].update(optimal_techniques=[]),
    "missing_tier3_when_not_optimal": lambda d: d.pop("tier3"),
    "tiers_present_when_optimal": lambda d: d["verdict"].update(is_optimal=True),
    "too_many_related": lambda d: d["pattern"].update(
        related_problems=[{"title": f"P{i}"} for i in range(4)]
    ),
    "extra_field": lambda d: d.update(confidence=0.9),
    "zero_line_comment": lambda d: d["tier1"]["line_comments"][0].update(line=0),
}


@pytest.mark.parametrize("case", MALFORMED)
def test_malformed_output_is_rejected_with_an_error(valid, case):
    mutation = MALFORMED[case]
    raw = mutation if isinstance(mutation, str) else _break(valid, mutation)
    outcome = validate_review(raw)
    assert not outcome.ok
    assert outcome.error


def test_complexity_classes_rank_best_to_worst():
    assert ComplexityClass.N.rank < ComplexityClass.N_LOG_N.rank < ComplexityClass.N_SQUARED.rank
