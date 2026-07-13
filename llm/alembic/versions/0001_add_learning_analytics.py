"""add learning_events and topic_mastery tables

Revision ID: 0001
Revises:
Create Date: 2026-06-27
"""

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = "0000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic", sa.String(500), nullable=False),
        sa.Column("correct", sa.Boolean(), nullable=False),
        sa.Column("time_seconds", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("hint_used", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("mistakes", sa.JSON(), nullable=True),
        sa.Column("difficulty", sa.String(50), nullable=True),
        sa.Column("exercise_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_learning_events_project_id", "learning_events", ["project_id"])
    op.create_index("ix_learning_events_topic", "learning_events", ["project_id", "topic"])

    op.create_table(
        "topic_mastery",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("topic", sa.String(500), nullable=False),
        sa.Column("mastery_score", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("als_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("correct_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_time_seconds", sa.Float(), nullable=True),
        sa.Column("hint_usage_rate", sa.Float(), nullable=True),
        sa.Column("last_event_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("project_id", "topic", name="uq_topic_mastery"),
    )
    op.create_index("ix_topic_mastery_project_id", "topic_mastery", ["project_id"])


def downgrade() -> None:
    op.drop_table("topic_mastery")
    op.drop_table("learning_events")
