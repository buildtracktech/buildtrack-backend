from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.time import utc_now
from app.database import Base


normative_stages = Table(
    "normative_stages",
    Base.metadata,
    Column(
        "normative_id",
        ForeignKey("normatives.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "stage_id",
        ForeignKey("stages.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    location = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    stages = relationship("Stage", back_populates="project", cascade="all, delete-orphan")
    scans = relationship("Scan", back_populates="project", cascade="all, delete-orphan")
    memberships = relationship(
        "ProjectMembership",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    tasks = relationship("Task", back_populates="project", cascade="all, delete-orphan")
    documents = relationship(
        "Document",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    checks = relationship("Check", back_populates="project", cascade="all, delete-orphan")
    acceptance_acts = relationship(
        "AcceptanceAct",
        back_populates="project",
        cascade="all, delete-orphan",
    )


class Stage(Base):
    __tablename__ = "stages"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime(timezone=True), default=utc_now)

    project = relationship("Project", back_populates="stages")
    scans = relationship("Scan", back_populates="stage", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="stage", cascade="all, delete-orphan")
    normatives = relationship(
        "Normative",
        secondary=normative_stages,
        back_populates="stages",
    )
    documents = relationship(
        "Document",
        back_populates="stage",
        cascade="all, delete-orphan",
    )
    checks = relationship("Check", back_populates="stage", cascade="all, delete-orphan")
    acceptance_acts = relationship(
        "AcceptanceAct",
        back_populates="stage",
        cascade="all, delete-orphan",
    )


class Scan(Base):
    __tablename__ = "scans"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    stage_id = Column(Integer, ForeignKey("stages.id"), nullable=False)

    original_filename = Column(String(255), nullable=False)
    stored_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_hash = Column(String(128), nullable=False)

    status = Column(String(50), default="pending")
    comment = Column(Text, nullable=True)
    checked_by = Column(String(255), nullable=True)
    checked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    project = relationship("Project", back_populates="scans")
    stage = relationship("Stage", back_populates="scans")
    audit_logs = relationship("ScanAuditLog", back_populates="scan", cascade="all, delete-orphan")


class ScanAuditLog(Base):
    __tablename__ = "scan_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    scan_id = Column(Integer, ForeignKey("scans.id"), nullable=False)

    old_status = Column(String(50), nullable=True)
    new_status = Column(String(50), nullable=False)
    comment = Column(Text, nullable=True)
    changed_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    scan = relationship("Scan", back_populates="audit_logs")


class Normative(Base):
    __tablename__ = "normatives"
    __table_args__ = (
        UniqueConstraint(
            "family_key",
            "version",
            name="uq_normatives_family_key_version",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    family_key = Column(String(64), nullable=False, index=True)
    supersedes_id = Column(
        Integer,
        ForeignKey("normatives.id", ondelete="SET NULL"),
        nullable=True,
    )
    title = Column(String(255), nullable=False)
    document_code = Column(String(100), nullable=False)
    section = Column(String(100), nullable=True)
    requirement_text = Column(Text, nullable=False)
    source = Column(String(500), nullable=True)
    version = Column(String(50), nullable=False)
    effective_date = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    stages = relationship(
        "Stage",
        secondary=normative_stages,
        back_populates="normatives",
    )
    supersedes = relationship("Normative", remote_side=[id], foreign_keys=[supersedes_id])
    rule_type = Column(
        String(50),
        nullable=False,
        default="manual_review",
    )
    rule_config = Column(JSON, nullable=True)
    recommendation = Column(Text, nullable=True)
    severity = Column(String(20), nullable=False, default="major")
    is_demo = Column(Boolean, nullable=False, default=False)
    expert_validated = Column(Boolean, nullable=False, default=False)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    full_name = Column(String(255), nullable=False)
    status = Column(String(20), nullable=False, default="active", index=True)
    is_system_admin = Column(Boolean, nullable=False, default=False)
    password_hash = Column(String(255), nullable=True)
    token_version = Column(Integer, nullable=False, default=0)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    memberships = relationship(
        "ProjectMembership",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    assigned_tasks = relationship(
        "Task",
        back_populates="assigned_to",
        foreign_keys="Task.assigned_to_user_id",
    )
    created_tasks = relationship(
        "Task",
        back_populates="created_by",
        foreign_keys="Task.created_by_user_id",
    )
    uploaded_documents = relationship(
        "Document",
        back_populates="uploaded_by",
        foreign_keys="Document.uploaded_by_user_id",
    )
    initiated_checks = relationship(
        "Check",
        back_populates="initiated_by",
        foreign_keys="Check.initiated_by_user_id",
    )
    reviewed_findings = relationship(
        "Finding",
        back_populates="reviewed_by",
        foreign_keys="Finding.reviewed_by_user_id",
    )
    finding_audit_entries = relationship(
        "FindingAuditLog",
        back_populates="changed_by",
        foreign_keys="FindingAuditLog.changed_by_user_id",
    )
    created_acceptance_acts = relationship(
        "AcceptanceAct",
        back_populates="created_by",
        foreign_keys="AcceptanceAct.created_by_user_id",
    )
    approved_acceptance_acts = relationship(
        "AcceptanceAct",
        back_populates="approved_by",
        foreign_keys="AcceptanceAct.approved_by_user_id",
    )
    acceptance_act_audit_entries = relationship(
        "AcceptanceActAuditLog",
        back_populates="changed_by",
        foreign_keys="AcceptanceActAuditLog.changed_by_user_id",
    )

    @property
    def has_password(self) -> bool:
        return self.password_hash is not None


class ProjectMembership(Base):
    __tablename__ = "project_memberships"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "user_id",
            "role",
            name="uq_project_memberships_project_user_role",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role = Column(String(50), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    project = relationship("Project", back_populates="memberships")
    user = relationship("User", back_populates="memberships")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_id = Column(
        Integer,
        ForeignKey("stages.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    assigned_to_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(30), nullable=False, default="created", index=True)
    priority = Column(String(20), nullable=False, default="normal", index=True)
    due_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    project = relationship("Project", back_populates="tasks")
    stage = relationship("Stage", back_populates="tasks")
    assigned_to = relationship(
        "User",
        back_populates="assigned_tasks",
        foreign_keys=[assigned_to_user_id],
    )
    created_by = relationship(
        "User",
        back_populates="created_tasks",
        foreign_keys=[created_by_user_id],
    )
    audit_logs = relationship(
        "TaskAuditLog",
        back_populates="task",
        cascade="all, delete-orphan",
    )


class TaskAuditLog(Base):
    __tablename__ = "task_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(
        Integer,
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    old_status = Column(String(30), nullable=True)
    new_status = Column(String(30), nullable=False)
    comment = Column(Text, nullable=True)
    changed_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    task = relationship("Task", back_populates="audit_logs")
    changed_by = relationship("User", foreign_keys=[changed_by_user_id])


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint(
            "series_key",
            "version",
            name="uq_documents_series_key_version",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    series_key = Column(String(64), nullable=False, index=True)
    supersedes_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_id = Column(
        Integer,
        ForeignKey("stages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    uploaded_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    title = Column(String(255), nullable=False)
    document_type = Column(
        String(100),
        nullable=False,
        default="project_documentation",
    )
    version = Column(String(50), nullable=False)
    original_filename = Column(String(255), nullable=False)
    storage_key = Column(String(500), nullable=False, unique=True)
    mime_type = Column(String(100), nullable=False, default="application/pdf")
    size_bytes = Column(Integer, nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    project = relationship("Project", back_populates="documents")
    stage = relationship("Stage", back_populates="documents")
    uploaded_by = relationship(
        "User",
        back_populates="uploaded_documents",
        foreign_keys=[uploaded_by_user_id],
    )
    supersedes = relationship(
        "Document",
        remote_side=[id],
        foreign_keys=[supersedes_id],
    )
    checks = relationship("Check", back_populates="document", cascade="all, delete-orphan")
    acceptance_acts = relationship(
        "AcceptanceAct",
        back_populates="document",
    )


class Check(Base):
    __tablename__ = "checks"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_id = Column(
        Integer,
        ForeignKey("stages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    initiated_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status = Column(String(20), nullable=False, default="created", index=True)
    verdict = Column(String(30), nullable=True, index=True)
    engine_code = Column(String(100), nullable=False)
    document_hash_snapshot = Column(String(64), nullable=False)
    pages_count = Column(Integer, nullable=True)
    extracted_text_hash = Column(String(64), nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    project = relationship("Project", back_populates="checks")
    stage = relationship("Stage", back_populates="checks")
    document = relationship("Document", back_populates="checks")
    initiated_by = relationship(
        "User",
        back_populates="initiated_checks",
        foreign_keys=[initiated_by_user_id],
    )
    normative_snapshots = relationship(
        "CheckNormativeSnapshot",
        back_populates="check",
        cascade="all, delete-orphan",
        order_by="CheckNormativeSnapshot.id",
    )
    findings = relationship(
        "Finding",
        back_populates="check",
        cascade="all, delete-orphan",
        order_by="Finding.id",
    )
    acceptance_acts = relationship("AcceptanceAct", back_populates="check")


class CheckNormativeSnapshot(Base):
    __tablename__ = "check_normative_snapshots"

    id = Column(Integer, primary_key=True, index=True)
    check_id = Column(
        Integer,
        ForeignKey("checks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    normative_id = Column(
        Integer,
        ForeignKey("normatives.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    family_key = Column(String(64), nullable=False)
    title = Column(String(255), nullable=False)
    document_code = Column(String(100), nullable=False)
    section = Column(String(100), nullable=True)
    requirement_text = Column(Text, nullable=False)
    source = Column(String(500), nullable=True)
    version = Column(String(50), nullable=False)
    rule_type = Column(String(50), nullable=False)
    rule_config = Column(JSON, nullable=True)
    recommendation = Column(Text, nullable=True)
    severity = Column(String(20), nullable=False)
    is_demo = Column(Boolean, nullable=False)
    expert_validated = Column(Boolean, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    check = relationship("Check", back_populates="normative_snapshots")
    normative = relationship("Normative")
    findings = relationship("Finding", back_populates="normative_snapshot")


class Finding(Base):
    __tablename__ = "findings"

    id = Column(Integer, primary_key=True, index=True)
    check_id = Column(
        Integer,
        ForeignKey("checks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    normative_snapshot_id = Column(
        Integer,
        ForeignKey("check_normative_snapshots.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    kind = Column(String(30), nullable=False, index=True)
    severity = Column(String(20), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="open", index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=True)
    page_number = Column(Integer, nullable=True)
    evidence_text = Column(Text, nullable=True)
    reviewed_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    review_comment = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    check = relationship("Check", back_populates="findings")
    normative_snapshot = relationship(
        "CheckNormativeSnapshot",
        back_populates="findings",
    )
    reviewed_by = relationship(
        "User",
        back_populates="reviewed_findings",
        foreign_keys=[reviewed_by_user_id],
    )
    audit_logs = relationship(
        "FindingAuditLog",
        back_populates="finding",
        cascade="all, delete-orphan",
        order_by="FindingAuditLog.id",
    )


class FindingAuditLog(Base):
    __tablename__ = "finding_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    finding_id = Column(
        Integer,
        ForeignKey("findings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    old_status = Column(String(20), nullable=True)
    new_status = Column(String(20), nullable=False)
    comment = Column(Text, nullable=True)
    changed_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    finding = relationship("Finding", back_populates="audit_logs")
    changed_by = relationship(
        "User",
        back_populates="finding_audit_entries",
        foreign_keys=[changed_by_user_id],
    )


class AcceptanceAct(Base):
    __tablename__ = "acceptance_acts"
    __table_args__ = (
        UniqueConstraint(
            "act_number",
            "version",
            name="uq_acceptance_acts_number_version",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    act_number = Column(String(100), nullable=False, index=True)
    version = Column(String(50), nullable=False, default="1.0")
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_id = Column(
        Integer,
        ForeignKey("stages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    check_id = Column(
        Integer,
        ForeignKey("checks.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    document_id = Column(
        Integer,
        ForeignKey("documents.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    act_type = Column(String(30), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="draft", index=True)
    work_description = Column(Text, nullable=False)
    period_start = Column(Date, nullable=True)
    period_end = Column(Date, nullable=True)
    participant_snapshot = Column(JSON, nullable=False)
    finding_snapshot = Column(JSON, nullable=False)
    verification_verdict = Column(String(30), nullable=False)
    document_hash = Column(String(64), nullable=False)
    report_hash = Column(String(64), nullable=False)
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    project = relationship("Project", back_populates="acceptance_acts")
    stage = relationship("Stage", back_populates="acceptance_acts")
    check = relationship("Check", back_populates="acceptance_acts")
    document = relationship("Document", back_populates="acceptance_acts")
    created_by = relationship(
        "User",
        back_populates="created_acceptance_acts",
        foreign_keys=[created_by_user_id],
    )
    approved_by = relationship(
        "User",
        back_populates="approved_acceptance_acts",
        foreign_keys=[approved_by_user_id],
    )
    audit_logs = relationship(
        "AcceptanceActAuditLog",
        back_populates="act",
        cascade="all, delete-orphan",
        order_by="AcceptanceActAuditLog.id",
    )


class AcceptanceActAuditLog(Base):
    __tablename__ = "acceptance_act_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    act_id = Column(
        Integer,
        ForeignKey("acceptance_acts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    old_status = Column(String(20), nullable=True)
    new_status = Column(String(20), nullable=False)
    comment = Column(Text, nullable=True)
    changed_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=utc_now)

    act = relationship("AcceptanceAct", back_populates="audit_logs")
    changed_by = relationship(
        "User",
        back_populates="acceptance_act_audit_entries",
        foreign_keys=[changed_by_user_id],
    )
