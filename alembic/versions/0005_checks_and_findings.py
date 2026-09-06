"""Add structured rules, checks, snapshots, and findings.

Revision ID: 0005_checks_findings
Revises: 0004_documents
Create Date: 2026-09-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_checks_findings"
down_revision: Union[str, Sequence[str], None] = "0004_documents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "normatives",
        sa.Column(
            "rule_type",
            sa.String(length=50),
            nullable=False,
            server_default="manual_review",
        ),
    )
    op.add_column(
        "normatives",
        sa.Column("rule_config", sa.JSON(), nullable=True),
    )
    op.add_column(
        "normatives",
        sa.Column("recommendation", sa.Text(), nullable=True),
    )
    op.add_column(
        "normatives",
        sa.Column(
            "severity",
            sa.String(length=20),
            nullable=False,
            server_default="major",
        ),
    )
    op.add_column(
        "normatives",
        sa.Column(
            "is_demo",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "normatives",
        sa.Column(
            "expert_validated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_table(
        "checks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("stage_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("initiated_by_user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("verdict", sa.String(length=30), nullable=True),
        sa.Column("engine_code", sa.String(length=100), nullable=False),
        sa.Column("document_hash_snapshot", sa.String(length=64), nullable=False),
        sa.Column("pages_count", sa.Integer(), nullable=True),
        sa.Column("extracted_text_hash", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["initiated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stage_id"],
            ["stages.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_checks_document_id"), "checks", ["document_id"])
    op.create_index(op.f("ix_checks_id"), "checks", ["id"])
    op.create_index(
        op.f("ix_checks_initiated_by_user_id"),
        "checks",
        ["initiated_by_user_id"],
    )
    op.create_index(op.f("ix_checks_project_id"), "checks", ["project_id"])
    op.create_index(op.f("ix_checks_stage_id"), "checks", ["stage_id"])
    op.create_index(op.f("ix_checks_status"), "checks", ["status"])
    op.create_index(op.f("ix_checks_verdict"), "checks", ["verdict"])

    op.create_table(
        "check_normative_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("check_id", sa.Integer(), nullable=False),
        sa.Column("normative_id", sa.Integer(), nullable=True),
        sa.Column("family_key", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("document_code", sa.String(length=100), nullable=False),
        sa.Column("section", sa.String(length=100), nullable=True),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=500), nullable=True),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("rule_type", sa.String(length=50), nullable=False),
        sa.Column("rule_config", sa.JSON(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("is_demo", sa.Boolean(), nullable=False),
        sa.Column("expert_validated", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["check_id"],
            ["checks.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["normative_id"],
            ["normatives.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_check_normative_snapshots_check_id"),
        "check_normative_snapshots",
        ["check_id"],
    )
    op.create_index(
        op.f("ix_check_normative_snapshots_id"),
        "check_normative_snapshots",
        ["id"],
    )
    op.create_index(
        op.f("ix_check_normative_snapshots_normative_id"),
        "check_normative_snapshots",
        ["normative_id"],
    )

    op.create_table(
        "findings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("check_id", sa.Integer(), nullable=False),
        sa.Column("normative_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("evidence_text", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["check_id"],
            ["checks.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["normative_snapshot_id"],
            ["check_normative_snapshots.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["reviewed_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "check_id",
        "id",
        "kind",
        "normative_snapshot_id",
        "severity",
        "status",
    ):
        op.create_index(op.f(f"ix_findings_{column}"), "findings", [column])

    op.create_table(
        "finding_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("finding_id", sa.Integer(), nullable=False),
        sa.Column("old_status", sa.String(length=20), nullable=True),
        sa.Column("new_status", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["finding_id"],
            ["findings.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_finding_audit_logs_finding_id"),
        "finding_audit_logs",
        ["finding_id"],
    )
    op.create_index(
        op.f("ix_finding_audit_logs_id"),
        "finding_audit_logs",
        ["id"],
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_finding_audit_logs_id"), table_name="finding_audit_logs")
    op.drop_index(
        op.f("ix_finding_audit_logs_finding_id"),
        table_name="finding_audit_logs",
    )
    op.drop_table("finding_audit_logs")
    for column in (
        "status",
        "severity",
        "normative_snapshot_id",
        "kind",
        "id",
        "check_id",
    ):
        op.drop_index(op.f(f"ix_findings_{column}"), table_name="findings")
    op.drop_table("findings")
    op.drop_index(
        op.f("ix_check_normative_snapshots_normative_id"),
        table_name="check_normative_snapshots",
    )
    op.drop_index(
        op.f("ix_check_normative_snapshots_id"),
        table_name="check_normative_snapshots",
    )
    op.drop_index(
        op.f("ix_check_normative_snapshots_check_id"),
        table_name="check_normative_snapshots",
    )
    op.drop_table("check_normative_snapshots")
    op.drop_index(op.f("ix_checks_verdict"), table_name="checks")
    op.drop_index(op.f("ix_checks_status"), table_name="checks")
    op.drop_index(op.f("ix_checks_stage_id"), table_name="checks")
    op.drop_index(op.f("ix_checks_project_id"), table_name="checks")
    op.drop_index(
        op.f("ix_checks_initiated_by_user_id"),
        table_name="checks",
    )
    op.drop_index(op.f("ix_checks_id"), table_name="checks")
    op.drop_index(op.f("ix_checks_document_id"), table_name="checks")
    op.drop_table("checks")
    op.drop_column("normatives", "expert_validated")
    op.drop_column("normatives", "is_demo")
    op.drop_column("normatives", "severity")
    op.drop_column("normatives", "recommendation")
    op.drop_column("normatives", "rule_config")
    op.drop_column("normatives", "rule_type")
