"""v44 add service type to notifications

Revision ID: 27ec9fd412ee
Revises: b7c4f9d2e1a0
Create Date: 2026-08-11 10:40:44.930110

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_utils


# revision identifiers, used by Alembic.    
revision: str = '27ec9fd412ee'
down_revision: Union[str, None] = 'b7c4f9d2e1a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "console_notification_serivce",
        sa.Column(
            "service_type",
            sa.String(length=50),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_console_notification_serivce_service_type",
        "console_notification_serivce",
        ["service_type"],
    )

    op.add_column(
        "console_notification_history",
        sa.Column(
            "service_type",
            sa.String(length=50),
            nullable=True,
        ),
    )

    op.create_index(
        "ix_console_notification_history_service_type",
        "console_notification_history",
        ["service_type"],
    )
    
    # Update notification subscription unique constraint
    op.drop_constraint(
        "uq_user_notification_identifier",
        "console_notification_serivce",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_user_notification_identifier_service",
        "console_notification_serivce",
        ["user_id", "identifier", "service_type"],
    )


def downgrade() -> None:
    # Restore old notification subscription unique constraint
    op.drop_constraint(
        "uq_user_notification_identifier_service",
        "console_notification_serivce",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_user_notification_identifier",
        "console_notification_serivce",
        ["user_id", "identifier"],
    )
    
    op.drop_index(
        "ix_console_notification_history_service_type",
        table_name="console_notification_history",
    )

    op.drop_column(
        "console_notification_history",
        "service_type",
    )

    op.drop_index(
        "ix_console_notification_serivce_service_type",
        table_name="console_notification_serivce",
    )

    op.drop_column(
        "console_notification_serivce",
        "service_type",
    )