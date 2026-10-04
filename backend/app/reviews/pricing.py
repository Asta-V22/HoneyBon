"""Estimated cost per call. Prices are USD per million tokens (input, output).

Unknown models return None rather than a guess; add rows as models are adopted.
"""

from decimal import Decimal

PRICES: dict[str, tuple[Decimal, Decimal]] = {
    # Anthropic first-party API, cached 2026-09-25.
    "claude-fable-5-1": (Decimal("10"), Decimal("50")),
    "claude-opus-5-5": (Decimal("4"), Decimal("20")),
    "claude-opus-5": (Decimal("5"), Decimal("25")),
    "claude-opus-4-8": (Decimal("5"), Decimal("25")),
    "claude-sonnet-5-5": (Decimal("2"), Decimal("10")),
    "claude-sonnet-5": (Decimal("2"), Decimal("10")),
    "claude-haiku-4-5": (Decimal("1"), Decimal("5")),
}

_MILLION = Decimal(1_000_000)


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> Decimal | None:
    price = PRICES.get(model)
    if price is None:
        return None
    return (price[0] * input_tokens + price[1] * output_tokens) / _MILLION
