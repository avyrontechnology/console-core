"""v29

Revision ID: 8c367767979e
Revises: a5f2afe24472
Create Date: 2026-01-14 18:52:23.842212
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8c367767979e"
down_revision: Union[str, None] = "a5f2afe24472"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns temporarily nullable
    op.add_column(
        "console_plans",
        sa.Column("heirarchy", sa.Integer(), nullable=True),
    )
    op.add_column(
        "console_plans",
        sa.Column("tag", sa.String(length=30), nullable=True),
    )
    op.add_column(
        "console_plans",
        sa.Column("service_name", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "console_plans",
        sa.Column("is_free_trial", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "console_plans",
        sa.Column("otc_charge", sa.Float(), nullable=True),
    )

    conn = op.get_bind()

    # Fetch existing plans ordered by id
    rows = conn.execute(
        sa.text(
            """
            SELECT id
            FROM console_plans
            ORDER BY id
            """
        )
    ).fetchall()

    # Backfill heirarchy, tag and service_name
    for index, row in enumerate(rows):
        conn.execute(
            sa.text(
                """
                UPDATE console_plans
                SET heirarchy = :heirarchy,
                    tag = :tag,
                    service_name = :service_name
                WHERE id = :id
                """
            ),
            {
                "heirarchy": index * 5,
                "tag": "standard",
                "service_name": "maglo",
                "id": row.id,
            },
        )

    # Make columns non-nullable after backfill
    op.alter_column("console_plans", "heirarchy", nullable=False)
    op.alter_column("console_plans", "tag", nullable=False)
    op.alter_column("console_plans", "service_name", nullable=False)

    # Create indexes and unique constraint
    op.create_index(
        "ix_console_plans_service_name",
        "console_plans",
        ["service_name"],
        unique=False,
    )
    op.create_index(
        "ix_console_plans_tag",
        "console_plans",
        ["tag"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_console_plans_heirarchy",
        "console_plans",
        ["heirarchy"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_console_plans_heirarchy",
        "console_plans",
        type_="unique",
    )
    op.drop_index("ix_console_plans_tag", table_name="console_plans")
    op.drop_index("ix_console_plans_service_name", table_name="console_plans")
    op.drop_column("console_plans", "otc_charge")
    op.drop_column("console_plans", "is_free_trial")
    op.drop_column("console_plans", "service_name")
    op.drop_column("console_plans", "tag")
    op.drop_column("console_plans", "heirarchy")
