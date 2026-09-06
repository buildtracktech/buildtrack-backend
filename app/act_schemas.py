from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import AcceptanceActStatus, AcceptanceActType, CheckVerdict


class AcceptanceActCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    check_id: int = Field(gt=0)
    act_type: AcceptanceActType
    act_number: str | None = Field(default=None, min_length=1, max_length=100)
    version: str = Field(default="1.0", min_length=1, max_length=50)
    work_description: str = Field(min_length=1)
    period_start: date | None = None
    period_end: date | None = None
    created_by_user_id: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_period(self):
        if (
            self.period_start is not None
            and self.period_end is not None
            and self.period_end < self.period_start
        ):
            raise ValueError("Дата окончания периода не может быть раньше даты начала")
        return self


class AcceptanceActStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: AcceptanceActStatus
    changed_by_user_id: int = Field(gt=0)
    comment: str | None = Field(default=None, max_length=2000)


class AcceptanceActResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    act_number: str
    version: str
    project_id: int
    stage_id: int
    check_id: int
    document_id: int
    act_type: AcceptanceActType
    status: AcceptanceActStatus
    work_description: str
    period_start: date | None = None
    period_end: date | None = None
    participant_snapshot: list[dict[str, Any]]
    finding_snapshot: list[dict[str, Any]]
    verification_verdict: CheckVerdict
    document_hash: str
    report_hash: str
    created_by_user_id: int | None = None
    approved_by_user_id: int | None = None
    approved_at: datetime | None = None
    cancellation_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class AcceptanceActAuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    act_id: int
    old_status: AcceptanceActStatus | None = None
    new_status: AcceptanceActStatus
    comment: str | None = None
    changed_by_user_id: int | None = None
    created_at: datetime
