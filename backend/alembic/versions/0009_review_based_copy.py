"""Store review evidence, review analysis, and optional discount copy."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0009_review_based_copy"
down_revision = "0008_photo_publications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("review_evidence", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("discount_text", sa.String(length=400), nullable=True))
    op.add_column("generated_copy", sa.Column("review_score", sa.Float(), nullable=True))
    op.add_column("generated_copy", sa.Column("review_summary", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("generated_copy", "review_summary")
    op.drop_column("generated_copy", "review_score")
    op.drop_column("projects", "discount_text")
    op.drop_column("projects", "review_evidence")
