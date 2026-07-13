"""Add example_bank table (Example RAG)

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-11
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "example_bank",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("sentence", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(200), nullable=False),
        sa.Column("level", sa.String(100), nullable=True),
        sa.Column("translation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.execute("ALTER TABLE example_bank ADD COLUMN embedding vector(384)")
    op.execute("""
        CREATE INDEX ix_example_bank_embedding
        ON example_bank
        USING hnsw(embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)
    op.create_index("ix_example_bank_topic_level", "example_bank", ["topic", "level"])


def downgrade() -> None:
    op.drop_index("ix_example_bank_topic_level", table_name="example_bank")
    op.execute("DROP INDEX IF EXISTS ix_example_bank_embedding")
    op.drop_table("example_bank")
