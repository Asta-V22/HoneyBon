"""The single review contract every provider must produce.

A review is generated in two parts so the verdict and tier 1 reach the user first:
`ReviewPartA` (verdict + tier 1) and `ReviewPartB` (tiers 2-4 + pattern). They merge into
`Review`. When the user's code is already optimal, tiers 2 and 3 are null and the review skips
straight to tier 4.
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
    optimal_time: Complexity = Field(description="Time complexity of the optimal solution.")
    optimal_space: Complexity = Field(description="Space complexity of the optimal solution.")
    is_optimal: bool = Field(
        description="True only if neither time nor space is worse than the optimal solution's."
    )

    @model_validator(mode="after")
    def _unique_optimal(self) -> "Verdict":
        if len(set(self.optimal_techniques)) != len(self.optimal_techniques):
            raise ValueError("optimal_techniques must not contain duplicates")
        return self

    @model_validator(mode="after")
    def _derive_is_optimal(self) -> "Verdict":
        # Derived from the complexity classes rather than trusted from the model, so every
        # provider applies the same rule: optimal means no worse in time AND no worse in space.
        self.is_optimal = (
            self.time.normalized.rank <= self.optimal_time.normalized.rank
            and self.space.normalized.rank <= self.optimal_space.normalized.rank
        )
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


class ReviewPartA(_Model):
    verdict: Verdict
    tier1: Tier1Improved


class ReviewPartB(_Model):
    tier2: Tier2SlightlyBetter | None = None
    tier3: Tier3Optimal | None = None
    tier4: Tier4CPMaster
    pattern: PatternFollowUp


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
