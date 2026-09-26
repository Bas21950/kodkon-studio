"""Add editable revisions, subtitles, masks, generated copy, and render history.

Revision ID: 0002_editor
Revises: 0001_initial
Create Date: 2026-09-22
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "0002_editor"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "revisions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source_asset_id", sa.String(length=36), sa.ForeignKey("assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("state", sa.String(length=24), nullable=False, server_default="draft"),
        sa.Column("settings_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "version", name="uq_revisions_project_version"),
    )
    op.create_index("ix_revisions_project_id", "revisions", ["project_id"])

    projects = sa.table("projects", sa.column("id", sa.String()))
    revisions = sa.table(
        "revisions",
        sa.column("id", sa.String()),
        sa.column("project_id", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("state", sa.String()),
        sa.column("settings_json", sa.Text()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    now = datetime.now(timezone.utc)
    bind = op.get_bind()
    for row in bind.execute(sa.select(projects.c.id)):
        bind.execute(
            revisions.insert().values(
                id=str(uuid.uuid4()), project_id=row.id, version=1, state="draft",
                settings_json='{"audio_mode":"mute","subtitle_style":{"font_size":52,"font_color":"#FFFFFF","box_color":"#111111","box_opacity":0.92,"margin_bottom":80}}',
                created_at=now, updated_at=now,
            )
        )

    op.create_table(
        "subtitle_segments",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("revision_id", sa.String(length=36), sa.ForeignKey("revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stable_id", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("translated_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column("review_flag", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("revision_id", "stable_id", name="uq_subtitle_revision_stable_id"),
    )
    op.create_index("ix_subtitle_revision_position", "subtitle_segments", ["revision_id", "position"])

    op.create_table(
        "overlay_regions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("revision_id", sa.String(length=36), sa.ForeignKey("revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False, server_default="ปิดซับเดิม"),
        sa.Column("x", sa.Float(), nullable=False),
        sa.Column("y", sa.Float(), nullable=False),
        sa.Column("width", sa.Float(), nullable=False),
        sa.Column("height", sa.Float(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False, server_default="#111111"),
        sa.Column("opacity", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_overlays_revision_id", "overlay_regions", ["revision_id"])

    op.create_table(
        "generated_copy",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("revision_id", sa.String(length=36), sa.ForeignKey("revisions.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("script_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("caption_candidates_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("selected_caption", sa.Text(), nullable=False, server_default=""),
        sa.Column("comment_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("model_name", sa.String(length=120), nullable=True),
        sa.Column("prompt_version", sa.String(length=40), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "renders",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("revision_id", sa.String(length=36), sa.ForeignKey("revisions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("output_asset_id", sa.String(length=36), sa.ForeignKey("assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("settings_hash", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False, server_default="queued"),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_renders_revision_created", "renders", ["revision_id", "created_at"])

    with op.batch_alter_table("jobs", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("revision_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"))
        batch_op.create_foreign_key("fk_jobs_revision_id_revisions", "revisions", ["revision_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    with op.batch_alter_table("jobs", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_jobs_revision_id_revisions", type_="foreignkey")
        batch_op.drop_column("payload_json")
        batch_op.drop_column("revision_id")
    op.drop_index("ix_renders_revision_created", table_name="renders")
    op.drop_table("renders")
    op.drop_table("generated_copy")
    op.drop_index("ix_overlays_revision_id", table_name="overlay_regions")
    op.drop_table("overlay_regions")
    op.drop_index("ix_subtitle_revision_position", table_name="subtitle_segments")
    op.drop_table("subtitle_segments")
    op.drop_index("ix_revisions_project_id", table_name="revisions")
    op.drop_table("revisions")
