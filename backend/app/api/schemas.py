import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import CaptureMode, SubmissionSource, SubmissionStatus


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProviderKeyOut(_Out):
    provider: str
    last_four: str
    base_url: str | None


class MeOut(_Out):
    id: uuid.UUID
    github_login: str
    avatar_url: str | None
    default_provider: str | None
    default_model: str | None
    capture_mode: CaptureMode
    providers: list[ProviderKeyOut]
    available_providers: list[str]
    provider_models: dict[str, list[str]]


class MeUpdate(BaseModel):
    default_provider: str | None = None
    default_model: str | None = Field(default=None, max_length=100)
    capture_mode: CaptureMode | None = None


class ProviderKeyIn(BaseModel):
    api_key: str = Field(min_length=8, max_length=500)
    base_url: str | None = Field(default=None, max_length=500)


class PasteIn(BaseModel):
    code: str = Field(min_length=1, max_length=100_000)
    link: str | None = Field(default=None, max_length=500)
    statement: str | None = Field(default=None, max_length=50_000)
    platform: str | None = Field(default=None, max_length=32)
    title: str | None = Field(default=None, max_length=300)
    language: str | None = Field(default=None, max_length=32)
    provider: str | None = None
    model: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _link_or_statement(self) -> "PasteIn":
        if not (self.link and self.link.strip()) and not (
            self.statement and self.statement.strip()
        ):
            raise ValueError("Provide a problem link or a problem statement.")
        return self


class ReviewRequestIn(BaseModel):
    provider: str | None = None
    model: str | None = Field(default=None, max_length=100)


class ProblemOut(_Out):
    id: uuid.UUID
    platform: str
    slug: str
    title: str | None
    difficulty: str | None
    topic_tags: list[str]
    url: str | None


class ReviewOut(_Out):
    id: uuid.UUID
    provider: str
    model: str
    served_model: str | None
    review_json: dict[str, Any] | None
    error: str | None
    used_technique: str | None
    optimal_techniques: list[str]
    time_class: str | None
    space_class: str | None
    optimal_time_class: str | None
    optimal_space_class: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int | None
    cost_usd: Decimal | None
    repair_attempted: bool
    created_at: datetime
    completed_at: datetime | None


class ReviewSummaryOut(_Out):
    used_technique: str | None
    optimal_techniques: list[str]
    time_class: str | None
    space_class: str | None
    optimal_time_class: str | None
    optimal_space_class: str | None


class SubmissionListItem(_Out):
    id: uuid.UUID
    problem: ProblemOut
    language: str
    source: SubmissionSource
    status: SubmissionStatus
    created_at: datetime
    review: ReviewSummaryOut | None = None


class SubmissionOut(_Out):
    id: uuid.UUID
    problem: ProblemOut
    code: str
    statement: str | None
    language: str
    source: SubmissionSource
    status: SubmissionStatus
    created_at: datetime
    review: ReviewOut | None = None


class SubmissionPage(BaseModel):
    items: list[SubmissionListItem]
    total: int
