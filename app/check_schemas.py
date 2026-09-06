from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    CheckStatus,
    CheckVerdict,
    FindingKind,
    FindingSeverity,
    FindingStatus,
    NormativeRuleType,
)


class CheckCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: int = Field(gt=0)
    initiated_by_user_id: int | None = Field(default=None, gt=0)


class CheckNormativeSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    check_id: int
    normative_id: int | None = None
    family_key: str
    title: str
    document_code: str
    section: str | None = None
    requirement_text: str
    source: str | None = None
    version: str
    rule_type: NormativeRuleType
    rule_config: dict[str, Any] | None = None
    recommendation: str | None = None
    severity: FindingSeverity
    is_demo: bool
    expert_validated: bool
    created_at: datetime


class FindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    check_id: int
    normative_snapshot_id: int | None = None
    kind: FindingKind
    severity: FindingSeverity
    status: FindingStatus
    title: str
    description: str
    recommendation: str | None = None
    page_number: int | None = None
    evidence_text: str | None = None
    reviewed_by_user_id: int | None = None
    review_comment: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class FindingStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: FindingStatus
    changed_by_user_id: int | None = Field(default=None, gt=0)
    comment: str | None = Field(default=None, max_length=2000)


class FindingAuditLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    finding_id: int
    old_status: FindingStatus | None = None
    new_status: FindingStatus
    comment: str | None = None
    changed_by_user_id: int | None = None
    created_at: datetime


class CheckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    stage_id: int
    document_id: int
    initiated_by_user_id: int | None = None
    status: CheckStatus
    verdict: CheckVerdict | None = None
    engine_code: str
    document_hash_snapshot: str
    pages_count: int | None = None
    extracted_text_hash: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    normative_snapshots: list[CheckNormativeSnapshotResponse]
    findings: list[FindingResponse]


class CheckReportSummary(BaseModel):
    total_normatives: int
    total_findings: int
    non_compliance_findings: int
    manual_review_findings: int
    open_findings: int
    confirmed_findings: int
    dismissed_findings: int
    resolved_findings: int


class CheckReportResponse(BaseModel):
    check: CheckResponse
    summary: CheckReportSummary
    disclaimer: str
