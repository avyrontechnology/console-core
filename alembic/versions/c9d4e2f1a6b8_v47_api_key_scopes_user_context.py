"""v47_api_key_scopes_user_context

Revision ID: c9d4e2f1a6b8
Revises: bb639fc29780
Create Date: 2026-09-09 00:00:00.000000

Adds ``user_context`` (JSON) to ``console_api_keys``. The existing ``scopes``
column is reused as-is (its semantics become a list[str] of permission slugs),
so no DDL is required for it.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d4e2f1a6b8'
down_revision: Union[str, None] = 'bb639fc29780'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'console_api_keys',
        sa.Column('user_context', sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('console_api_keys', 'user_context')
