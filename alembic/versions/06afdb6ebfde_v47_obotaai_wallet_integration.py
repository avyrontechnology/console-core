"""v47_obotaai_wallet_integration

Revision ID: 06afdb6ebfde
Revises: bb639fc29780
Create Date: 2026-09-28 00:00:00.000000

Obotaai wallet integration, Phase 1 (console-service foundation):
- ServiceName gets a new OBOTAAI member (native Postgres enum
  `servicename` -- SQLAlchemy's Enum(PythonEnum) stores the member name,
  not `.value`, so the DB-side type needs the value added too, not just
  the Python enum class).
- An expression index on console_wallet_transactions' JSON `attributes`
  column, keyed on `usage_event_idempotency_key` -- the idempotent-debit
  existence check the Obotaai billing_sync pull relies on before ever
  calling perform_transaction(), so a retried pull is a safe re-ack
  rather than a double debit.

ADD VALUE run in an autocommit block: Postgres disallows ALTER TYPE ...
ADD VALUE inside a transaction block on versions before 12, and even on
12+ a value added inside a transaction can't be used by a query in that
same transaction -- this migration only adds it, never uses it, but the
autocommit block keeps this safe across Postgres versions regardless.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '06afdb6ebfde'
down_revision: Union[str, None] = 'bb639fc29780'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE servicename ADD VALUE IF NOT EXISTS 'OBOTAAI'")

    op.create_index(
        'ix_wallet_transactions_usage_event_idempotency_key',
        'console_wallet_transactions',
        [sa.text("(attributes ->> 'usage_event_idempotency_key')")],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_wallet_transactions_usage_event_idempotency_key',
        table_name='console_wallet_transactions',
    )
    # Postgres does not support removing a value from an enum type --
    # 'OBOTAAI' stays in `servicename` on downgrade. Harmless: nothing
    # reads/writes it once this migration is reverted, since the Python
    # ServiceName.OBOTAAI member and every caller of it ship in the same
    # commit as this migration.
