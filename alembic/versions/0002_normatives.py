"""Add versioned normatives and stage associations.

Revision ID: 0002_normatives
Revises: 0001_existing_core
Create Date: 2026-09-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_normatives"
down_revision: Union[str, Sequence[str], None] = "0001_existing_core"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "normatives",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("family_key", sa.String(length=64), nullable=False),
        sa.Column("supersedes_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("document_code", sa.String(length=100), nullable=False),
        sa.Column("section", sa.String(length=100), nullable=True),
        sa.Column("requirement_text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=500), nullable=True),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["normatives.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "family_key",
            "version",
            name="uq_normatives_family_key_version",
        ),
    )
    op.create_index(
        op.f("ix_normatives_family_key"),
        "normatives",
        ["family_key"],
        unique=False,
    )
    op.create_index(op.f("ix_normatives_id"), "normatives", ["id"], unique=False)
    op.create_index(
        op.f("ix_normatives_status"),
        "normatives",
        ["status"],
        unique=False,
    )

    op.create_table(
        "normative_stages",
        sa.Column("normative_id", sa.Integer(), nullable=False),
        sa.Column("stage_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["normative_id"],
            ["normatives.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["stage_id"],
            ["stages.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("normative_id", "stage_id"),
    )


def downgrade() -> None:
    op.drop_table("normative_stages")
    op.drop_index(op.f("ix_normatives_status"), table_name="normatives")
    op.drop_index(op.f("ix_normatives_id"), table_name="normatives")
    op.drop_index(op.f("ix_normatives_family_key"), table_name="normatives")
    op.drop_table("normatives")
