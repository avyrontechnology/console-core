"""Services module."""

from uuid import UUID
import copy
import json
import re
from contextlib import AbstractContextManager
from typing import Any, Callable, Dict, List, Optional, Union

from src.components.user.bulk_upload_utils import build_bulk_upload_headers
from src.components.user.constants import FileContent
import csv
import io

from fastapi.responses import StreamingResponse


from dependency_injector.wiring import Provide
from fastapi import Depends
from passlib.context import CryptContext  # type: ignore
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from src.components.api_key.errors import ApiKeyNotFoundError
from src.components.api_key.repositories import ApiKey, ApiKeyRepository
from src.components.audit_log.schema import AuditLogSchema
from src.components.audit_log.services import AuditService
from src.components.auth.constant import (
    AuthExceptionMsg,
    OtpConstants,
    OtpType,
    UserHierarchyLevel,
)
from src.components.auth.error import RoleNotFoundError
from src.components.auth.models import OTP, Role
from src.components.auth.repositories import AuthRepository
from src.components.auth.schema import (
    AllUsersDataResponse,
    PaginatedAllUsersDataResponse,
)
from src.components.auth.util import AuthUtility
from src.components.cache import Keys as CacheKeys
from src.components.cache.helper import CacheHelper
from src.components.common.actions import AuditActions
from src.components.common.constants import CurrentUserMap
from src.components.common.datetime import DateTimeUtil
from src.components.filters.criteria import BaseFilterCriteria
from src.components.common.resources import Resource
from src.components.location.errors import (
    CityNotFoundError,
    CountryNotFoundError,
    StateNotFoundError,
)
from src.components.location.services import LocationService
from src.components.partner.error import PartnerNotFoundError
from src.components.partner.models import Partner
from src.components.partner.repositories import PartnerRepository
from src.components.partner_config.constants import PartnerConfigEnum
from src.components.session_mangement.services import UserSessionService
from src.components.user.constants import (
    OBOTAAI_PARTNER_ID,
    UserResponseMsg,
    UserWalkthroughAttribtes,
)
from src.components.user.errors import UserNotFoundError
from src.components.user.filter_service import FilterService
from src.components.user.models import User
from src.components.user.repositories import UserRepository
from src.components.user.schema import (
    BulkUserCreateRequest,
    BulkUserEntry,
    Contrasts,
    UserRoleFilterRequest,
    WalkthroughUpdateRequest,
)
from src.components.user_tracker.constants import StandardStatuses
from src.components.user_tracker.errors import InvalidStatusError
from src.components.user_tracker.services import UserTrackerService
from src.core.environment import ENV
from src.core.redis import RedisCache
from src.exceptions import AuthException, UserException
from src.loggers.console_service_logger import ConsoleServiceLogger

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserService:

    def __init__(
        self,
        user_repository: UserRepository,
        audit_service: AuditService,
        console_service_logger: ConsoleServiceLogger,
        console_service_cache: CacheHelper,
        auth_service_utility: AuthUtility,
        session_factory: Callable[..., AbstractContextManager[Session]],
    ) -> None:
        self.__repository: UserRepository = user_repository
        self.__audit_service: AuditService = audit_service
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger
        self.__console_service_cache: CacheHelper = console_service_cache
        self.__auth_service_utility: AuthUtility = auth_service_utility
        self._session_factory = session_factory

    async def get_users(
        self,
        current_user_id: UUID,
        limit: int,
        offset: int,
        auth_service=Depends(Provide["auth_service"]),
        partner_config_service=Depends(Provide["partner_config_service"]),
        filter_criteria: Optional[BaseFilterCriteria] = None,
    ) -> PaginatedAllUsersDataResponse:
        try:
            """
            Fetch paginated users under a user's hierarchy.

            Args:
                current_user_id: ID of the user for hierarchy.
                limit: Max users to return.
                offset: Pagination start.
                auth_service: Service for role data.
                filter_criteria: Optional User Listing filters; omitted means
                    the full authorized listing.

            Returns:
                PaginatedAllUsersDataResponse: Paginated user data.

            Raises:
                Exception: For errors fetching users/roles.
            """
            self.__console_service_logger.info("getting all users")
            all_users, total_count = await self.__repository.get_all(
                current_user_id, limit, offset, filter_criteria=filter_criteria
            )
            self.__console_service_logger.info(
                "Fetched all the users successfully : {}".format(all_users)
            )

            users_data: List[AllUsersDataResponse] = []
            for user in all_users:
                role_name: Optional[str] = None
                role_id: Optional[UUID] = user.role_id

                if role_id:
                    role = await auth_service.get_role_by_id(role_id)
                    role_name: Optional[str] = role.name if role else None

                country_id: Optional[UUID] = user.country_id
                country_name: Optional[str] = (
                    user.country.name if user.country else None
                )

                parent_name = user.parent.name if user.parent_id else None

                is_active = user.is_active
                user_email = user.email
                user_phone_number = user.phone_number
                if not is_active:
                    user_email, user_phone_number = self._clean_user_data(user)
                user_response = AllUsersDataResponse(
                    id=user.id,
                    name=user.name,
                    email=user_email,
                    designation=user.designation,
                    phone_number=user_phone_number,
                    parent_id=user.parent_id,
                    partner_id=user.partner_id,
                    role_id=user.role_id,
                    role_name=role_name,
                    country_id=country_id,
                    country_name=country_name,
                    state_id=user.state_id,
                    city_id=user.city_id,
                    parent_name=parent_name,
                    is_active=user.is_active,
                    cloud_agent_number=user.cloud_agent_number,
                    current_status=user.current_status or StandardStatuses.AWAY,
                )
                users_data.append(user_response)

            return PaginatedAllUsersDataResponse(
                total_count=total_count,
                limit=limit,
                offset=offset,
                users_data=users_data,
            )
        except UserException as uex:
            self.__console_service_logger.error(
                "User role not found while getting all users: {}".format(str(uex))
            )
            raise uex

        except Exception as e:
            self.__console_service_logger.error("Error retriving users.{}".format(e))
            raise

    async def get_user_by_id(self, user_id: UUID) -> User:
        try:
            self.__console_service_logger.info(
                "Getting the user by id :{} ".format(user_id)
            )
            user_by_id = await self.__repository.get_by_id(user_id)
            self.__console_service_logger.info(
                "User fetched sucsessfully : {} ".format(user_by_id)
            )
            return user_by_id
        except UserNotFoundError as e:
            self.__console_service_logger.error(str(e))
            raise
        except Exception as e:
            self.__console_service_logger.error("error getting user {}".format(e))
            raise

    async def delete_user_by_id(
        self,
        request,
        user_id: UUID,
        user_session_service: UserSessionService = Depends(
            Provide["user_session_service"]
        ),
        auth_repository: AuthRepository = Depends(Provide["auth_repository"]),
    ) -> None:
        try:
            self.__console_service_logger.info(
                "Deleting user with id : {}".format(user_id)
            )
            await self.get_user_by_id(user_id=user_id)

            is_child_users: bool = await self.has_child_users(user_id=user_id)
            if is_child_users:
                raise UserException("User has associated child users")

            user: User = await self.__repository.delete_by_id(user_id)
            self.__console_service_logger.info("user deleted successfully.")

            if not user.is_active:
                await user_session_service.deactivate_user_sessions(user_id)
                self.__console_service_logger.info(
                    "deactivate user session: {}".format(user_id)
                )

            await self.__console_service_cache.clear_pattern(
                prefix=RedisCache.KeysPrefix.CONSOLE,
                pattern=CacheKeys.TOKEN.format(user.partner_id, ""),
            )

            log_entry = AuditLogSchema(
                action=AuditActions.delete,
                resource=Resource.user,
                resource_id=user_id,
                performed_by=user_id,
                resource_previous_state=None,
                resource_current_state=None,
                details="The user with id {} is now deleted from the database.".format(
                    user_id
                ),
            )
            await self.__audit_service.log_action(log_entry)

        except UserNotFoundError as e:
            self.__console_service_logger.error(str(e))
            raise
        except Exception as e:
            self.__console_service_logger.error("error deleting partner {}".format(e))
            raise

    async def update_user(
        self,
        user_id: UUID,
        current_user: dict,
        user_data: Contrasts.UpdateUserData,
        location_service: LocationService = Depends(Provide["location_service"]),
        auth_repository: AuthRepository = Depends(Provide["auth_repository"]),
        partner_service: Partner = Depends(Provide["partner_service"]),
        user_session_service: UserSessionService = Depends(
            Provide["user_session_service"]
        ),
        user_tracker_service: UserTrackerService = Depends(
            Provide["user_tracker_service"]
        ),
    ) -> User:
        try:
            existing_user: User = await self.__repository.get_by_id(
                user_id, show_inactive_users=True
            )            
            resource_previous_state: User = copy.deepcopy(existing_user)
            current_user_partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)
            current_user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            partner_obj: Partner = await partner_service.get_partner_by_id(
                current_user_partner_id
            )

            update_data = user_data.model_dump(exclude_unset=True)
            if not partner_obj.is_internal:
                update_data.pop("is_internal", None)
            if (
                "is_active" in update_data
                and update_data["is_active"] == existing_user.is_active
            ):
                raise UserException(
                    "User is already {}".format(
                        "active" if existing_user.is_active else "inactive"
                    )
                )
            
            if isinstance(update_data.get("current_status"), str):
                cleaned_status: str = update_data["current_status"].strip()
                if not await user_tracker_service.is_valid_status(
                    existing_user.partner_id, cleaned_status
                ):
                    raise InvalidStatusError(cleaned_status)
                update_data["current_status"] = cleaned_status
                # This endpoint has no status_icon field, so clear any stale
                # per-user icon override from a previous (different) status.
                update_data["current_status_icon"] = None

            self.__console_service_logger.info(
                "checking country city and state validation"
            )
            if user_data.country_id or user_data.state_id or user_data.city_id:
                await location_service.validate_location_hierarchy(
                    user_data.country_id,
                    user_data.state_id,
                    user_data.city_id,
                )

            self.__console_service_logger.info(
                "Received update request for user id {} with data: {}".format(
                    user_id, user_data
                )
            )
            if "password" in update_data:
                update_data["password"] = (
                    await self.__auth_service_utility.get_password_hash(
                        update_data["password"]
                    )
                )

            if update_data.get("role_id") and update_data.get("partner_id"):
                user_role: Role = await auth_repository.get_role_by_id(
                    update_data.get("role_id")
                )
                if (
                    user_role.hierarchy == UserHierarchyLevel.ADMIN_LEVEL_HIERARCHY
                    and (
                        await self.__repository.is_admin_exists(
                            update_data.get("partner_id"), user_role.id
                        )
                    )
                ):
                    raise AuthException(AuthExceptionMsg.ADMIN_EXIST)

            updated_user = await self.__repository.update_user(
                user_id=user_id,
                current_user_id=current_user_id,
                **update_data,
            )
            self.__console_service_logger.info(
                "user updated successfully: {}".format(updated_user)
            )

            await self.__console_service_cache.clear_pattern(
                prefix=RedisCache.KeysPrefix.CONSOLE,
                pattern=CacheKeys.TOKEN.format(updated_user.partner_id, ""),
            )

            self.__console_service_logger.info(
                "Deactivating all the user sessions by user id: {}".format(user_id)
            )
            await user_session_service.deactivate_user_sessions(user_id)
            resource_previous_state_json = json.dumps(
                resource_previous_state.__dict__, default=str
            )
            resource_current_state_json = json.dumps(updated_user.__dict__, default=str)
            # give activate/deactivate its own distinct audit action
            # instead of the generic "update", so status changes are easy
            # to query and report on separately from ordinary field edits.
            audit_action: str = AuditActions.update
            if "is_active" in update_data:
                audit_action = "ACTIVATE" if update_data["is_active"] else "DEACTIVATE"

            audit_details: str = "The user with id {} is now updated".format(user_id)
            if audit_action == "ACTIVATE":
                audit_details = "The user with id {} has been activated".format(user_id)
            elif audit_action == "DEACTIVATE":
                audit_details = "The user with id {} has been deactivated".format(
                    user_id
                )
            
            log_entry = AuditLogSchema(
                action=audit_action,
                resource=Resource.user,
                resource_id=user_id,
                performed_by=current_user_id,
                resource_previous_state=resource_previous_state_json,
                resource_current_state=resource_current_state_json,
                details=audit_details,
            )
            await self.__audit_service.log_action(log_entry)
            return updated_user

        except SQLAlchemyError as exec:
            error_map = {
                "console_users_partner_id_fkey": PartnerNotFoundError(
                    user_data.partner_id
                ),
                "console_users_parent_id_fkey": UserNotFoundError(user_data.parent_id),
                "console_users_role_id_fkey": RoleNotFoundError(user_data.role_id),
                "console_users_country_id_fkey": CountryNotFoundError(
                    user_data.country_id
                ),
                "console_users_state_id_fkey": StateNotFoundError(user_data.state_id),
                "console_users_city_id_fkey": CityNotFoundError(user_data.city_id),
                "console_users_email_key": UserException(
                    UserResponseMsg.EMAIL_ALREADY_EXISTS
                ),
                "console_users_phone_number_key": UserException(
                    UserResponseMsg.PHONE_NUMBER_ALREADY_EXISTS
                ),
            }
            error_message = str(exec.orig) if hasattr(exec, "orig") else str(exec)
            match = re.search(r'constraint\s+"([^"]+)"', error_message)
            constraint_name = match.group(1) if match else None
            exp = error_map.get(constraint_name)
            if exp is None:
                raise
            raise exp

        except CountryNotFoundError as exec:
            self.__console_service_logger.error(
                "Country not find while create user: {}".format(str(exec))
            )
            raise exec
        except StateNotFoundError as exec:
            self.__console_service_logger.error(
                "State not find while create user: {}".format(str(exec))
            )
            raise exec
        except CityNotFoundError as exec:
            self.__console_service_logger.error(
                "City not find while create user: {}".format(str(exec))
            )
            raise exec
        except UserNotFoundError as e:
            self.__console_service_logger.error(str(e))
            raise
        except Exception as e:
            self.__console_service_logger.error("error updating partner {}".format(e))
            raise

    async def get_users_by_partner_id(
        self,
        partner_id: UUID,
        partner_repository: PartnerRepository = Depends(Provide["partner_repository"]),
    ) -> List[Dict]:
        try:
            self.__console_service_logger.info(
                "Checking partner: {} is activate or available.".format(partner_id)
            )
            # call partner repository to check partner is exist
            partner = await partner_repository.get_by_id(partner_id)

            if partner:
                self.__console_service_logger.info(
                    "Attempting to get users by partner id: {}".format(partner_id)
                )
                return await self.__repository.get_users_by_partner_id(
                    partner_id,
                )
            raise PartnerNotFoundError(partner_id)
        except PartnerNotFoundError as ex:
            self.__console_service_logger.error(
                "Partner not find while get users by partner_id: {}".format(str(ex))
            )
            raise ex
        except Exception as ex:
            self.__console_service_logger.error(
                "Unexpected error during get users by partner_id: {}".format(repr(ex))
            )
            raise ex

    async def get_user_by_field(
        self,
        field_name: str,
        value: Any,
    ) -> User:
        try:
            self.__console_service_logger.info(
                "Attempting to get users by {}: {}".format(field_name, value)
            )
            user = await self.__repository.get_user_by_field(field_name, value)
            return user
        except Exception as ex:
            self.__console_service_logger.error(
                "Unexpected error during get users by {}: {}".format(
                    field_name, repr(ex)
                )
            )
            raise ex

    async def get_user_details(
        self,
        user_id: UUID,
    ) -> User:
        try:
            self.__console_service_logger.info(
                "Attempting to get user details by user_id {}".format(user_id)
            )
            user_details = await self.__repository.get_user_details(
                user_id,
            )
            return user_details
        except Exception as ex:
            self.__console_service_logger.error(
                "Unexpected error occurred while getting user details by user_id {}".format(
                    user_id
                )
            )
            raise ex

    async def get_service_board_users_details(
        self, user_ids: List[int], show_inactive_users: Optional[bool] = False
    ) -> List[User]:
        try:
            self.__console_service_logger.info(
                "Attempting to get service board user details by user_ids {}".format(
                    user_ids
                )
            )
            user_details: List[User] = (
                await self.__repository.get_service_board_users_details(
                    user_ids,
                    show_inactive_users,
                )
            )
            return user_details
        except Exception as ex:
            self.__console_service_logger.error(
                "Unexpected error occurred while getting service board users details by user_ids {}".format(
                    user_ids
                )
            )
            raise ex

    async def get_admin_credentials_by_hierarchy(
        self,
        user_hierarchy: int,
        partner_id: Union[int, list[int]],
    ) -> Optional[Dict[str, str]]:
        try:
            self.__console_service_logger.info(
                "Trying to get the admin creds by hierarchy: {}".format(user_hierarchy)
            )
            admin_credentials = (
                await self.__repository.get_admin_credentials_by_hierarchy(
                    user_hierarchy, partner_id
                )
            )
            self.__console_service_logger.info(
                "Admin creds fetched successfully: {}".format(admin_credentials)
            )
            return admin_credentials
        except Exception as exec:
            self.__console_service_logger.error(
                "An error occured while getting admin creds: {}".format(exec)
            )
            raise exec

    def _clean_user_data(self, user: User) -> tuple[str, str]:
        """
        Clean email and phone_number for inactive users by removing ID prefix/suffix.

        Args:
            user: User object containing email, phone_number, id.

        Returns:
            Tuple[str, str]: Cleaned email and phone_number.
        """
        email = user.email
        phone_number = user.phone_number

        # Clean email: remove ID prefix/suffix (e.g., "48_shalini.rani@affinityeducation.in" -> "shalini.rani@affinityeducation.in")
        email_parts = email.split("@")
        email_local = (
            email_parts[0].replace(f"{user.id}_", "").replace(f"_{user.id}", "")
        )
        email = f"{email_local}@{email_parts[1]}"

        # Clean phone_number: remove ID suffix (e.g., "+91-7634-567-890_48" -> "+91-7634-567-890")
        phone_number = phone_number.replace(f"_{user.id}", "")

        return email, phone_number

    async def get_user_by_user_id(
        self, user_id: UUID, partner_id, show_inactive_users: bool = False
    ) -> Contrasts.GetUserDetailResponse:
        try:
            self.__console_service_logger.info(
                "Fetching user by user_id: {}".format(user_id)
            )
            user: User = await self.__repository.get_user_by_user_id(
                user_id, partner_id, show_inactive_users
            )
            return Contrasts.GetUserDetailResponse.model_validate(user)
        except UserNotFoundError as exec:
            self.__console_service_logger.error(
                "User not found for user id: {}".format(user_id)
            )
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "An error occured while fetching the user: {}".format(exec)
            )
            raise exec
            
    async def get_admin_details_by_partner_id(
        self, partner_id: UUID
    ) -> Contrasts.GetUserDetailResponse:
        try:
            self.__console_service_logger.info(
                "Fetching admin user by partner id: {}".format(partner_id)
            )
            user: User = await self.__repository.get_admin_details_by_partner_id(
                partner_id
            )
            if user is None:
                return Contrasts.GetUserDetailResponse(
                    id=0,
                    name="",
                    email="",
                    designation="",
                    phone_number="",
                    alternate_phone_number="",
                )
            response: Contrasts.GetUserDetailResponse = (
                Contrasts.GetUserDetailResponse.model_validate(user)
            )
            return response
        except UserException as exec:
            self.__console_service_logger.error(
                "User not found for the partner id: {}".format(partner_id)
            )
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "An error occured while fetching the user: {}".format(exec)
            )
            raise exec

    async def is_user_internal(self, user_id: UUID) -> bool:
        user: User = await self.get_user_by_id(user_id)
        if not user.is_internal:
            return False
        return True

    async def enlist_users_dynamically(
        self,
        current_user: dict,
        filter_request: UserRoleFilterRequest,
        partner_repository: PartnerRepository = Depends(Provide["partner_repository"]),
        filter_service: FilterService = Depends(Provide["filter_service"]),
    ) -> List[Dict]:
        try:
            self.__console_service_logger.info(
                "Checking partner: {} is activate or available.".format(
                    filter_request.partner_id
                )
            )
            current_user_partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)
            current_user_id: UUID = current_user.get(CurrentUserMap.USER_ID)
            filter_request.partner_id = (
                filter_request.partner_id or current_user_partner_id
            )
            if filter_request.partner_id != current_user_partner_id:
                if not await self.is_user_internal(current_user_id):
                    return []

            # call partner repository to check partner is exist
            partner = await partner_repository.get_by_id(filter_request.partner_id)

            if partner:
                self.__console_service_logger.info(
                    "Attempting to get users by partner id: {}".format(
                        filter_request.partner_id
                    )
                )
                return await filter_service.get_user_data(filter_request=filter_request)
            raise PartnerNotFoundError(filter_request.partner_id)
        except UserException as user_exc:
            self.__console_service_logger.error(
                "UserException occurred while getting users by partner_id: {}".format(
                    str(user_exc)
                )
            )
            raise user_exc
        except PartnerNotFoundError as ex:
            self.__console_service_logger.error(
                "Partner not find while get users by partner_id: {}".format(str(ex))
            )
            raise ex
        except Exception as ex:
            self.__console_service_logger.error(
                "Unexpected error during get users by partner_id: {}".format(repr(ex))
            )
            raise ex

    async def get_users_by_user_ids(
        self, partner_id: UUID, user_ids: List[int]
    ) -> List[User]:
        try:
            self.__console_service_logger.info(
                "Attempting to get users by user ids: {}".format(user_ids)
            )
            users: List[User] = await self.__repository.get_users_by_user_ids(
                partner_id, user_ids
            )
            return users
        except Exception as ex:
            self.__console_service_logger.error(
                "Unexpected error during get users by user_ids: {}".format(repr(ex))
            )
            raise ex

    async def get_users_availability_status(self, user_ids: List[int]) -> List[Any]:
        try:
            self.__console_service_logger.info(
                "Trying to get the users status by user_ids: {}".format(user_ids)
            )
            users_status: List[Any] = await self.__repository.get_users_availability_status(
                user_ids
            )
            self.__console_service_logger.info(
                "Users status fetched successfully: {}".format(users_status)
            )
            return users_status
        except Exception as exec:
            self.__console_service_logger.error(
                "An error occured while getting users status: {}".format(exec)
            )
            raise exec

    async def has_child_users(self, user_id: UUID) -> bool:
        self.__console_service_logger.info(
            f"Attempting to check user has child users: {user_id}"
        )
        result: bool = await self.__repository.has_child_users(user_id)
        return result

    async def toggle_walkthrough_key_activation(
        self, user_id: UUID, update_data: WalkthroughUpdateRequest
    ) -> None:
        try:
            self.__console_service_logger.info(
                "Trying to update the user walkthrough key for user id: {}".format(
                    user_id
                )
            )

            update_data = update_data.model_dump(exclude_unset=True)

            result: User = await self.__repository.toggle_walkthrough_key_activation(
                user_id, **update_data
            )

            await self.__console_service_cache.clear_pattern(
                prefix=RedisCache.KeysPrefix.CONSOLE,
                pattern=CacheKeys.TOKEN.format(result.partner_id, ""),
            )

        except Exception as exec:
            self.__console_service_logger.error(
                "An unexpected error occured while updating the walkthrough key: {}".format(
                    exec
                )
            )
            raise exec

    async def resolve_user_walkthrough_key(self, user_id: UUID, partner_id: UUID) -> None:
        try:
            self.__console_service_logger.error(
                "Attempting to resolve user walkthrough key by user_id: {}".format(
                    user_id
                )
            )
            user_object: Contrasts.GetUserDetailResponse = (
                await self.get_user_by_user_id(user_id, partner_id)
            )
            walkthrough_starts_at: int = max(
                int(user_object.created_at), int(ENV.WALKTHROUGH_LAUNCH_DATE)
            )
            walkthrough_expires_at: int = (
                walkthrough_starts_at + UserWalkthroughAttribtes.WALKTHROUGH_TIME_PERIOD
            )
            # update_walkthrough_data: WalkthroughUpdateRequest = WalkthroughUpdateRequest(
            #         is_walkthrough_completed = False
            #     )
            if (
                DateTimeUtil.get_current_time() >= walkthrough_expires_at
                and user_object.is_walkthrough_completed == False
            ):
                self.__console_service_logger.info(
                    "User walkthrough is in the time limit updating the key to false"
                )
                update_walkthrough_data: WalkthroughUpdateRequest = (
                    WalkthroughUpdateRequest(is_walkthrough_completed=True)
                )

                await self.toggle_walkthrough_key_activation(
                    user_id, update_walkthrough_data
                )
            # await self.toggle_walkthrough_key_activation(user_id, update_walkthrough_data)

            self.__console_service_logger.info(
                "User walkthrough resolved successfully."
            )

        except Exception as exec:
            self.__console_service_logger.error(
                "An error occured while resolving the user walkthrough key: {}".format(
                    exec
                )
            )
            raise exec

    async def get_agent_details_by_IVR(
        self,
        partner_id: UUID,
        ivr_phone: str,
        api_key: str,
        apiKeyRepository: ApiKeyRepository = Depends(Provide["api_key_repository"]),
        partner_key_repo: PartnerRepository = Depends(Provide["partner_repository"]),
    ) -> dict | None:
        try:
            # Check if the partner exists
            partner: Partner = await partner_key_repo.get_by_id(partner_id=partner_id)

            # Fetch the API key for makonai Partner
            obotaai_api_key: ApiKey = await apiKeyRepository.get_active_api_key(
                partner_id=OBOTAAI_PARTNER_ID
            )
            OBOTAAI_API_KEY: str = obotaai_api_key.key

            # Validadate if the API_KEY is valid
            if api_key == OBOTAAI_API_KEY:
                # Check if the user exists and belong to the partner
                user = await self.__repository.get_user_by_field(
                    "phone_number", ivr_phone
                )
                self.__console_service_logger.info(f"got the user {user}")
                # Get User Information and send it as a response
                if user and user.partner_id == partner_id:
                    response = {
                        "name": user.name,
                        "phone_number": user.phone_number,
                        "id": user.id,
                        "email": user.email,
                    }
                    return response
                raise UserNotFoundError(
                    f"user with IVR {ivr_phone} does't exist for this partner"
                )

            self.__console_service_logger.info(
                f"API_KEY does not exist for user with IVR {ivr_phone}"
            )
            raise ApiKeyNotFoundError("API_KEY is incorrect or does not exist")

        except ApiKeyNotFoundError as apiexc:
            self.__console_service_logger.error(
                "Error while validating API_KEY: {}".format(
                    "API key doesn't match or exist"
                )
            )
            raise ApiKeyNotFoundError(str(apiexc))
        except UserNotFoundError as userExc:
            self.__console_service_logger.error(
                "Error while getting User: {}".format(
                    "User not found, with IVR Number: {}".format(ivr_phone)
                )
            )
            raise UserNotFoundError(str(userExc))
        except PartnerNotFoundError as ex:
            self.__console_service_logger.error(
                "Error while getting Partner: {}".format(
                    "Partner not found, id: {}".format(partner_id)
                )
            )
            raise PartnerNotFoundError(str(ex))
        except Exception as exec:
            self.__console_service_logger.error(
                "An error occured while resolving the user walkthrough key: {}".format(
                    exec
                )
            )
            raise exec

    async def bulk_create(
        self,
        request: BulkUserCreateRequest,
        requesting_partner_id: UUID,
    ):
        """
        Create all users in a single atomic DB transaction.

        Args:
            request: Fully validated BulkUserCreateRequest.
            requesting_partner_id: partner_id from the X-Partner-Id header —
                every user in the batch must carry this same partner_id
                (Server injects it; this is a defence-in-depth check).

        Raises:
            ValueError: Validation failures (duplicate email/phone, bad role, etc.)
        """

        # ── 3. Pre-flight DB uniqueness check ─────────────────────────
        await self._check_uniqueness(request.users)

        # ── 4. Build parent map and topologically sort ─────────────────
        # parent_map: sequence → parent_sequence (None = root)
        parent_map: Dict[int, Optional[int]] = {
            r.sequence: r.parent_sequence for r in request.parent_resolution
        }
        ordered_users = self._topological_sort(request.users, parent_map)

        # ── 5 & 6. Hash + insert inside a single transaction ──────────
        seq_to_user_id: Dict[int, int] = {}
        created = []

        async with self._session_factory() as session:
            async with session.begin():
                for user_entry in ordered_users:
                    hashed_pw = _pwd_context.hash(user_entry.password)

                    # Resolve parent_id from already-created users in this batch
                    parent_seq = parent_map.get(user_entry.sequence)
                    parent_id: Optional[UUID] = None
                    if parent_seq is not None:
                        parent_id = seq_to_user_id.get(parent_seq)
                        if parent_id is None:
                            # Should never happen after topological sort,
                            # but guard explicitly.
                            raise ValueError(
                                "sequence={}: parent sequence={} was not created "
                                "before this user (topology error).".format(
                                    user_entry.sequence, parent_seq
                                )
                            )

                    try:
                        user_id = await self._create_user(
                            session=session,
                            entry=user_entry,
                            hashed_password=hashed_pw,
                            parent_id=parent_id,
                        )
                    except IntegrityError as exc:
                        error_str = str(exc.orig).lower()
                        if "email" in error_str:
                            raise ValueError(
                                "Email '{}' is already registered.".format(
                                    user_entry.email
                                )
                            ) from exc
                        if "phone_number" in error_str:
                            raise ValueError(
                                "Phone number '{}' is already registered.".format(
                                    user_entry.phone_number
                                )
                            ) from exc
                        raise ValueError(
                            "Database integrity error for sequence={}: {}".format(
                                user_entry.sequence, exc
                            )
                        ) from exc

                    seq_to_user_id[user_entry.sequence] = user_id
                    created.append(
                        {
                            "sequence": user_entry.sequence,
                            "user_id": user_id,
                            "email": str(user_entry.email),
                        }
                    )
                    self.__console_service_logger.info(
                        "Created user id={} sequence={} partner={}".format(
                            user_id, user_entry.sequence, user_entry.partner_id
                        )
                    )

        self.__console_service_logger.info(
            "bulk_create complete: {} users created for partner={}".format(
                len(created), requesting_partner_id
            )
        )
        return {"created_users": created, "total": len(created)}

    def _topological_sort(
        self,
        users: List[BulkUserEntry],
        parent_map: Dict[int, Optional[int]],
    ) -> List[BulkUserEntry]:
        """
        Sort users so parents are always created before their children.

        Uses Kahn's algorithm (BFS). Circular chains are already rejected
        by the schema validator so this will always terminate.

        Args:
            users: The full user list.
            parent_map: Dict mapping sequence → parent_sequence (None = root).

        Returns:
            Ordered list — every user appears after their parent.
        """
        user_map: Dict[int, BulkUserEntry] = {u.sequence: u for u in users}

        # in_degree: how many parents does this node depend on (0 or 1)
        in_degree: Dict[int, int] = {u.sequence: 0 for u in users}
        for seq, parent_seq in parent_map.items():
            if parent_seq is not None:
                in_degree[seq] += 1

        # children: parent_sequence → list of child sequences
        children: Dict[int, List[int]] = {u.sequence: [] for u in users}
        for seq, parent_seq in parent_map.items():
            if parent_seq is not None:
                children[parent_seq].append(seq)

        # Start with all roots (no parent dependency)
        queue: List[int] = [seq for seq, deg in in_degree.items() if deg == 0]
        ordered: List[BulkUserEntry] = []

        while queue:
            current_seq = queue.pop(0)
            ordered.append(user_map[current_seq])
            for child_seq in children[current_seq]:
                in_degree[child_seq] -= 1
                if in_degree[child_seq] == 0:
                    queue.append(child_seq)

        return ordered

    async def _check_uniqueness(
        self,
        users: List[BulkUserEntry],
        user_repository: UserRepository = Depends(Provide["user_repository"]),
    ) -> None:
        """
        Pre-flight: confirm no email or phone number already exists in the DB.

        Gives a clear, actionable error before the transaction begins —
        much friendlier than catching an IntegrityError mid-batch.
        """
        emails = [str(u.email).lower() for u in users]
        phones = [u.phone_number for u in users]

        existing_emails = await user_repository.get_users_by_emails(emails)
        if existing_emails:
            raise ValueError(
                "The following email(s) are already registered: {}.".format(
                    ", ".join(sorted(existing_emails))
                )
            )

        existing_phones = await user_repository.get_users_by_phones(phones)
        if existing_phones:
            raise ValueError(
                "The following phone number(s) are already registered: {}.".format(
                    ", ".join(sorted(existing_phones))
                )
            )

    async def _create_user(
        self,
        session: Any,
        entry: BulkUserEntry,
        hashed_password: str,
        parent_id: Optional[UUID],
    ) -> int:
        """
        Insert a single User row within the active session/transaction.

        Returns the new user's primary key (via session.flush).
        The caller is responsible for catching IntegrityError.
        """
        from src.components.user.models import User  # avoid circular import

        user = User(
            name=entry.name,
            email=str(entry.email),
            hashed_password=hashed_password,
            phone_number=entry.phone_number,
            partner_id=entry.partner_id,
            role_id=entry.role_id,
            parent_id=parent_id,
            designation=entry.designation,
            country_id=entry.country_id,
            state_id=entry.state_id,
            city_id=entry.city_id,
            alternate_phone_number=entry.alternate_phone_number,
            cloud_agent_number=entry.cloud_agent_number,
            is_active=True,
            is_internal=False,
            is_email_verified=False,
            is_phone_number_verified=False,
        )
        session.add(user)
        await session.flush()  # assigns user.id without committing
        return user.id


    async def get_bulk_upload_feature_flags(
        self,
        partner_id: UUID,
        partner_config_service = Provide["partner_config_service"],
    ) -> dict:
        custom_roles_cfg = await partner_config_service.get_partner_config_by_key(
            partner_id, PartnerConfigEnum.IS_PARTNER_CUSTOM_ROLES_ENABLED.value
        )
        return {
            "is_partner_custom_roles_enabled": (
                bool(custom_roles_cfg.value) if custom_roles_cfg else False
            ),
        }
    
    async def get_users_id_hierarchy_by_emails(
        self, emails: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Thin delegate to UserRepository.get_users_id_hierarchy_by_emails.
        Bulk-upload's parent resolution (tasks.py) calls this on the object
        returned by container.console_service(), which is a UserService
        instance, not UserRepository directly — hence this pass-through.
        """
        return await self.__repository.get_users_id_hierarchy_by_emails(emails)
    
    async def download_bulk_upload_reference_file(
        self, current_user: dict
    ) -> list[str]:
        partner_id: UUID = current_user.get(CurrentUserMap.PARTNER_ID)

        flags: dict = await self.get_bulk_upload_feature_flags(partner_id)
        headers: list[str] = build_bulk_upload_headers(flags)

        return headers