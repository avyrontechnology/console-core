"""v45 add role base_role_id provenance

Revision ID: d5e8b1c4a072
Revises: 27ec9fd412ee
Create Date: 2026-08-06

Adds:
- console_role.base_role_id: nullable self-referential FK recording the role a
  custom role's permissions were seeded from at creation (NULL for system
  default roles). ondelete SET NULL so a base role can be removed without
  blocking; roles are soft-deleted anyway, so it rarely fires.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d5e8b1c4a072"
down_revision = "27ec9fd412ee"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "console_role",
        sa.Column("base_role_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_console_role_base_role_id"),
        "console_role",
        ["base_role_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_console_role_base_role_id",
        "console_role",
        "console_role",
        ["base_role_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_console_role_base_role_id", "console_role", type_="foreignkey"
    )
    op.drop_index(
        op.f("ix_console_role_base_role_id"), table_name="console_role"
    )
    op.drop_column("console_role", "base_role_id")
