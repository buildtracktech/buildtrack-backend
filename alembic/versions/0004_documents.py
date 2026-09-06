"""Add versioned project documents.

Revision ID: 0004_documents
Revises: 0003_users_and_tasks
Create Date: 2026-09-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_documents"
down_revision: Union[str, Sequence[str], None] = "0003_users_and_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_key", sa.String(length=64), nullable=False),
        sa.Column("supersedes_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("stage_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=100), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("file_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["documents.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "series_key",
            "version",
            name="uq_documents_series_key_version",
        ),
        sa.UniqueConstraint("storage_key"),
    )
    op.create_index(op.f("ix_documents_file_hash"), "documents", ["file_hash"])
    op.create_index(op.f("ix_documents_id"), "documents", ["id"])
    op.create_index(op.f("ix_documents_project_id"), "documents", ["project_id"])
    op.create_index(op.f("ix_documents_series_key"), "documents", ["series_key"])
    op.create_index(op.f("ix_documents_stage_id"), "documents", ["stage_id"])
    op.create_index(op.f("ix_documents_status"), "documents", ["status"])
    op.create_index(
        op.f("ix_documents_uploaded_by_user_id"),
        "documents",
        ["uploaded_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_documents_uploaded_by_user_id"),
        table_name="documents",
    )
    op.drop_index(op.f("ix_documents_status"), table_name="documents")
    op.drop_index(op.f("ix_documents_stage_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_series_key"), table_name="documents")
    op.drop_index(op.f("ix_documents_project_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_file_hash"), table_name="documents")
    op.drop_table("documents")
