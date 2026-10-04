"""The single review contract every provider must produce.

The verdict and tier 1 are always present. When the user's code is already optimal,
tiers 2 and 3 are omitted and the review skips straight to tier 4.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.reviews.taxonomy import ComplexityClass, Technique

SCHEMA_VERSION = 1


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Complexity(_Model):
    display: str = Field(min_length=1, description="As written for people, e.g. 'O(n log n)'.")
    normalized: ComplexityClass


class FailingInput(_Model):
    input: str = Field(min_length=1)
    outcome: Literal["wrong_answer", "time_limit", "runtime_error"]
    reason: str = Field(min_length=1)


class Verdict(_Model):
    correct: bool
    summary: str = Field(min_length=1)
    bugs: list[str] = Field(default_factory=list)
    missed_edge_cases: list[str] = Field(default_factory=list)
    failing_inputs: list[FailingInput] = Field(default_factory=list)
    time: Complexity
    space: Complexity
    used_technique: Technique
    optimal_techniques: list[Technique] = Field(
        min_length=1, description="Every technique that is equally optimal for this problem."
    )
    is_optimal: bool

    @model_validator(mode="after")
    def _unique_optimal(self) -> "Verdict":
        if len(set(self.optimal_techniques)) != len(self.optimal_techniques):
            raise ValueError("optimal_techniques must not contain duplicates")
        return self


class LineComment(_Model):
    line: int = Field(ge=1, description="1-based line in the improved code.")
    comment: str = Field(min_length=1)


class Tier1Improved(_Model):
    """Same approach, tightened. The UI renders it as a diff against the original."""

    summary: str = Field(min_length=1)
    code: str = Field(min_length=1)
    line_comments: list[LineComment] = Field(default_factory=list)


class Tier2SlightlyBetter(_Model):
    approach: str = Field(min_length=1)
    what_changes: str = Field(min_length=1)
    why_faster: str = Field(min_length=1)
    code: str = Field(min_length=1)
    time: Complexity
    space: Complexity


class Tier3Optimal(_Model):
    insight: str = Field(min_length=1, description="The core idea in plain words.")
    code: str = Field(min_length=1)
    time: Complexity
    space: Complexity


class Tier4CPMaster(_Model):
    notes: str = Field(min_length=1)
    code: str = Field(min_length=1)
    interview_caveat: str | None = Field(
        default=None, description="Set when the contest style would hurt in an interview."
    )


class RelatedProblem(_Model):
    title: str = Field(min_length=1)
    platform: str = "leetcode"
    slug: str | None = None


class PatternFollowUp(_Model):
    name: str = Field(min_length=1)
    related_problems: list[RelatedProblem] = Field(min_length=2, max_length=3)


class Review(_Model):
    schema_version: Literal[1] = SCHEMA_VERSION
    verdict: Verdict
    tier1: Tier1Improved
    tier2: Tier2SlightlyBetter | None = None
    tier3: Tier3Optimal | None = None
    tier4: Tier4CPMaster
    pattern: PatternFollowUp

    @model_validator(mode="after")
    def _optimal_skips_to_tier4(self) -> "Review":
        if self.verdict.is_optimal:
            if self.tier2 is not None or self.tier3 is not None:
                raise ValueError("an optimal solution must skip tiers 2 and 3")
        elif self.tier2 is None or self.tier3 is None:
            raise ValueError("tiers 2 and 3 are required unless the solution is optimal")
        return self
