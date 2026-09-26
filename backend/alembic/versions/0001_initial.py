"""Create project, asset, durable job, and event tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("product_name", sa.String(length=200), nullable=True),
        sa.Column("affiliate_url", sa.String(length=2048), nullable=True),
        sa.Column("source_url", sa.String(length=2048), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_projects_created_at", "projects", ["created_at"])

    op.create_table(
        "assets",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("relative_path", sa.String(length=1024), nullable=False, unique=True),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("has_audio", sa.Boolean(), nullable=True),
        sa.Column("video_codec", sa.String(length=80), nullable=True),
        sa.Column("container_format", sa.String(length=120), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_assets_project_id", "assets", ["project_id"])
    op.create_index("ix_assets_created_at", "assets", ["created_at"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", sa.String(length=36), sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=True),
        sa.Column("job_type", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_jobs_state_created_at", "jobs", ["state", "created_at"])
    op.create_index("ix_jobs_project_id", "jobs", ["project_id"])

    op.create_table(
        "job_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("job_id", sa.String(length=36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_job_events_job_id_created_at", "job_events", ["job_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_job_events_job_id_created_at", table_name="job_events")
    op.drop_table("job_events")
    op.drop_index("ix_jobs_project_id", table_name="jobs")
    op.drop_index("ix_jobs_state_created_at", table_name="jobs")
    op.drop_table("jobs")
    op.drop_index("ix_assets_created_at", table_name="assets")
    op.drop_index("ix_assets_project_id", table_name="assets")
    op.drop_table("assets")
    op.drop_index("ix_projects_created_at", table_name="projects")
    op.drop_table("projects")
