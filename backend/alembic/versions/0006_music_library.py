"""Add reusable music library."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0006_music_library"
down_revision = "0005_facebook_pages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "music_tracks",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("relative_path", sa.String(length=1024), nullable=False, unique=True),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_music_tracks_created_at", "music_tracks", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_music_tracks_created_at", table_name="music_tracks")
    op.drop_table("music_tracks")
