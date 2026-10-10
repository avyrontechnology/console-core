import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from src.core.app_env import AppEnvironment
from src.core.environment import ENV

DATABASE_URL = "postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}{ssl}".format(
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

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata

from src.components.org.model import Base, Organization

target_metadata = Base.metadata
from src.components.api_key.models import ApiKey
from src.components.audit_log.models import AuditLog
from src.components.db_constants.models import (
    Constants,
    DynamicVariables,
    GlobalConstants,
    GlobalDynamicVariables,
    GlobalMediaConstants,
    MediaConstants,
)
from src.components.release_note.models import ReleaseNotes
from src.components.default_role_permission.models import DefaultRolePermission
from src.components.digital_assets.models import DigitalAssets
from src.components.location.models import Cities, Countries, States
from src.components.partner.models import Partner
from src.components.partner_config.models import PartnerConfig
from src.components.payment.models import Payment
from src.components.session_mangement.models import UserSession
from src.components.user.models import User
from src.components.user_config.models import UserConfig
from src.components.user_metadata.models import UserMetadata
from src.components.wallet.models import Wallet, WalletTransaction
from src.components.plan.models import Plan
from src.components.order.models import Order
from src.components.entitlement.models import Entitlement
from src.components.team.models import Team, TeamMember
from src.components.notifications.models import NotificationHistory, NotificationSubscription
from src.components.grace.models import GracePeriod

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """

    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
