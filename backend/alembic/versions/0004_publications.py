"""Add durable local publication snapshots, schedules, and event history."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_publications"
down_revision = "0003_ai_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "publications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("revision_id", sa.String(length=36), sa.ForeignKey("revisions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("render_asset_id", sa.String(length=36), sa.ForeignKey("assets.id", ondelete="SET NULL"), nullable=True),
        sa.Column("platform", sa.String(length=40), nullable=False, server_default="facebook_page"),
        sa.Column("page_name", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("comment_status", sa.String(length=32), nullable=False, server_default="not_set"),
        sa.Column("caption", sa.Text(), nullable=False),
        sa.Column("comment_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("affiliate_url", sa.String(length=2048), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_post_id", sa.String(length=200), nullable=True),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_publications_status_scheduled", "publications", ["status", "scheduled_at"])
    op.create_index("ix_publications_project_created", "publications", ["project_id", "created_at"])
    op.create_table(
        "publication_events",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("publication_id", sa.String(length=36), sa.ForeignKey("publications.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_publication_events_publication_created", "publication_events", ["publication_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_publication_events_publication_created", table_name="publication_events")
    op.drop_table("publication_events")
    op.drop_index("ix_publications_project_created", table_name="publications")
    op.drop_index("ix_publications_status_scheduled", table_name="publications")
    op.drop_table("publications")
