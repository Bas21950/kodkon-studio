"""Add support for image publications."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008_photo_publications"
down_revision = "0007_product_copy_details"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "publications",
        sa.Column("media_type", sa.String(length=16), nullable=False, server_default="video"),
    )


def downgrade() -> None:
    op.drop_column("publications", "media_type")
