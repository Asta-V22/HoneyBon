"""Validate raw provider output against the review contract."""

import json
from dataclasses import dataclass

from pydantic import ValidationError

from app.reviews.schema import Review


@dataclass(frozen=True)
class ValidationOutcome:
    review: Review | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.review is not None


def validate_review(raw: str | dict) -> ValidationOutcome:
    """Parse and validate. The error text is what goes back to the model on the repair retry."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as exc:
        return ValidationOutcome(None, f"Response is not valid JSON: {exc}")
    try:
        return ValidationOutcome(Review.model_validate(data), None)
    except ValidationError as exc:
        return ValidationOutcome(None, str(exc))
