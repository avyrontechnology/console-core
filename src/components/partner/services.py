from uuid import UUID
import copy
import json
from typing import Any, List, Optional

from dependency_injector.wiring import Provide
from fastapi import Depends, Request
from sqlalchemy.exc import IntegrityError

from src.components.audit_log.schema import AuditLogSchema
from src.components.audit_log.services import AuditService
from src.components.auth.models import Role
from src.components.auth.schema import LoginData
from src.components.cache import Keys as CacheKeys
from src.components.cache.helper import CacheHelper
from src.components.common.actions import AuditActions
from src.components.common.constants import CurrentUserMap
from src.components.common.datetime import DateTimeUtil
from src.components.common.resources import Resource
from src.components.partner.constant import (
    PartnerResponseData,
    PartnerStatus,
    TrialPartnerConstant,
)
from src.components.partner.error import PartnerNotFoundError
from src.components.partner.models import Partner
from src.components.partner.partner_filter_service import PartnerFilterService
from src.components.partner.repositories import PartnerRepository
from src.components.partner.schema import (
    ApiKeyOnboarding,
    BasePartnerData,
    ChangePartnerStatusResponse,
    PartnerDetails,
    PartnerFilterRequest,
    PartnerMetaDataDetails,
    PartnerOnboardingDetails,
    PartnerOnboardingResponse,
    TogglePartnerActivation,
    TogglePartnerActivationResponse,
    UpdatePartnerRequest,
    UserDetails,
)
from src.components.session_mangement.services import UserSessionService
from src.components.user.services import UserService
from src.components.wallet.errors import WalletAlreadyExistsError
from src.components.wallet.services import WalletService
from src.core.redis import RedisCache
from src.exceptions import (
    AuthException,
    PartnerException,
    PartnerStatusUnchangedException,
)
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerService:

    def __init__(
        self,
        partner_repository: PartnerRepository,
        audit_service: AuditService,
        console_service_logger: ConsoleServiceLogger,
        partner_service_cache: CacheHelper,
    ) -> None:
        self.__repository: PartnerRepository = partner_repository
        self.__audit_service: AuditService = audit_service
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger
        self.__partner_service_cache: CacheHelper = partner_service_cache

    async def enlist_partners_dynamically(
        self,
        current_user: dict,
        filter_request: PartnerFilterRequest,
        user_service: UserService = Depends(Provide["console_service"]),
        partner_filter_service: PartnerFilterService = Depends(
            Provide["partner_filter_service"]
        ),
    ) -> dict[str, Any]:
        try:
            user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            if not await user_service.is_user_internal(user_id):
                raise AuthException()
            self.__console_service_logger.info("Getting all partners from database.")
            response = await partner_filter_service.enlist_partners_dynamically(
                filter_request=filter_request
            )
            return response
        except PartnerException as exec:
            self.__console_service_logger.error(
                "Partner exception occured while fetching partners: {}".format(exec)
            )
            raise exec
        except Exception as ex:
            self.__console_service_logger.error(
                "Error while getting all partners: {}".format(str(ex))
            )
            raise ex

    async def get_partner_by_id(self, partner_id: UUID) -> Partner:
        try:
            self.__console_service_logger.info(
                "Getting the partner with id :{} ".format(partner_id)
            )
            partner_by_id = await self.__repository.get_by_id(partner_id)
            self.__console_service_logger.info(
                "Fetched partner successfully : {} ".format(partner_by_id)
            )
            return partner_by_id
        except PartnerNotFoundError as ex:
            self.__console_service_logger.error(
                "Error while getting Partner: {}".format(
                    "Partner not found, id: {}".format(partner_id)
                )
            )
            raise PartnerException(str(ex))
        except Exception as ex:
            self.__console_service_logger.error(
                "Error while getting Partner: {}".format(str(ex))
            )
            raise ex

    async def create_partner(
        self,
        partner_data: BasePartnerData,
        wallet_service: WalletService = Depends(Provide["wallet_service"]),
        api_key_service=Depends(Provide["api_key_service"]),
    ) -> Partner:
        try:
            self.__console_service_logger.info(
                "Received the partner data : {}".format(partner_data)
            )

            created_partner: Partner = await self.__repository.add_partner(
                partner_data=partner_data,
            )

            self.__console_service_logger.info(
                "Partner created successfully : {}".format(created_partner)
            )

            try:
                await wallet_service.create_wallet(created_partner.id)
            except WalletAlreadyExistsError:
                pass

            # Generate API key ONLY for non-free-trial partner
            if not partner_data.is_free_trail_enabled:
                await api_key_service.generated_api_key_while_partner_onboarding(
                    created_partner.id
                )

            log_entry: AuditLogSchema = AuditLogSchema(
                action=AuditActions.create,
                resource=Resource.partner,
                resource_id=created_partner.id,
                resource_previous_state=None,
                resource_current_state=str(partner_data),
                details="Partner created with name {}".format(partner_data.name),
            )

            await self.__audit_service.log_action(log_entry)

            return created_partner

        except IntegrityError as ex:
            error_message = str(ex.orig) if hasattr(ex, "orig") else str(ex)

            if "console_partners_gst_no_key" in error_message:
                raise PartnerException("GST number already exists.")
            elif "console_partners_cin_no_key" in error_message:
                raise PartnerException("cin number already exists.")

        except PartnerException as ex:
            self.__console_service_logger.error(
                "IntegrityError while creating partner: {}".format(str(ex))
            )
            raise ex

        except Exception as ex:
            self.__console_service_logger.error(
                "Error while creating Partner: {}".format(str(ex))
            )
            raise ex

    async def delete_partner_by_id(self, partner_id: UUID, current_user: dict) -> None:
        try:

            self.__console_service_logger.info(
                "Deleting partner with id : {}".format(partner_id)
            )
            user_id = current_user.get(CurrentUserMap.USER_ID)
            deleted_partner = await self.__repository.delete_by_id(partner_id, user_id)
            self.__console_service_logger.info(
                "Partner with id {} deleted successfully.".format(partner_id)
            )
            log_entry = AuditLogSchema(
                action=AuditActions.delete,
                resource=Resource.partner,
                resource_id=partner_id,
                resource_previous_state=None,
                resource_current_state=None,
                performed_by=user_id,
                details="The partner with id {} is now deleted from the database.".format(
                    partner_id
                ),
            )
            await self.__audit_service.log_action(log_entry)

            return deleted_partner
        except PartnerNotFoundError as ex:
            self.__console_service_logger.error(
                "Error while delete Partner: {}".format(
                    "Partner not found, id: {}".format(partner_id)
                )
            )
            raise PartnerException(str(ex))
        except Exception as ex:
            self.__console_service_logger.error(
                "Error while delete Partner: {}".format(str(ex))
            )
            raise ex

    async def update_partner(
        self, partner_id: UUID, partner_data: UpdatePartnerRequest, current_user: dict
    ) -> Partner:
        try:
            user_id = current_user.get(CurrentUserMap.USER_ID)
            existing_partner = await self.__repository.get_by_id(partner_id)
            resource_previous_state = copy.deepcopy(existing_partner)
            self.__console_service_logger.info(
                "Received update request for partner id {} with data: {}".format(
                    partner_id, partner_data
                )
            )

            updated_partner = await self.__repository.update(
                user_id=user_id, partner_id=partner_id, partner_data=partner_data
            )
            self.__console_service_logger.info(
                "Partner updated successfully: {}".format(updated_partner)
            )
            updated_partner_response = await self.__repository.get_by_id(
                updated_partner.id
            )
            resource_previous_state_json = json.dumps(
                resource_previous_state.__dict__, default=str
            )
            resource_current_state_json = json.dumps(
                updated_partner_response.__dict__, default=str
            )
            log_entry = AuditLogSchema(
                action=AuditActions.update,
                resource=Resource.partner,
                resource_id=partner_id,
                resource_previous_state=resource_previous_state_json,
                resource_current_state=resource_current_state_json,
                performed_by=user_id,
                details="The partner with id {} is now updated".format(partner_id),
            )
            await self.__audit_service.log_action(log_entry)

            return updated_partner_response

        except PartnerNotFoundError as exec:
            self.__console_service_logger.error(
                "duplicate partner: {}".format(str(exec))
            )
            raise exec

        except IntegrityError as ex:
            self.__console_service_logger.error(
                "IntegrityError while creating partner: {}".format(str(ex))
            )
            raise PartnerException(str(ex))

        except Exception as ex:
            self.__console_service_logger.error(
                "Error while update Partner: {}".format(str(ex))
            )
            raise ex

    def get_partner_statuses(self) -> List[str]:
        """
        Retrieve the list of all partner statuses.

        Returns:
            List[str]: A list of all possible partner statuses.
        """
        self.__console_service_logger.info("Fetching partner statuses")
        try:
            statuses = PartnerStatus.choices()
            self.__console_service_logger.info(
                f"Retrieved {len(statuses)} partner statuses"
            )
            return statuses
        except Exception as exc:
            self.__console_service_logger.error(
                f"Error fetching partner statuses: {exc}"
            )
            raise

    async def change_partner_status(
        self,
        partner_id: UUID,
        status: Optional[str],
        is_feedback_enabled: Optional[bool],
    ) -> ChangePartnerStatusResponse:
        """
        Change the status and/or is_feedback_enabled flag of a partner.

        Args:
            partner_id: ID of the partner to update.
            status: New status for the partner (optional, must be in PartnerStatus.choices() if provided).
            is_feedback_enabled: New value for the is_feedback_enabled flag (optional).

        Returns:
            ChangePartnerStatusResponse: Updated partner details.

        Raises:
            ValueError: If the partner_id is invalid or not found.
        """
        self.__console_service_logger.info(
            f"Processing status change for partner_id={partner_id}, status={status}, is_feedback_enabled={is_feedback_enabled}"
        )
        try:
            current_partner = await self.__repository.get_by_id(partner_id)
            if not current_partner:
                raise PartnerNotFoundError(partner_id)

            if (status in (None, current_partner.partner_status)) and (
                is_feedback_enabled in (None, current_partner.is_feedback_enabled)
            ):
                self.__console_service_logger.info(
                    f"No update needed for partner_id={partner_id}: status and is_feedback_enabled unchanged"
                )
                raise PartnerStatusUnchangedException(partner_id)

            updated_partner = await self.__repository.change_partner_status(
                partner_id, status, is_feedback_enabled
            )
            if not updated_partner:
                raise ValueError(f"Partner with id={partner_id} not found or inactive")

            self.__console_service_logger.info(
                f"Successfully updated partner_id={partner_id}"
            )

            return ChangePartnerStatusResponse(
                id=updated_partner.id,
                name=updated_partner.name,
                partner_status=updated_partner.partner_status,
                is_feedback_enabled=updated_partner.is_feedback_enabled,
            )
        except PartnerStatusUnchangedException as psuex:
            self.__console_service_logger.error(
                "Partner: {} remians unchanged".format(partner_id)
            )
            raise psuex
        except PartnerNotFoundError as ex:
            self.__console_service_logger.error(
                "Error while changing status of Partner: {}".format(
                    "Partner not found, id: {}".format(partner_id)
                )
            )
            raise PartnerException(str(ex))
        except Exception as exc:
            self.__console_service_logger.error(
                f"Error changing partner status for partner_id={partner_id}: {exc}"
            )
            raise

    async def onboard_partner(
        self,
        request: Request,
        partner_data: PartnerOnboardingDetails,
        auth_service=Depends(Provide["auth_service"]),
        auth_service_utility=Depends(Provide["auth_service_utility"]),
        wallet_service: WalletService = Depends(Provide["wallet_service"]),
    ) -> PartnerOnboardingResponse:
        try:
            self.__console_service_logger.info(
                "Attempting to onboarding free trial partner with details : {}".format(
                    partner_data.partner_details
                )
            )

            user_details: UserDetails = partner_data.user_details
            partner_meta_data_details: PartnerMetaDataDetails = (
                partner_data.partner_meta_data
            )
            partner_details: PartnerDetails = partner_data.partner_details

            # check partner is eligible for free trial
            await self.check_partner_free_trial_eligible(partner_data)

            # convert plainpassword to hash password
            user_details.hashed_password = await auth_service_utility.get_password_hash(
                user_details.password
            )

            # get role admin role details
            role_details: Role = await auth_service.get_role_by_hierarchy(1)
            user_details.role_id = role_details.id
            user_details.designation = "Admin"

            #  set free trial expiry time for allowed services
            self.set_trial_expiry_time_and_allow_services(
                partner_meta_data_details, user_details
            )

            created_partner: Partner = await self.__repository.onboard_partner(
                partner_data=partner_data,
            )
            self.__console_service_logger.info(
                "Partner created successfully : {}".format(created_partner)
            )

            try:
                await wallet_service.create_wallet(created_partner.id)
            except WalletAlreadyExistsError:
                pass

            log_entry: AuditLogSchema = AuditLogSchema(
                action=AuditActions.create,
                resource=Resource.partner,
                resource_id=created_partner.id,
                resource_previous_state=None,
                resource_current_state=str(partner_details),
                details="Partner created with name {}".format(partner_details.name),
            )
            await self.__audit_service.log_action(log_entry)
            # get user login token
            user_credential = LoginData(
                credential=user_details.email, password=user_details.password
            )
            user_login_token = await auth_service.get_token(request, user_credential)
            response = PartnerOnboardingResponse.model_validate(created_partner)
            response.user_login_token = user_login_token
            return response
        except PartnerException as exc:
            self.__console_service_logger.error(
                "Error occurred onboarding free trial partner, error: {}".format(
                    str(exc)
                )
            )
            raise exc
        except Exception as ex:
            self.__console_service_logger.error(
                "Error while creating Partner: {}".format(str(ex))
            )
            raise ex

    def set_trial_expiry_time_and_allow_services(
        self,
        partner_meta_data_details: PartnerMetaDataDetails,
        user_details: UserDetails,
    ) -> None:

        expiry_time_ms: int = int(
            DateTimeUtil.get_current_time()
            + (TrialPartnerConstant.TRIAL_PERIOD_DAYS * 24 * 60 * 60 * 1000)
        )
        if partner_meta_data_details.is_talko_free_trial__enabled:
            partner_meta_data_details.talko_trail_expiry_time = expiry_time_ms
            user_details.is_talko_enabled = True

    async def check_partner_free_trial_eligible(
        self, partner_data: PartnerOnboardingDetails
    ) -> bool:
        try:
            self.__console_service_logger.info(
                "Attempting to check partner is eligible"
            )
            response: bool = await self.__repository.check_partner_free_trial_eligible(
                partner_data
            )
            return response
        except PartnerException as exc:
            self.__console_service_logger.error(
                "Error occurred while checking partner eligibility, error: {}".format(
                    str(exc)
                )
            )
            raise exc
        except Exception as exc:
            self.__console_service_logger.error(
                "Unexpected error occurred while checking partner eligibility, error: {}".format(
                    str(exc)
                )
            )
            raise exc

    async def toggle_partner_activation(
        self,
        current_user: dict,
        partner_id: UUID,
        partner_data: TogglePartnerActivation,
        user_service: UserService = Depends(Provide["console_service"]),
        user_session_service: UserSessionService = Depends(
            Provide["user_session_service"]
        ),
    ):
        try:
            self.__console_service_logger.info(
                "Trying to update the partner active status for id: {}".format(
                    partner_id
                )
            )
            current_user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            if not await user_service.is_user_internal(current_user_id):
                self.__console_service_logger.error(
                    "Only internal team members can change the active status of partners"
                )
                raise PartnerException(
                    PartnerResponseData.CHANGE_PARTNER_STATUS_VALIDATION
                )
            is_active, users = await self.__repository.toggle_partner_activation(
                partner_id=partner_id, partner_data=partner_data
            )
            if not is_active:
                self.__console_service_logger.info(
                    "partner is deactivated, making all user's session false for partner id: {}".format(
                        partner_id
                    )
                )
                user_ids = [value.get("id") for value in users]
                await user_session_service.deactivate_user_sessions(user_ids)
                self.__console_service_logger.info(
                    "All the user's session associated with current partner id: {} is deactivated successfully".format(
                        partner_id
                    )
                )
            await self.__partner_service_cache.clear_pattern(
                prefix=RedisCache.KeysPrefix.CONSOLE,
                pattern=CacheKeys.TOKEN.format(partner_id, ""),
            )
            response = TogglePartnerActivationResponse(is_active=is_active)
            return response
        except PartnerNotFoundError as exec:
            self.__console_service_logger.error(
                "Partner not found error: {}".format(exec)
            )
            raise exec
        except PartnerException as exec:
            self.__console_service_logger.error(
                "Partner exception occured: {}".format(exec)
            )
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "An unexpected error occured while updating the partner active status: {}".format(
                    exec
                )
            )
            raise exec
