"""v36

Revision ID: a7c7910584e7
Revises: b97f4ef4539a
Create Date: 2026-03-23 07:10:11.072325

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = 'a7c7910584e7'
down_revision: Union[str, None] = 'b97f4ef4539a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('console_users', sa.Column('current_status', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('console_users', 'current_status')
