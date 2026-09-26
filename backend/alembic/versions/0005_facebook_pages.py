"""Add protected Facebook Page connection and remote publish tracking."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005_facebook_pages"
down_revision = "0004_publications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assets", sa.Column("frame_rate", sa.Float(), nullable=True))
    op.add_column("publications", sa.Column("page_id", sa.String(length=40), nullable=True))
    op.add_column("publications", sa.Column("remote_stage", sa.String(length=40), nullable=True))
    op.add_column("publications", sa.Column("remote_video_id", sa.String(length=200), nullable=True))
    op.add_column("publications", sa.Column("remote_comment_id", sa.String(length=200), nullable=True))
    op.add_column("publications", sa.Column("next_poll_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("publications", sa.Column("publish_started_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_publications_status_poll", "publications", ["status", "next_poll_at"])
    op.create_table(
        "facebook_pages",
        sa.Column("id", sa.String(length=40), primary_key=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("tasks_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_facebook_pages_active", "facebook_pages", ["is_active"])


def downgrade() -> None:
    op.drop_index("ix_facebook_pages_active", table_name="facebook_pages")
    op.drop_table("facebook_pages")
    op.drop_index("ix_publications_status_poll", table_name="publications")
    op.drop_column("publications", "publish_started_at")
    op.drop_column("publications", "next_poll_at")
    op.drop_column("publications", "remote_comment_id")
    op.drop_column("publications", "remote_video_id")
    op.drop_column("publications", "remote_stage")
    op.drop_column("publications", "page_id")
    op.drop_column("assets", "frame_rate")
