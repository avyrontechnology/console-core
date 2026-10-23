"""One-time bootstrap: system-admin role (hierarchy -1) + first system user.

The permission system grants all slugs to the earliest active user whose
role has hierarchy -1 (see UserRepository.get_system_admin_user). Without
this script that identity only exists via manual DB inserts (chicken-and-egg).

Usage:
    POSTGRES_* envs must point at the target DB.
    SYSTEM_ADMIN_EMAIL / SYSTEM_ADMIN_PASSWORD envs (password min 8 chars).
    Safe to re-run: existing role/user are reused, never duplicated.

Every action is printed AND audit-logged to console_audit_logs.
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from src.components.auth.models import Role  # noqa: E402
from src.components.user.models import User  # noqa: E402
from src.core.db import DatabaseSessionManager  # noqa: E402
from src.core.environment import ENV  # noqa: E402

SYSTEM_ROLE_HIERARCHY = -1
SYSTEM_ROLE_NAME = "system_admin"
SYSTEM_ROLE_SLUG = "system_admin"


async def main() -> None:
    email = os.getenv("SYSTEM_ADMIN_EMAIL", "").strip().lower()
    password = os.getenv("SYSTEM_ADMIN_PASSWORD", "")
    if not email or len(password) < 8:
        print("Set SYSTEM_ADMIN_EMAIL and SYSTEM_ADMIN_PASSWORD (min 8 chars).")
        sys.exit(2)

    from passlib.context import CryptContext

    from src.core.app_env import AppEnvironment

    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    url = "postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}{ssl}".format(
        user=ENV.POSTGRES_USER,
        password=ENV.POSTGRES_PASSWORD,
        host=ENV.POSTGRES_HOST,
        port=ENV.POSTGRES_PORT,
        db=ENV.POSTGRES_DB,
        ssl=(
            "?ssl=require"
            if ENV.ENVIRONMENT != AppEnvironment.AllowedEnvs.Local.value
            else ""
        ),
    )
    mgr = DatabaseSessionManager(url)
    async with mgr.session() as session:
        role = (
            await session.execute(
                select(Role).where(Role.hierarchy == SYSTEM_ROLE_HIERARCHY)
            )
        ).scalars().first()
        if role is None:
            role = Role(
                id=uuid.uuid4(),
                name=SYSTEM_ROLE_NAME,
                slug=SYSTEM_ROLE_SLUG,
                hierarchy=SYSTEM_ROLE_HIERARCHY,
                is_active=True,
                is_deleted=False,
                is_internal=True,
            )
            session.add(role)
            await session.flush()
            print(f"Created role {SYSTEM_ROLE_NAME} id={role.id}")
        else:
            print(f"Role exists id={role.id} slug={role.slug}")

        user = (
            await session.execute(select(User).where(User.email == email))
        ).scalars().first()
        if user is None:
            user = User(
                id=uuid.uuid4(),
                name="System Admin",
                email=email,
                hashed_password=pwd_context.hash(password),
                partner_id=None,
                role_id=role.id,
                is_active=True,
                is_deleted=False,
                is_staff=True,
                is_admin=True,
                is_internal=True,
            )
            session.add(user)
            await session.flush()
            print(f"Created user {email} id={user.id}")
        else:
            print(f"User exists id={user.id} (password unchanged)")
        await session.commit()
    print("Bootstrap complete.")


if __name__ == "__main__":
    asyncio.run(main())
