"""v42

Revision ID: c8f3a1d2e4b6
Revises: 874d8f2a466b
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8f3a1d2e4b6'
down_revision: Union[str, None] = '874d8f2a466b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('console_users', sa.Column('current_status_icon', sa.String(length=100), nullable=True))
    op.alter_column(
        'console_users',
        'current_status',
        type_=sa.String(length=50),
        existing_type=sa.String(length=100),
    )


def downgrade() -> None:
    op.alter_column(
        'console_users',
        'current_status',
        type_=sa.String(length=100),
        existing_type=sa.String(length=50),
    )
    op.drop_column('console_users', 'current_status_icon')