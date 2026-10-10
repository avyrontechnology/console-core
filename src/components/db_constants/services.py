from typing import List, Optional

from src.components.audit_log.schema import AuditLogSchema
from src.components.audit_log.services import AuditService
from src.components.common.actions import AuditActions
from src.components.common.resources import Resource
from src.components.db_constants import messages
from src.components.db_constants.enums import ConstantsTypes
from src.components.db_constants.loader.constant import DbConstants
from src.components.db_constants.models import (
    ConstantsBase,
    GlobalDynamicVariables,
    GlobalMediaConstants,
    MediaConstants,
)
from src.components.db_constants.repositories import ConstantsRepository
from src.components.db_constants.schema import (
    ConstantResponseSchema,
    NavbarMarqueeResponseSchema,
)
from src.components.digital_assets.services import DigitalAssetService
from src.components.digital_assets.storage.helper import StorageHelper
from src.exceptions import (
    ConstantNotFoundException,
    ConstantVersionException,
    ConstantVersionNotFoundException,
)
from src.loggers.console_service_logger import ConsoleServiceLogger


class ConstantsService:
    def __init__(
        self,
        constants_repository: ConstantsRepository,
        console_service_logger: ConsoleServiceLogger,
        audit_log_service: AuditService,
        digital_asset_service: DigitalAssetService,
    ) -> None:
        self.constants_repository: ConstantsRepository = constants_repository
        self.console_service_logger: ConsoleServiceLogger = console_service_logger
        self.audit_log_service: AuditService = audit_log_service
        self.digital_asset_service: DigitalAssetService = digital_asset_service

    async def get_constants_details(
        self, constant_model: type[ConstantsBase]
    ) -> List[ConstantResponseSchema]:
        """
        Retrieves constants from the repository .
        """
        try:
            constants: List[ConstantResponseSchema] = (
                await self.constants_repository.fetch_constant_by_type(constant_model)
            )
            if constant_model in [MediaConstants, GlobalMediaConstants]:
                for constant in constants:
                    constant.additional_info = {
                        key: (
                            StorageHelper.get_presigned_url(value)
                            if isinstance(value, str)
                            else value
                        )
                        for key, value in (constant.additional_info or {}).items()
                    }

                    constant.value = (
                        StorageHelper.get_presigned_url(constant.value)
                        if isinstance(constant.value, str)
                        else constant.value
                    )

            return constants

        except Exception as e:
            self.console_service_logger.error(
                "Unexpected error occured while fetching constants details in constants service: {}".format(
                    e
                )
            )
            raise e

    async def get_navbar_marquee_config(self) -> NavbarMarqueeResponseSchema:
        """
        Compose the navbar marquee enabled-flag and message into a single
        response for frontend consumption. Message is suppressed whenever
        the marquee is disabled (or not yet configured).
        """
        try:
            constants: List[ConstantResponseSchema] = (
                await self.get_constants_details(GlobalDynamicVariables)
            )
            values_by_name = {constant.name: constant.value for constant in constants}

            is_enabled: bool = str(
                values_by_name.get("NAVBAR_MARQUEE_ENABLED", "")
            ).strip().lower() == "true"

            message: Optional[str] = (
                values_by_name.get("NAVBAR_MARQUEE_MESSAGE") or None
                if is_enabled
                else None
            )

            return NavbarMarqueeResponseSchema(is_enabled=is_enabled, message=message)
        except Exception as e:
            self.console_service_logger.error(
                "Unexpected error occured while fetching navbar marquee config: {}".format(
                    e
                )
            )
            raise e

    async def get_constant_by_id(
        self, id: int, constant_model: type[ConstantsBase]
    ) -> List[ConstantResponseSchema]:
        """
        Fetch a constant by its ID.
        """
        return await self.constants_repository.get_constant_by_id(constant_model, id)

    async def update_constant(
        self,
        id: int,
        constant_model: type[ConstantsBase],
        value: str | object,
        is_media_type: bool,
        asset_type: str,
        user_id: int,
        description: Optional[str] = None,
    ) -> List[ConstantResponseSchema]:
        """
        Update the constant value, description, and increment version using the highest version in additional_info.
        """
        try:
            constant: List[ConstantResponseSchema] = (
                await self.constants_repository.get_constant_by_id(constant_model, id)
            )

            if is_media_type:
                digital_asset_response = (
                    await self.digital_asset_service.create_digital_asset(
                        partner_id=0,
                        asset_type=asset_type,
                        input_file=value,
                        user_id=user_id,
                    )
                )
                value: int = digital_asset_response.id

            additional_info: dict = constant.additional_info or {}
            description: Optional[str] = description or constant.description

            if not constant.value:
                version: int = 1
            else:
                version: int = (
                    self.get_highest_version(constant.additional_info, constant.version)
                    + 1
                )
                previous_version_key: str = f"version-{constant.version}"

                additional_info[previous_version_key] = constant.value

            version_keys: List[str] = [
                key for key in additional_info.keys() if key.startswith("version-")
            ]
            if len(version_keys) > DbConstants.VERSION_CAP:
                version_keys.sort(key=lambda key: int(key.split("-")[1]))
                key_to_remove: str = version_keys[0]
                del additional_info[key_to_remove]

            updated_constant = await self.constants_repository.update_constant(
                id=id,
                constant_model=constant_model,
                value=value,
                description=description,
                version=version,
                additional_info=additional_info,
                user_id=user_id,
            )

            log_entry = AuditLogSchema(
                action=AuditActions.update,
                resource=Resource.constant,
                resource_id=id,
                resource_previous_state=None,
                resource_current_state=None,
                performed_by=user_id,
                details="Updated constant with ID: {constant_id} for model type: {model_type}. New value: {new_value}, New version: {new_version}. Updated by user ID: {user_id}".format(
                    constant_id=id,
                    model_type=constant_model,
                    new_value=value,
                    new_version=version,
                    user_id=user_id,
                ),
            )
            await self.audit_log_service.log_action(log_entry)

            return updated_constant
        except Exception as e:
            self.console_service_logger.error(
                "Unexpected error occured while updating Constants: {}".format(e)
            )
            raise e

    def get_highest_version(self, additional_info: dict, current_version: int) -> int:
        """
        Fetch the highest version from the additional_info dictionary.
        """
        try:
            versions = []
            if additional_info:
                versions.extend(
                    int(key.split("-")[1])
                    for key in additional_info.keys()
                    if key.startswith("version-")
                )
            versions.append(current_version)

            return max(versions, default=0)
        except Exception as e:
            self.console_service_logger.error(
                "An error occured while getting highest version of constant: {}".format(
                    e
                )
            )
            raise e

    async def rollback_constant(
        self, id: int, target_version: int, constant_type: ConstantsTypes, user_id: int
    ) -> List[ConstantResponseSchema]:
        """
        Rollback the constant to the specified version. This will update the constant's value and version.
        """
        try:
            constant_model: type[ConstantsBase] = ConstantsTypes.get_db_constant_model(
                constant_type.value
            )

            constant: List[ConstantResponseSchema] = await self.get_constant_by_id(
                id, constant_model
            )
            if not constant:
                self.console_service_logger.error(
                    "Constant with ID {} not found.".format(id)
                )
                raise ConstantNotFoundException(messages.CONSTANT_NOT_FOUND.format(id))

            if not constant.additional_info:
                self.console_service_logger.error(
                    "Constant with ID {} has no previous versions.".format(id)
                )
                raise ConstantVersionNotFoundException(
                    messages.CONSTANT_NO_PREVIOUS_VERSIONS.format(id)
                )

            if constant.version == target_version:
                self.console_service_logger.error(
                    "Constant with ID {} is already on version {}.".format(
                        id, target_version
                    )
                )
                raise ConstantVersionException(
                    messages.CONSTANT_ALREADY_ON_VERSION.format(id, target_version)
                )

            version_key = "version-{0}".format(target_version)
            if version_key not in constant.additional_info:
                self.console_service_logger.error(
                    "Version {} not found in additional_info for Constant ID {}.".format(
                        target_version, id
                    )
                )
                raise ConstantVersionNotFoundException(
                    messages.VERSION_NOT_FOUND_IN_ADDITIONAL_INFO.format(target_version)
                )

            previous_value = constant.additional_info[version_key]

            current_version_key = f"version-{constant.version}"
            if current_version_key not in constant.additional_info:
                constant.additional_info[current_version_key] = constant.value

            updated_constant = await self.constants_repository.rollback_version(
                id=id,
                constant_model=constant_model,
                value=previous_value,
                version=target_version,
                user_id=user_id,
                additional_info=constant.additional_info,
            )

            log_entry = AuditLogSchema(
                action=AuditActions.update,
                resource=Resource.constant,
                resource_id=id,
                resource_previous_state=None,
                resource_current_state=None,
                performed_by=user_id,
                details="rolled back constant to a previous version with ID: {} for model type: {}. New value: {}, New version: {}. Updated by user ID: {}".format(
                    id, constant_model, previous_value, target_version, user_id
                ),
            )
            await self.audit_log_service.log_action(log_entry)

            return updated_constant
        except Exception as e:
            self.console_service_logger.error(
                "An error occured while rollback constant: {}".format(e)
            )
            raise e
