"""v30

Revision ID: 8e2e6332d2a0
Revises: 8c367767979e
Create Date: 2026-01-20 13:04:54.468294
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8e2e6332d2a0'
down_revision: Union[str, None] = '8c367767979e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # FIX heirarchy -> hierarchy (data-safe rename)
    # ------------------------------------------------------------------

    # 1. Add new column as NULLABLE
    op.add_column(
        'console_plans',
        sa.Column('hierarchy', sa.Integer(), nullable=True)
    )

    # 2. Copy existing data
    op.execute(
        """
        UPDATE console_plans
        SET hierarchy = heirarchy
        WHERE hierarchy IS NULL
        """
    )

    # 3. Make new column NOT NULL
    op.alter_column(
        'console_plans',
        'hierarchy',
        nullable=False
    )

    # 4. Replace unique constraint
    op.drop_constraint(
        op.f('uq_console_plans_heirarchy'),
        'console_plans',
        type_='unique'
    )

    op.create_unique_constraint(
        'uq_console_plans_hierarchy',
        'console_plans',
        ['hierarchy']
    )

    # 5. Drop old misspelled column
    op.drop_column('console_plans', 'heirarchy')

    # ------------------------------------------------------------------
    # ADD duration column (months)
    # ------------------------------------------------------------------

    # 6. Add duration as nullable
    op.add_column(
        'console_plans',
        sa.Column('duration', sa.Integer(), nullable=True)
    )

    # 7. Backfill existing rows
    op.execute(
        "UPDATE console_plans SET duration = 1 WHERE duration IS NULL"
    )

    # 8. Enforce NOT NULL
    op.alter_column(
        'console_plans',
        'duration',
        nullable=False
    )


def downgrade() -> None:
    # ------------------------------------------------------------------
    # REVERT duration
    # ------------------------------------------------------------------

    op.drop_column('console_plans', 'duration')

    # ------------------------------------------------------------------
    # REVERT hierarchy -> heirarchy
    # ------------------------------------------------------------------

    # 1. Recreate old column as nullable
    op.add_column(
        'console_plans',
        sa.Column('heirarchy', sa.Integer(), nullable=True)
    )

    # 2. Copy data back
    op.execute(
        """
        UPDATE console_plans
        SET heirarchy = hierarchy
        WHERE heirarchy IS NULL
        """
    )

    # 3. Restore NOT NULL
    op.alter_column(
        'console_plans',
        'heirarchy',
        nullable=False
    )

    # 4. Restore unique constraint
    op.drop_constraint(
        'uq_console_plans_hierarchy',
        'console_plans',
        type_='unique'
    )

    op.create_unique_constraint(
        op.f('uq_console_plans_heirarchy'),
        'console_plans',
        ['heirarchy']
    )

    # 5. Drop new column
    op.drop_column('console_plans', 'hierarchy')
