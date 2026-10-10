"""v43 teams and per-partner role groundwork

Revision ID: b7c4f9d2e1a0
Revises: c8f3a1d2e4b6
Create Date: 2025-06-23

Adds:
- console_role.partner_id (NULL = system default role) + data_scope tier,
  swapping the global unique(hierarchy)/unique(slug) for per-scope uniqueness.
- console_team and console_team_member tables.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "b7c4f9d2e1a0"
down_revision = "c8f3a1d2e4b6"
branch_labels = None
depends_on = None


def _metadata_columns():
    """The standard MetaData base columns shared by every table."""
    return [
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("deleted_by", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("additional_info", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.BigInteger(), nullable=True),
        sa.Column("deleted_at", sa.BigInteger(), nullable=True),
    ]


def upgrade() -> None:
    # --- console_role: per-partner custom roles + data_scope ---------------
    op.add_column(
        "console_role",
        sa.Column("partner_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "console_role",
        sa.Column("data_scope", sa.String(length=16), nullable=True),
    )
    op.create_index(
        op.f("ix_console_role_partner_id"), "console_role", ["partner_id"], unique=False
    )
    op.create_foreign_key(
        "fk_console_role_partner_id",
        "console_role",
        "console_partners",
        ["partner_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    # Swap global uniqueness for per-scope uniqueness.
    op.drop_constraint("console_role_slug_key", "console_role", type_="unique")
    op.drop_constraint("console_role_hierarchy_key", "console_role", type_="unique")
    op.create_index(
        "uq_role_default_hierarchy",
        "console_role",
        ["hierarchy"],
        unique=True,
        postgresql_where=sa.text("partner_id IS NULL"),
    )
    op.create_index(
        "uq_role_default_slug",
        "console_role",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("partner_id IS NULL"),
    )
    op.create_unique_constraint(
        "uq_role_partner_hierarchy", "console_role", ["partner_id", "hierarchy"]
    )
    op.create_unique_constraint(
        "uq_role_partner_slug", "console_role", ["partner_id", "slug"]
    )

    # --- console_team ------------------------------------------------------
    op.create_table(
        "console_team",
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("partner_id", sa.Integer(), nullable=False),
        sa.Column("parent_team_id", sa.Integer(), nullable=True),
        sa.Column("is_internal", sa.Boolean(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("is_deleted", sa.Boolean(), nullable=True),
        *_metadata_columns(),
        sa.ForeignKeyConstraint(["partner_id"], ["console_partners.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_team_id"], ["console_team.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("partner_id", "slug", name="uq_team_partner_slug"),
    )
    op.create_index(op.f("ix_console_team_partner_id"), "console_team", ["partner_id"], unique=False)
    op.create_index(op.f("ix_console_team_parent_team_id"), "console_team", ["parent_team_id"], unique=False)
    op.create_index(op.f("ix_console_team_is_internal"), "console_team", ["is_internal"], unique=False)
    op.create_index(op.f("ix_console_team_is_active"), "console_team", ["is_active"], unique=False)
    op.create_index(op.f("ix_console_team_is_deleted"), "console_team", ["is_deleted"], unique=False)
    op.create_index(op.f("ix_console_team_updated_by"), "console_team", ["updated_by"], unique=False)

    # --- console_team_member ----------------------------------------------
    op.create_table(
        "console_team_member",
        sa.Column("team_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=True),
        *_metadata_columns(),
        sa.ForeignKeyConstraint(["team_id"], ["console_team.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["console_users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["role_id"], ["console_role.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_member_team_user"),
    )
    op.create_index(op.f("ix_console_team_member_team_id"), "console_team_member", ["team_id"], unique=False)
    op.create_index(op.f("ix_console_team_member_user_id"), "console_team_member", ["user_id"], unique=False)
    op.create_index(op.f("ix_console_team_member_updated_by"), "console_team_member", ["updated_by"], unique=False)


def downgrade() -> None:
    # team_member
    op.drop_index(op.f("ix_console_team_member_updated_by"), table_name="console_team_member")
    op.drop_index(op.f("ix_console_team_member_user_id"), table_name="console_team_member")
    op.drop_index(op.f("ix_console_team_member_team_id"), table_name="console_team_member")
    op.drop_table("console_team_member")

    # team
    op.drop_index(op.f("ix_console_team_updated_by"), table_name="console_team")
    op.drop_index(op.f("ix_console_team_is_deleted"), table_name="console_team")
    op.drop_index(op.f("ix_console_team_is_active"), table_name="console_team")
    op.drop_index(op.f("ix_console_team_is_internal"), table_name="console_team")
    op.drop_index(op.f("ix_console_team_parent_team_id"), table_name="console_team")
    op.drop_index(op.f("ix_console_team_partner_id"), table_name="console_team")
    op.drop_table("console_team")

    # role
    op.drop_constraint("uq_role_partner_slug", "console_role", type_="unique")
    op.drop_constraint("uq_role_partner_hierarchy", "console_role", type_="unique")
    op.drop_index("uq_role_default_slug", table_name="console_role")
    op.drop_index("uq_role_default_hierarchy", table_name="console_role")
    op.create_unique_constraint("console_role_hierarchy_key", "console_role", ["hierarchy"])
    op.create_unique_constraint("console_role_slug_key", "console_role", ["slug"])
    op.drop_constraint("fk_console_role_partner_id", "console_role", type_="foreignkey")
    op.drop_index(op.f("ix_console_role_partner_id"), table_name="console_role")
    op.drop_column("console_role", "data_scope")
    op.drop_column("console_role", "partner_id")