from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import FindingSeverity, NormativeRuleType


NormativeStatus = Literal["active", "inactive"]


class NormativeStageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str


class NormativeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=255)
    document_code: str = Field(min_length=1, max_length=100)
    section: str | None = Field(default=None, max_length=100)
    requirement_text: str = Field(min_length=1)
    source: str | None = Field(default=None, max_length=500)
    version: str = Field(default="1.0", min_length=1, max_length=50)
    effective_date: date | None = None
    status: NormativeStatus = "active"
    stage_ids: list[int] = Field(min_length=1)
    rule_type: NormativeRuleType = NormativeRuleType.MANUAL_REVIEW
    rule_config: dict[str, Any] | None = None
    recommendation: str | None = None
    severity: FindingSeverity = FindingSeverity.MAJOR
    is_demo: bool = False
    expert_validated: bool = False


class NormativeUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: NormativeStatus | None = None
    stage_ids: list[int] | None = Field(default=None, min_length=1)


class NormativeVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    version: str = Field(min_length=1, max_length=50)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    document_code: str | None = Field(default=None, min_length=1, max_length=100)
    section: str | None = Field(default=None, max_length=100)
    requirement_text: str | None = Field(default=None, min_length=1)
    source: str | None = Field(default=None, max_length=500)
    effective_date: date | None = None
    stage_ids: list[int] | None = Field(default=None, min_length=1)
    rule_type: NormativeRuleType | None = None
    rule_config: dict[str, Any] | None = None
    recommendation: str | None = None
    severity: FindingSeverity | None = None
    is_demo: bool | None = None
    expert_validated: bool | None = None


class NormativeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    family_key: str
    supersedes_id: int | None = None
    title: str
    document_code: str
    section: str | None = None
    requirement_text: str
    source: str | None = None
    version: str
    effective_date: date | None = None
    status: NormativeStatus
    created_at: datetime
    updated_at: datetime
    stages: list[NormativeStageResponse]
    rule_type: NormativeRuleType
    rule_config: dict[str, Any] | None = None
    recommendation: str | None = None
    severity: FindingSeverity
    is_demo: bool
    expert_validated: bool
