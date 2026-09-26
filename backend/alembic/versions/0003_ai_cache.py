"""Add content-addressed AI response cache.

Revision ID: 0003_ai_cache
Revises: 0002_editor
Create Date: 2026-09-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_ai_cache"
down_revision = "0002_editor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ai_cache",
        sa.Column("cache_key", sa.String(length=64), primary_key=True),
        sa.Column("task", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("response_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_cache_task_created", "ai_cache", ["task", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_cache_task_created", table_name="ai_cache")
    op.drop_table("ai_cache")
