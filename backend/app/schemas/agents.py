from typing import Literal

from pydantic import BaseModel, Field


class Fact(BaseModel):
    fact_id: str
    type: str
    description: str
    evidence_ids: list[str]


class Evidence(BaseModel):
    evidence_id: str
    file_id: str
    page_no: int = Field(ge=1)
    quote: str = Field(min_length=1)


class Analysis(BaseModel):
    name: str | None = None
    facts: list[Fact]
    evidence: list[Evidence]
    missing_fields: list[str]


class ConditionResult(BaseModel):
    condition_id: str
    result: Literal["satisfied", "unsatisfied", "unknown"]
    reason: str
    evidence_ids: list[str]


class DimensionScore(BaseModel):
    dimension_id: str
    score: float = Field(ge=0, le=100, allow_inf_nan=False)
    reason: str
    evidence_ids: list[str]


class Evaluation(BaseModel):
    hard_conditions: list[ConditionResult]
    dimension_scores: list[DimensionScore]
    risks: list[str]
    missing_fields: list[str]


class Verification(BaseModel):
    review_notes: list[str]
    needs_human_review: bool
