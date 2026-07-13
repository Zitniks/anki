"""rename fileentitytype enum values to uppercase to match SQLAlchemy default

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-28
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SQLAlchemy's SAEnum(FileEntityType) sends the Python enum .name (uppercase)
    # as the PostgreSQL bind parameter. Rename the values to match.
    op.execute("ALTER TYPE fileentitytype RENAME VALUE 'message' TO 'MESSAGE'")
    op.execute("ALTER TYPE fileentitytype RENAME VALUE 'material' TO 'MATERIAL'")
    op.execute("ALTER TYPE fileentitytype RENAME VALUE 'repeat_item' TO 'REPEAT_ITEM'")


def downgrade() -> None:
    op.execute("ALTER TYPE fileentitytype RENAME VALUE 'MESSAGE' TO 'message'")
    op.execute("ALTER TYPE fileentitytype RENAME VALUE 'MATERIAL' TO 'material'")
    op.execute("ALTER TYPE fileentitytype RENAME VALUE 'REPEAT_ITEM' TO 'repeat_item'")
