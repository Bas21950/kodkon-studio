"""Store all images attached to a photo publication."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0011_publication_media_assets"
down_revision = "0010_product_link_research"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "publications",
        sa.Column("media_asset_ids_json", sa.Text(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("publications", "media_asset_ids_json")
