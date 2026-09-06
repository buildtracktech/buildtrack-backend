"""Add technical acceptance acts and audit history.

Revision ID: 0006_acceptance_acts
Revises: 0005_checks_findings
Create Date: 2026-09-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_acceptance_acts"
down_revision: Union[str, Sequence[str], None] = "0005_checks_findings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "acceptance_acts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("act_number", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("stage_id", sa.Integer(), nullable=False),
        sa.Column("check_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("act_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("work_description", sa.Text(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("participant_snapshot", sa.JSON(), nullable=False),
        sa.Column("finding_snapshot", sa.JSON(), nullable=False),
        sa.Column("verification_verdict", sa.String(length=30), nullable=False),
        sa.Column("document_hash", sa.String(length=64), nullable=False),
        sa.Column("report_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_by_user_id", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["approved_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["check_id"],
            ["checks.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            ondelete="RESTRICT",
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
        sa.UniqueConstraint(
            "act_number",
            "version",
            name="uq_acceptance_acts_number_version",
        ),
    )
    for column in (
        "act_number",
        "act_type",
        "check_id",
        "document_id",
        "id",
        "project_id",
        "stage_id",
        "status",
    ):
        op.create_index(
            op.f(f"ix_acceptance_acts_{column}"),
            "acceptance_acts",
            [column],
        )

    op.create_table(
        "acceptance_act_audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("act_id", sa.Integer(), nullable=False),
        sa.Column("old_status", sa.String(length=20), nullable=True),
        sa.Column("new_status", sa.String(length=20), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("changed_by_user_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["act_id"],
            ["acceptance_acts.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["changed_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_acceptance_act_audit_logs_act_id"),
        "acceptance_act_audit_logs",
        ["act_id"],
    )
    op.create_index(
        op.f("ix_acceptance_act_audit_logs_id"),
        "acceptance_act_audit_logs",
        ["id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_acceptance_act_audit_logs_id"),
        table_name="acceptance_act_audit_logs",
    )
    op.drop_index(
        op.f("ix_acceptance_act_audit_logs_act_id"),
        table_name="acceptance_act_audit_logs",
    )
    op.drop_table("acceptance_act_audit_logs")
    for column in (
        "status",
        "stage_id",
        "project_id",
        "id",
        "document_id",
        "check_id",
        "act_type",
        "act_number",
    ):
        op.drop_index(
            op.f(f"ix_acceptance_acts_{column}"),
            table_name="acceptance_acts",
        )
    op.drop_table("acceptance_acts")
