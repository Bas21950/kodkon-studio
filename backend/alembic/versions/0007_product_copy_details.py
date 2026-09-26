"""Store product facts and preferred sales copy style."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007_product_copy_details"
down_revision = "0006_music_library"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("product_details", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("copy_style", sa.String(length=32), nullable=False, server_default="problem_solution"))


def downgrade() -> None:
    op.drop_column("projects", "copy_style")
    op.drop_column("projects", "product_details")
