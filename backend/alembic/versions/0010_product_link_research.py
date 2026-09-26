"""Store product details and rating read from the public source link."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010_product_link_research"
down_revision = "0009_review_based_copy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("product_source_details", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("product_average_rating", sa.Float(), nullable=True))
    op.add_column("projects", sa.Column("product_review_count", sa.Integer(), nullable=True))
    op.add_column("projects", sa.Column("product_review_summary", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("product_data_read_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "product_data_read_at")
    op.drop_column("projects", "product_review_summary")
    op.drop_column("projects", "product_review_count")
    op.drop_column("projects", "product_average_rating")
    op.drop_column("projects", "product_source_details")
