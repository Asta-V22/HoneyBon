"""Generate a validated review in two calls: verdict + tier 1 first, then tiers 2-4.

Each call gets one repair retry: the validation error is sent back to the model with its own
response. A second failure ends the review as failed.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from pydantic import BaseModel

from app.providers.base import Message, ProviderAdapter, StructuredRequest, Usage
from app.reviews.prompts import (
    SYSTEM_PROMPT,
    ReviewInput,
    part_a_prompt,
    part_b_prompt,
    repair_prompt,
)
from app.reviews.provider_schema import provider_schema
from app.reviews.schema import Review, ReviewPartA, ReviewPartB
from app.reviews.validation import validate_as


@dataclass
class CallStats:
    usage: Usage = field(default_factory=Usage)
    latency_ms: int = 0
    served_model: str | None = None
    repair_attempted: bool = False


class ReviewFailed(Exception):
    pass


async def _call_validated[M: BaseModel](
    adapter: ProviderAdapter,
    model: str,
    schema: type[M],
    prompt: str,
    stats: CallStats,
    extra_check: Callable[[M], str | None] | None = None,
) -> M:
    messages = [Message("user", prompt)]
    json_schema = provider_schema(schema)
    error = "no response"
    for attempt in range(2):
        result = await adapter.review(
            StructuredRequest(model, SYSTEM_PROMPT, messages, json_schema)
        )
        stats.usage += result.usage
        stats.latency_ms += result.latency_ms
        stats.served_model = result.model

        outcome = validate_as(schema, result.raw)
        error = outcome.error or (extra_check(outcome.value) if extra_check else None)
        if error is None:
            return outcome.value
        if attempt == 0:
            stats.repair_attempted = True
            messages = [
                *messages,
                Message("assistant", result.raw or "(empty response)"),
                Message("user", repair_prompt(error)),
            ]
    raise ReviewFailed(f"The model's response failed validation after a repair retry: {error}")


async def generate_review(
    adapter: ProviderAdapter,
    model: str,
    inp: ReviewInput,
    stats: CallStats,
    on_part_a: Callable[[ReviewPartA], Awaitable[None]],
) -> Review:
    part_a = await _call_validated(adapter, model, ReviewPartA, part_a_prompt(inp), stats)
    await on_part_a(part_a)

    optimal = part_a.verdict.is_optimal

    def check_b(part: ReviewPartB) -> str | None:
        if not optimal and (part.tier2 is None or part.tier3 is None):
            return "tier2 and tier3 are required because the solution is not optimal."
        return None

    part_b = await _call_validated(
        adapter,
        model,
        ReviewPartB,
        part_b_prompt(inp, part_a.verdict.model_dump_json()),
        stats,
        extra_check=check_b,
    )
    if optimal:
        # An optimal solution skips straight to tier 4, whatever the model sent.
        part_b = part_b.model_copy(update={"tier2": None, "tier3": None})
    return Review(verdict=part_a.verdict, tier1=part_a.tier1, **part_b.model_dump(mode="json"))
