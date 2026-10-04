"""Live reviews against a real provider. These cost money, so they are opt-in:

    HB_LIVE_PROVIDER=gemini HB_LIVE_MODEL=gemini-3.8-flash HB_LIVE_API_KEY=... \\
        uv run pytest -m live -s
"""

import os

import pytest

from app.providers import DEFAULT_MODELS, get_adapter
from app.reviews.pipeline import CallStats, generate_review
from app.reviews.pricing import estimate_cost
from app.reviews.taxonomy import ComplexityClass, Technique
from tests.samples import LC678_TWO_STACKS

pytestmark = pytest.mark.live

PROVIDER = os.environ.get("HB_LIVE_PROVIDER", "anthropic")
MODEL = os.environ.get("HB_LIVE_MODEL") or DEFAULT_MODELS.get(PROVIDER, "")
API_KEY = os.environ.get("HB_LIVE_API_KEY", "")


@pytest.mark.skipif(not (API_KEY and MODEL), reason="set HB_LIVE_API_KEY (and HB_LIVE_MODEL)")
async def test_lc678_two_stack_solution():
    stats = CallStats()
    parts = []

    async def on_part_a(part):
        parts.append(part)

    adapter = get_adapter(PROVIDER, API_KEY)
    review = await generate_review(adapter, MODEL, LC678_TWO_STACKS, stats, on_part_a)
    v = review.verdict

    cost = estimate_cost(
        stats.served_model or MODEL, stats.usage.input_tokens, stats.usage.output_tokens
    )
    tier3 = review.tier3 and (review.tier3.time.display, review.tier3.space.display)
    print(
        f"\n{PROVIDER}/{stats.served_model}: correct={v.correct} optimal={v.is_optimal} "
        f"used={v.used_technique} optimal_set={[t.value for t in v.optimal_techniques]}\n"
        f"time={v.time.display} space={v.space.display} "
        f"optimal_time={v.optimal_time.display} optimal_space={v.optimal_space.display}\n"
        f"tier3={tier3}\n"
        f"pattern={review.pattern.name} "
        f"related={[p.title for p in review.pattern.related_problems]}\n"
        f"tokens={stats.usage.input_tokens}/{stats.usage.output_tokens} "
        f"latency={stats.latency_ms}ms repaired={stats.repair_attempted} cost={cost}\n"
        f"summary: {v.summary}"
    )

    # The pipeline itself: part A arrived first, everything validated.
    assert len(parts) == 1 and parts[0].verdict == v
    # Facts about this accepted solution that any sound review gets right.
    assert v.correct, "the submission was accepted on LeetCode"
    assert v.used_technique in {Technique.STACK, Technique.GREEDY}
    assert (v.time.normalized, v.space.normalized) == (ComplexityClass.N, ComplexityClass.N)
    # The greedy low/high scan is O(n) time and O(1) space, so two stacks are not optimal...
    assert v.optimal_time.normalized == ComplexityClass.N
    assert v.optimal_space.normalized == ComplexityClass.CONSTANT
    assert not v.is_optimal
    # ...and the review must teach the better solution.
    assert review.tier2 is not None and review.tier3 is not None
    assert review.tier3.space.normalized == ComplexityClass.CONSTANT
