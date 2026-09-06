from enum import StrEnum


class UserStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class ProjectRole(StrEnum):
    INVESTOR = "investor"
    PROJECT_MANAGER = "project_manager"
    INSPECTOR = "inspector"
    CONTRACTOR = "contractor"
    SERVICE_AGENT = "service_agent"


class TaskPriority(StrEnum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TaskStatus(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class DocumentStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"


TASK_STATUS_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.CREATED: {TaskStatus.ACTIVE, TaskStatus.CANCELLED},
    TaskStatus.ACTIVE: {
        TaskStatus.PENDING_VERIFICATION,
        TaskStatus.CANCELLED,
    },
    TaskStatus.PENDING_VERIFICATION: {
        TaskStatus.VERIFIED,
        TaskStatus.REJECTED,
    },
    TaskStatus.REJECTED: {TaskStatus.ACTIVE, TaskStatus.CANCELLED},
    TaskStatus.VERIFIED: set(),
    TaskStatus.CANCELLED: set(),
}


class CheckStatus(StrEnum):
    CREATED = "created"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class CheckVerdict(StrEnum):
    VALID = "valid"
    INVALID = "invalid"
    MANUAL_REVIEW = "manual_review"


class NormativeRuleType(StrEnum):
    REQUIRED_PHRASE = "required_phrase"
    FORBIDDEN_PHRASE = "forbidden_phrase"
    MANUAL_REVIEW = "manual_review"


class FindingKind(StrEnum):
    NON_COMPLIANCE = "non_compliance"
    MANUAL_REVIEW = "manual_review"


class FindingSeverity(StrEnum):
    INFO = "info"
    MINOR = "minor"
    MAJOR = "major"
    CRITICAL = "critical"


class FindingStatus(StrEnum):
    OPEN = "open"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    RESOLVED = "resolved"


FINDING_STATUS_TRANSITIONS: dict[FindingStatus, set[FindingStatus]] = {
    FindingStatus.OPEN: {
        FindingStatus.CONFIRMED,
        FindingStatus.DISMISSED,
    },
    FindingStatus.CONFIRMED: {
        FindingStatus.RESOLVED,
        FindingStatus.DISMISSED,
    },
    FindingStatus.DISMISSED: set(),
    FindingStatus.RESOLVED: set(),
}


class AcceptanceActStatus(StrEnum):
    DRAFT = "draft"
    READY = "ready"
    APPROVED = "approved"
    CANCELLED = "cancelled"


class AcceptanceActType(StrEnum):
    STAGE_ACCEPTANCE = "stage_acceptance"
    DEFECT = "defect"


ACCEPTANCE_ACT_STATUS_TRANSITIONS: dict[
    AcceptanceActStatus,
    set[AcceptanceActStatus],
] = {
    AcceptanceActStatus.DRAFT: {
        AcceptanceActStatus.READY,
        AcceptanceActStatus.CANCELLED,
    },
    AcceptanceActStatus.READY: {
        AcceptanceActStatus.DRAFT,
        AcceptanceActStatus.APPROVED,
        AcceptanceActStatus.CANCELLED,
    },
    AcceptanceActStatus.APPROVED: {AcceptanceActStatus.CANCELLED},
    AcceptanceActStatus.CANCELLED: set(),
}
