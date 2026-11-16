from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Fact(BaseModel):
    fact_id: str
    type: str
    description: str
    evidence_ids: list[str]


class Evidence(BaseModel):
    evidence_id: str
    file_id: str
    block_id: str | None = Field(default=None, min_length=1)
    page_no: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def has_source(self):
        if self.block_id is None and self.page_no is None:
            raise ValueError("证据须关联正文来源标识或历史页码")
        return self

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


class ScreeningConditionResult(ConditionResult):
    basis: Literal["evidence", "not_found", "uncertain"] = Field(
        description="evidence: 有原文依据；not_found: 已检查全文仍未匹配到；uncertain: 信息冲突或无法可靠核实"
    )


class HardConditionScreening(BaseModel):
    name: str | None = None
    hard_conditions: list[ScreeningConditionResult]
    evidence: list[Evidence]


class ScoringMatch(BaseModel):
    dimension_id: str
    matched: bool
    reason: str
    evidence_ids: list[str]


class ScoringEvidence(BaseModel):
    name: str | None = None
    matches: list[ScoringMatch]
    evidence: list[Evidence]
