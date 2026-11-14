from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class JobCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    responsibilities: str | None = None
    requirements: str | None = None
    draft_rules: dict[str, Any] | None = None


class JobPatch(BaseModel):
    draft_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    responsibilities: str | None = None
    requirements: str | None = None
    draft_rules: dict[str, Any] | None = None


class PublishRequest(BaseModel):
    draft_version: int = Field(ge=1)
    operator_name: str = Field(min_length=1, max_length=128)


class ReviewRequest(BaseModel):
    operation: Literal["supplement", "approve", "defer"]
    review_version: int = Field(ge=0)
    reason: str = Field(min_length=1)
    operator_name: str = Field(min_length=1, max_length=128)
    supplements: list[dict[str, str]] | None = None


class SlotInput(BaseModel):
    starts_at: datetime
    ends_at: datetime
    timezone: str = "Asia/Shanghai"
    interviewer: str | None = None

    @field_validator("starts_at", "ends_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("时间必须带时区偏移")
        return value


class PreviewInput(BaseModel):
    preview_version: int = Field(ge=0)
    recipient: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=10000)


class ActionApproval(BaseModel):
    preview_version: int = Field(ge=1)
    operator_name: str = Field(min_length=1, max_length=128)
