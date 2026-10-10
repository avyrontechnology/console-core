"""v32

Revision ID: 5307871e1b43
Revises: f6656e60d8c8
Create Date: 2026-01-27 13:00:53.969831

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = '5307871e1b43'
down_revision: Union[str, None] = 'f6656e60d8c8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add column as nullable first
    op.add_column(
        "console_orders",
        sa.Column("source", sa.String(length=50), nullable=True),
    )

    # Backfill existing rows
    op.execute(
        "UPDATE console_orders SET source = 'console' WHERE source IS NULL"
    )

    # Alter column to NOT NULL
    op.alter_column(
        "console_orders",
        "source",
        nullable=False,
    )

    # Add server-side default for safety
    op.alter_column(
        "console_orders",
        "source",
        server_default=sa.text("'console'"),
    )


def downgrade() -> None:
    op.drop_column("console_orders", "source")
