"""add BKT parameters to topic_mastery

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-28

Adds four BKT parameters and a predicted-correct column to topic_mastery.
mastery_score is now driven by BKT P(know) instead of EMA.
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("topic_mastery", sa.Column("bkt_p_know",    sa.Float(), nullable=False, server_default="0.1"))
    op.add_column("topic_mastery", sa.Column("bkt_p_transit", sa.Float(), nullable=False, server_default="0.1"))
    op.add_column("topic_mastery", sa.Column("bkt_p_guess",   sa.Float(), nullable=False, server_default="0.25"))
    op.add_column("topic_mastery", sa.Column("bkt_p_slip",    sa.Float(), nullable=False, server_default="0.1"))
    op.add_column("topic_mastery", sa.Column("bkt_p_correct_next", sa.Float(), nullable=True))
    op.add_column("topic_mastery", sa.Column("is_mastered",   sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("topic_mastery", "is_mastered")
    op.drop_column("topic_mastery", "bkt_p_correct_next")
    op.drop_column("topic_mastery", "bkt_p_slip")
    op.drop_column("topic_mastery", "bkt_p_guess")
    op.drop_column("topic_mastery", "bkt_p_transit")
    op.drop_column("topic_mastery", "bkt_p_know")
