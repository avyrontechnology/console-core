"""
Service layer for partner database configuration CRUD.

Stores encrypted credentials in the existing `console_partner_config` table
using key = 'partner_db_config'.  Only super-admin (internal) users can
create, read, or delete partner DB configs.
"""

from uuid import UUID
import json
from typing import Optional

from src.components.partner_config.constants import PartnerConfigEnum
from src.components.partner_config.models import PartnerConfig
from src.components.partner_config.repositories import PartnerConfigRepository
from src.components.partner_db_config.encryption import encrypt_value
from src.components.partner_db_config.schemas import (
    PartnerDBConfigRequest,
    PartnerDBConfigResponse,
)
from src.loggers.console_service_logger import ConsoleServiceLogger

class PartnerDBConfigService:

    CONFIG_KEY = PartnerConfigEnum.PARTNER_DB_CONFIG.value

    def __init__(
        self,
        partner_config_repository: PartnerConfigRepository,
        console_service_logger: ConsoleServiceLogger,
    ) -> None:
        self.__repo: PartnerConfigRepository = partner_config_repository
        self.__logger: ConsoleServiceLogger = console_service_logger

    # ------------------------------------------------------------------
    # CREATE / UPDATE
    # ------------------------------------------------------------------
    async def upsert_db_config(
        self,
        partner_id: UUID,
        config_data: PartnerDBConfigRequest,
        current_user_id: UUID,
    ) -> PartnerDBConfigResponse:
        """Encrypt the password and upsert the config row."""
        self.__logger.info(
            "Upserting partner DB config for partner_id={}".format(partner_id)
        )

        config_value = {
            "db_host": config_data.db_host,
            "db_port": config_data.db_port,
            "db_name": config_data.db_name,
            "db_user": config_data.db_user,
            "db_password": encrypt_value(config_data.db_password),
            "ssl_required": config_data.ssl_required,
        }

        await self.__repo.upsert_partner_config(
            current_user={
                "partner_id": partner_id,
                "user_id": current_user_id,
            },
            key=self.CONFIG_KEY,
            value=json.dumps(config_value),
        )

        self.__logger.info(
            "Partner DB config upserted for partner_id={}".format(partner_id)
        )
        return PartnerDBConfigResponse(
            partner_id=partner_id,
            db_host=config_data.db_host,
            db_port=config_data.db_port,
            db_name=config_data.db_name,
            db_user=config_data.db_user,
            db_password="********",
            ssl_required=config_data.ssl_required,
        )

    # ------------------------------------------------------------------
    # READ (masked — for console UI)
    # ------------------------------------------------------------------
    async def get_db_config(
        self, partner_id: UUID
    ) -> Optional[PartnerDBConfigResponse]:
        """Return partner DB config with password masked."""
        raw = await self._get_raw_config(partner_id)
        if raw is None:
            return None

        return PartnerDBConfigResponse(
            partner_id=partner_id,
            db_host=raw["db_host"],
            db_port=raw["db_port"],
            db_name=raw["db_name"],
            db_user=raw["db_user"],
            db_password="********",
            ssl_required=raw.get("ssl_required", True),
        )

    async def delete_db_config(self, partner_id: UUID) -> bool:
        """Soft-delete the partner DB config by setting is_active=False."""
        configs = await self.__repo.get_partner_config_by_key(
            partner_id, self.CONFIG_KEY
        )
        if not configs:
            return False
        await self.__repo.delete_partner_config_by_key(partner_id, self.CONFIG_KEY)
        self.__logger.info(
            "Soft-deleted partner DB config for partner_id={}".format(partner_id)
        )

        return True

    # ------------------------------------------------------------------
    # PRIVATE HELPERS
    # ------------------------------------------------------------------
    async def _get_raw_config(self, partner_id: UUID) -> Optional[dict]:
        """Fetch the raw JSON value from partner_config."""
        configs = await self.__repo.get_partner_config_by_key(
            partner_id, self.CONFIG_KEY
        )
        if not configs:
            return None

        config: PartnerConfig = configs[0] if isinstance(configs, list) else configs
        value = config.value

        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                self.__logger.error(
                    "Invalid JSON in partner DB config for partner_id={}".format(
                        partner_id
                    )
                )
                return None

        return value
