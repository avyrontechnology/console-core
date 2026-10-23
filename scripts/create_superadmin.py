"""Create a local superadmin login for console-core.

WHAT IT DOES (idempotent — safe to re-run)
  1. Ensures the system role at hierarchy 0 (Super Admin, partner_id NULL).
  2. Grants that role every permission via console_default_role_permission.
  3. Ensures an internal partner exists for the user to belong to.
  4. Ensures the partner_config rows login reads (otp/verification/talko).
  5. Upserts the user (bcrypt hash) and prints the credentials.

USAGE
  python scripts/create_superadmin.py --email admin@local.test --password 'Str0ng-Pass!'
  SUPERADMIN_EMAIL=... SUPERADMIN_PASSWORD=... python scripts/create_superadmin.py

Requires a migrated database (alembic upgrade head) and reachable Postgres.
"""
import argparse
import asyncio
import getpass
import os
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from src.core.environment import ENV  # noqa: E402

SUPERADMIN_HIERARCHY = 0
SUPERADMIN_SLUG = "superadmin"
ROLE_NAME = "Super Admin"
ROLE_DESCRIPTION = "System superadmin with full access"
INTERNAL_PARTNER_NAME = "Console Internal"
PARTNER_LEGAL_NAME = "Console Internal Pvt Ltd"

# Login reads these partner_config keys; missing rows make get_token raise.
LOGIN_CRITICAL_CONFIG = {
    "is_otp_enabled": False,
    "is_email_verification_enabled": False,
    "is_phone_number_verification_enabled": False,
    "is_talko_enabled": True,
    "is_custom_role_permission_enabled": False,
}

DSN = (
    "postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}".format(
        user=ENV.POSTGRES_USER,
        password=ENV.POSTGRES_PASSWORD,
        host=ENV.POSTGRES_HOST,
        port=ENV.POSTGRES_PORT,
        db=ENV.POSTGRES_DB,
    )
)


def hashed(password: str) -> str:
    from passlib.context import CryptContext

    # Same scheme the login path verifies against.
    return CryptContext(schemes=["bcrypt"], deprecated="auto").hash(password)


async def ensure_role(conn) -> str:
    row = (
        await conn.execute(
            text(
                "SELECT id FROM console_role "
                "WHERE hierarchy = :h AND partner_id IS NULL"
            ),
            {"h": SUPERADMIN_HIERARCHY},
        )
    ).fetchone()
    if row:
        return str(row[0])

    role_id = str(uuid.uuid4())
    await conn.execute(
        text(
            "INSERT INTO console_role (id, name, slug, hierarchy, partner_id, "
            "description, data_scope, is_active, is_deleted, created_at) "
            "VALUES (:id, :name, :slug, :h, NULL, :desc, 'ALL', TRUE, FALSE, :now)"
        ),
        {
            "id": role_id,
            "name": ROLE_NAME,
            "slug": SUPERADMIN_SLUG,
            "h": SUPERADMIN_HIERARCHY,
            "desc": ROLE_DESCRIPTION,
            "now": int(time.time() * 1000),
        },
    )
    print("created system role:", SUPERADMIN_SLUG)
    return role_id


async def grant_all_permissions(conn, role_id: str) -> int:
    result = await conn.execute(
        text(
            "INSERT INTO console_default_role_permission "
            "(id, role_id, permission_id, created_at) "
            "SELECT gen_random_uuid(), :role, p.id, :now "
            "FROM console_permission p "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM console_default_role_permission d "
            "  WHERE d.role_id = :role AND d.permission_id = p.id"
            ")"
        ),
        {"role": role_id, "now": int(time.time() * 1000)},
    )
    return result.rowcount or 0


async def ensure_partner(conn) -> str:
    row = (
        await conn.execute(
            text("SELECT id FROM console_partners WHERE name = :n"),
            {"n": INTERNAL_PARTNER_NAME},
        )
    ).fetchone()
    if row:
        return str(row[0])

    partner_id = str(uuid.uuid4())
    await conn.execute(
        text(
            "INSERT INTO console_partners (id, name, company_legal_name, "
            "active_license, is_active, is_deleted, is_internal, partner_status, "
            "created_at) "
            "VALUES (:id, :n, :legal, 0, TRUE, FALSE, TRUE, 'ACTIVE', :now)"
        ),
        {
            "id": partner_id,
            "n": INTERNAL_PARTNER_NAME,
            "legal": PARTNER_LEGAL_NAME,
            "now": int(time.time() * 1000),
        },
    )
    print("created internal partner:", INTERNAL_PARTNER_NAME)
    return partner_id


async def ensure_partner_configs(conn, partner_id: str) -> None:
    for key, value in LOGIN_CRITICAL_CONFIG.items():
        await conn.execute(
            text(
                "INSERT INTO console_partner_config (id, partner_id, key, value, "
                "created_at) SELECT gen_random_uuid(), CAST(:pid AS uuid), "
                "CAST(:k AS varchar), CAST(:v AS jsonb), :now "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM console_partner_config "
                "  WHERE partner_id = CAST(:pid AS uuid) AND key = CAST(:k AS varchar)"
                ")"
            ),
            {
                "pid": partner_id,
                "k": key,
                "v": "true" if value else "false",
                "now": int(time.time() * 1000),
            },
        )


async def ensure_wallet(conn, partner_id: str) -> None:
    await conn.execute(
        text(
            "INSERT INTO console_wallets (id, partner_id, balance, frozen_balance, "
            "currency, created_at) SELECT gen_random_uuid(), CAST(:pid AS uuid), "
            "1000.00, 0, 'INR', :now WHERE NOT EXISTS ("
            "  SELECT 1 FROM console_wallets WHERE partner_id = CAST(:pid AS uuid)"
            ")"
        ),
        {"pid": partner_id, "now": int(time.time() * 1000)},
    )


async def ensure_api_key(conn, partner_id: str) -> None:
    """A partner key so the API-KEY auth path and the UI page both work."""
    import secrets

    await conn.execute(
        text(
            "INSERT INTO console_api_keys (id, key, scopes, user_context, is_active, "
            "partner_id, created_at) "
            "SELECT gen_random_uuid(), :key, "
            "'[]'::jsonb, NULL, TRUE, CAST(:pid AS uuid), :now WHERE NOT EXISTS ("
            "  SELECT 1 FROM console_api_keys WHERE partner_id = CAST(:pid AS uuid)"
            ")"
        ),
        {"pid": partner_id, "key": secrets.token_hex(32), "now": int(time.time() * 1000)},
    )


async def upsert_user(conn, email: str, password: str, name: str, phone: str) -> str:
    row = (
        await conn.execute(
            text("SELECT id FROM console_users WHERE email = :e"), {"e": email}
        )
    ).fetchone()
    now = int(time.time() * 1000)
    if row:
        user_id = str(row[0])
        await conn.execute(
            text(
                "UPDATE console_users SET hashed_password = :pw, name = :n, "
                "phone_number = :ph, is_active = TRUE, is_deleted = FALSE "
                "WHERE id = :id"
            ),
            {"pw": hashed(password), "n": name, "ph": phone, "id": user_id},
        )
        print("updated existing user:", email)
        return user_id

    user_id = str(uuid.uuid4())
    await conn.execute(
        text(
            "INSERT INTO console_users (id, name, email, phone_number, "
            "hashed_password, is_active, is_deleted, is_internal, is_staff, "
            "is_admin, is_email_verified, is_phone_number_verified, created_at) "
            "VALUES (:id, :n, :e, :ph, :pw, TRUE, FALSE, TRUE, TRUE, TRUE, "
            "TRUE, TRUE, :now)"
        ),
        {
            "id": user_id,
            "n": name,
            "e": email,
            "ph": phone,
            "pw": hashed(password),
            "now": now,
        },
    )
    print("created user:", email)
    return user_id


async def main(email: str, password: str, name: str, phone: str) -> None:
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(DSN, poolclass=None)
    async with engine.begin() as conn:
        role_id = await ensure_role(conn)
        partner_id = await ensure_partner(conn)
        await ensure_partner_configs(conn, partner_id)
        await ensure_wallet(conn, partner_id)
        await ensure_api_key(conn, partner_id)

        user_id = await upsert_user(conn, email, password, name, phone)
        await conn.execute(
            text(
                "UPDATE console_users SET partner_id = :pid, role_id = :rid "
                "WHERE id = :uid"
            ),
            {"pid": partner_id, "rid": role_id, "uid": user_id},
        )
        granted = await grant_all_permissions(conn, role_id)
    await engine.dispose()

    print("\n--- superadmin ready ---")
    print("email:           ", email)
    print("password:        ", password)
    print("user_id:         ", user_id)
    print("role (hier 0):   ", role_id)
    print("partner_id:      ", partner_id)
    print("permissions added this run:", granted)
    print("\nLog in at http://localhost:3000/login (or POST /do_login?svc_name=console).")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default=os.getenv("SUPERADMIN_EMAIL", ""))
    ap.add_argument("--password", default=os.getenv("SUPERADMIN_PASSWORD", ""))
    ap.add_argument("--name", default=os.getenv("SUPERADMIN_NAME", "Super Admin"))
    ap.add_argument("--phone", default=os.getenv("SUPERADMIN_PHONE", "9999999999"))
    args = ap.parse_args()

    email = args.email.strip().lower()
    password = args.password
    if not password:
        password = getpass.getpass("Password for superadmin: ")
    if not email or not password:
        sys.exit("Need --email and a password.")

    asyncio.run(main(email, password, args.name, args.phone))