"""v41 — OAuth 2.1 authorization server tables

Adds the five tables backing the self-hosted OAuth server in
src/components/oauth_server. Purely additive — no changes to existing
tables. Safe to roll forward without coordinating with running traffic;
on rollback, ``downgrade()`` drops the new tables and leaves everything
else untouched.

Revision ID: 874d8f2a466b
Revises: f3965f39e7fe
Create Date: 2026-05-25
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "874d8f2a466b"
down_revision: Union[str, None] = "f3965f39e7fe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.String(length=64), primary_key=True),
        sa.Column("client_secret_hash", sa.String(length=128), nullable=True),
        sa.Column("client_name", sa.String(length=255), nullable=False),
        sa.Column("redirect_uris", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("grant_types", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scope", sa.String(length=2048), nullable=False),
        sa.Column(
            "token_endpoint_auth_method", sa.String(length=64), nullable=False
        ),
        sa.Column("registered_at", sa.BigInteger(), nullable=False),
        sa.Column("registered_by_ip", sa.String(length=64), nullable=True),
        sa.Column("registered_user_agent", sa.String(length=512), nullable=True),
        sa.Column("disabled_at", sa.BigInteger(), nullable=True),
    )

    op.create_table(
        "oauth_authorization_codes",
        sa.Column("code_hash", sa.String(length=128), primary_key=True),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("redirect_uri", sa.String(length=1024), nullable=False),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("code_challenge", sa.String(length=128), nullable=False),
        sa.Column(
            "code_challenge_method", sa.String(length=16), nullable=False
        ),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("consumed_at", sa.BigInteger(), nullable=True),
    )
    op.create_index(
        "ix_oauth_authorization_codes_client_id",
        "oauth_authorization_codes",
        ["client_id"],
    )
    op.create_index(
        "ix_oauth_authorization_codes_user_id",
        "oauth_authorization_codes",
        ["user_id"],
    )
    op.create_index(
        "ix_oauth_authorization_codes_expires_at",
        "oauth_authorization_codes",
        ["expires_at"],
    )

    op.create_table(
        "oauth_refresh_tokens",
        sa.Column("token_hash", sa.String(length=128), primary_key=True),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("issued_at", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("revoked_at", sa.BigInteger(), nullable=True),
        sa.Column("consumed_at", sa.BigInteger(), nullable=True),
        sa.Column("parent_token_hash", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_oauth_refresh_tokens_client_id",
        "oauth_refresh_tokens",
        ["client_id"],
    )
    op.create_index(
        "ix_oauth_refresh_tokens_user_id",
        "oauth_refresh_tokens",
        ["user_id"],
    )
    op.create_index(
        "ix_oauth_refresh_tokens_expires_at",
        "oauth_refresh_tokens",
        ["expires_at"],
    )
    op.create_index(
        "ix_oauth_refresh_tokens_parent_token_hash",
        "oauth_refresh_tokens",
        ["parent_token_hash"],
    )

    op.create_table(
        "oauth_consents",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("client_id", sa.String(length=64), nullable=False),
        sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("granted_at", sa.BigInteger(), nullable=False),
        sa.Column("revoked_at", sa.BigInteger(), nullable=True),
        sa.UniqueConstraint(
            "user_id", "client_id", name="uq_oauth_consent_user_client"
        ),
    )
    op.create_index("ix_oauth_consents_user_id", "oauth_consents", ["user_id"])
    op.create_index(
        "ix_oauth_consents_client_id", "oauth_consents", ["client_id"]
    )

    op.create_table(
        "oauth_authorize_requests",
        sa.Column("request_id", sa.String(length=64), primary_key=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column(
            "consent_recorded",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
    )
    op.create_index(
        "ix_oauth_authorize_requests_user_id",
        "oauth_authorize_requests",
        ["user_id"],
    )
    op.create_index(
        "ix_oauth_authorize_requests_expires_at",
        "oauth_authorize_requests",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_oauth_authorize_requests_expires_at",
        table_name="oauth_authorize_requests",
    )
    op.drop_index(
        "ix_oauth_authorize_requests_user_id",
        table_name="oauth_authorize_requests",
    )
    op.drop_table("oauth_authorize_requests")

    op.drop_index("ix_oauth_consents_client_id", table_name="oauth_consents")
    op.drop_index("ix_oauth_consents_user_id", table_name="oauth_consents")
    op.drop_table("oauth_consents")

    op.drop_index(
        "ix_oauth_refresh_tokens_parent_token_hash",
        table_name="oauth_refresh_tokens",
    )
    op.drop_index(
        "ix_oauth_refresh_tokens_expires_at", table_name="oauth_refresh_tokens"
    )
    op.drop_index(
        "ix_oauth_refresh_tokens_user_id", table_name="oauth_refresh_tokens"
    )
    op.drop_index(
        "ix_oauth_refresh_tokens_client_id", table_name="oauth_refresh_tokens"
    )
    op.drop_table("oauth_refresh_tokens")

    op.drop_index(
        "ix_oauth_authorization_codes_expires_at",
        table_name="oauth_authorization_codes",
    )
    op.drop_index(
        "ix_oauth_authorization_codes_user_id",
        table_name="oauth_authorization_codes",
    )
    op.drop_index(
        "ix_oauth_authorization_codes_client_id",
        table_name="oauth_authorization_codes",
    )
    op.drop_table("oauth_authorization_codes")

    op.drop_table("oauth_clients")
