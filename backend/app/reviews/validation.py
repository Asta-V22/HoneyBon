"""Validate raw provider output against the review contract."""

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.reviews.schema import Review


@dataclass(frozen=True)
class ValidationOutcome[M: BaseModel]:
    value: M | None
    error: str | None

    @property
    def ok(self) -> bool:
        return self.value is not None

    @property
    def review(self) -> M | None:
        return self.value


def validate_as[M: BaseModel](model: type[M], raw: str | dict[str, Any]) -> ValidationOutcome[M]:
    """Parse and validate. The error text is what goes back to the model on the repair retry."""
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError as exc:
        return ValidationOutcome(None, f"Response is not valid JSON: {exc}")
    try:
        return ValidationOutcome(model.model_validate(data), None)
    except ValidationError as exc:
        return ValidationOutcome(None, str(exc))


def validate_review(raw: str | dict[str, Any]) -> ValidationOutcome[Review]:
    return validate_as(Review, raw)
