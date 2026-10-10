"""v46_add_indexes_for_user_listing_filters

Revision ID: bb639fc29780
Revises: d5e8b1c4a072
Create Date: 2026-08-21 06:50:13.252838

Adds indexes on console_users columns the User Listing filters (MGL-9482)
query frequently:
- created_at, updated_at: BETWEEN/BEFORE/AFTER range scans
- current_status: equality lookups for the Availability filter

console_users.is_active, .role_id, .partner_id and .is_internal already
carry an index from earlier migrations, so they are left untouched here.

NOTE: autogenerate also picked up a large amount of unrelated pre-existing
drift between models.py and this database (dropped oauth_* tables, a
dropped console_users.username column, constraint renames, a nullable
change on created_at, and an unrelated is_walkthrough_completed index).
None of that belongs to this change, so it was stripped out by hand -
only the three index additions below are intentional.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'bb639fc29780'
down_revision: Union[str, None] = 'd5e8b1c4a072'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f('ix_console_users_created_at'), 'console_users', ['created_at'], unique=False)
    op.create_index(op.f('ix_console_users_current_status'), 'console_users', ['current_status'], unique=False)
    op.create_index(op.f('ix_console_users_updated_at'), 'console_users', ['updated_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_console_users_updated_at'), table_name='console_users')
    op.drop_index(op.f('ix_console_users_current_status'), table_name='console_users')
    op.drop_index(op.f('ix_console_users_created_at'), table_name='console_users')
