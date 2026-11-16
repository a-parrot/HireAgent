from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class JobCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    responsibilities: str | None = None
    requirements: str | None = None
    draft_rules: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, value):
        if not value.strip():
            raise ValueError("岗位名称不能为空")
        return value.strip()


class JobPatch(BaseModel):
    draft_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    responsibilities: str | None = None
    requirements: str | None = None
    draft_rules: dict[str, Any] | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, value):
        if value is not None and not value.strip():
            raise ValueError("岗位名称不能为空")
        return value.strip() if value is not None else None


class PublishRequest(BaseModel):
    draft_version: int = Field(ge=1)
    operator_name: str = Field(min_length=1, max_length=128)


class ReviewRequest(BaseModel):
    operation: Literal["supplement", "approve", "defer"]
    review_version: int = Field(ge=0)
    reason: str = ""
    operator_name: str = Field(min_length=1, max_length=128)
    supplements: list[dict[str, str]] | None = None

    @model_validator(mode="after")
    def validate_reason(self):
        self.reason = self.reason.strip()
        if self.operation != "approve" and not self.reason:
            raise ValueError("请填写审核理由")
        return self


class SlotInput(BaseModel):
    starts_at: datetime
    ends_at: datetime
    timezone: str = "Asia/Shanghai"
    interviewer: str | None = Field(default=None, max_length=200)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("时间必须带时区偏移")
        return value


class InterviewBooking(SlotInput):
    candidate_ids: list[int] = Field(min_length=1, max_length=100)
    gap_minutes: int = Field(default=0, ge=0, le=240)


class InterviewReschedule(SlotInput):
    preview_version: int = Field(ge=0)


class PreviewInput(BaseModel):
    preview_version: int = Field(ge=0)
    recipient: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=10000)


class ActionApproval(BaseModel):
    preview_version: int = Field(ge=1)
    operator_name: str = Field(min_length=1, max_length=128)
