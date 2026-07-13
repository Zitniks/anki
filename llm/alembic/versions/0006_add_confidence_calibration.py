"""Add confidence calibration columns to topic_mastery

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-28
"""

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("topic_mastery", sa.Column("avg_confidence", sa.Float(), nullable=True))
    op.add_column("topic_mastery", sa.Column("confidence_bias", sa.Float(), nullable=True))
    op.add_column("topic_mastery", sa.Column("calibration_error", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("topic_mastery", "calibration_error")
    op.drop_column("topic_mastery", "confidence_bias")
    op.drop_column("topic_mastery", "avg_confidence")
