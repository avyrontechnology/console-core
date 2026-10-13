from uuid import UUID
from typing import Any, Dict, List, Optional

import jwt
from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from grpc import StatusCode
from grpc_interceptor.exceptions import GrpcException
from sqlalchemy import func, select
from sqlalchemy.orm import aliased
from sqlalchemy.sql import column, values

from src.components.api_key.schemas import ApiKeyResponse
from src.components.api_key.services import ApiKeyService
from src.components.common.rpc_uuid import (
    parse_uuid,
    parse_uuid_or_none,
    parse_uuid_list,
    uuid_list_str,
    uuid_str,
)
from src.components.auth.constant import (
    RoleDictKeys,
    RPCExceptionMsg,
    UserKeys,
    config_keys,
)
from src.components.auth.models import Role
from src.components.auth.repositories import AuthRepository
from src.components.entitlement.services import EntitlementService
from src.components.entitlement.utils import EntitlementUtils
from src.components.grace.repositories import GraceRepository
from src.components.location.models import Cities, Countries, States
from src.components.partner.error import PartnerNotFoundError
from src.components.partner.models import Partner
from src.components.partner_address.models import PartnerAddress
from src.components.partner_config.services import PartnerConfigService
from src.components.partner_meta_data.services import PartnerMetaDataServices
from src.components.plan.constants import Platform
from src.components.user.models import User
from src.components.user.services import UserService
from src.components.user_config.models import UserConfig
from src.components.wallet.models import Wallet, WalletTransaction
from src.core.container import Container
from src.core.db import DatabaseSessionManager
from src.core.environment import ENV
from src.pub.auth_pb2 import (
    ActiveUserDetails,
    ChildHierarchy,
    CityDetail,
    CountryDetail,
    GetAllRolesResponse,
    GetCitiesByIdsResponse,
    GetCitiesByNamesResponse,
    GetCountriesByIdsResponse,
    GetCountriesByNamesResponse,
    GetPartnerApiKeyResponse,
    GetPartnerDetailsResponse,
    GetPartnerMetaDataDetailsResponse,
    GetServiceBoardUserDetailsResponse,
    GetStatesByIdsResponse,
    GetStatesByNamesResponse,
    GetUserChildDetailsResponse,
    GetUserChildHierarchyResponse,
    GetUserDetailsByPartnerIdResponse,
    GetUserDetailsResponse,
    GetUserParentDetailsResponse,
    GetUserParentHierarchyResponse,
    GetRolePermissionsResponse,
    GetUserPermissionsResponse,
    GetUserRoleResponse,
    ParentUser,
    RoleDetail,
    StateDetail,
    UserDetail,
    UserParentDetail,
    UserProfile,
    TalkoLoginResponse,
    ValidateTokenResponse,
)
from src.pub.auth_pb2_grpc import AuthServiceServicer

SECRET_KEY = ENV.SECRET_KEY
ALGORITHM = ENV.ALGORITHM


class AuthServiceGRPC(AuthServiceServicer):

    def __init__(self, logger, db_session_manager: DatabaseSessionManager) -> None:
        self.__logger = logger
        self.__db_session_manager = db_session_manager

    @inject
    async def ValidateToken(
        self,
        request,
        context,
        session_management_service=Depends(Provide[Container.user_session_service]),
    ):
        mcontext = request.mcontext
        mbody = request.mbody
        self.__logger.info(
            f"Validating token for correlation_id: {mcontext.correlation_id}"
        )
        token = mbody.token
        if not token:
            self.__logger.info("Token not provided")
            raise GrpcException(
                details="Token not provided",
                status_code=StatusCode.UNAUTHENTICATED,
            )
        try:
            # Decode token
            payload = jwt.decode(token, SECRET_KEY, algorithms=ALGORITHM)
            session_id = payload.get("user_session_id")

            # Need to verify session is active or not
            user_session = await session_management_service.get_user_session(session_id)

            return ValidateTokenResponse(
                is_active=user_session.is_active,
                session_id=user_session.session_id,
                user_id=payload.get("user_id"),
                partner_id=payload.get("partner_id"),
                is_talko_enabled=payload.get("is_talko_enabled"),
                is_internal=payload.get("is_internal"),
                is_wallet_enabled=payload.get("is_wallet_enabled"),
                is_obotaai_enabled=payload.get("is_obotaai_enabled"),
            )
        except jwt.ExpiredSignatureError:
            return ValidateTokenResponse(is_active=False)
        except jwt.InvalidTokenError:
            return ValidateTokenResponse(is_active=False)
        except Exception as exc:
            self.__logger.error(f"Got an unexpected Error: {exc}")
            return ValidateTokenResponse(is_active=False)

    @inject
    async def TalkoLogin(
        self,
        request,
        context,
        auth_service=Depends(Provide[Container.auth_service]),
    ):
        """Centralized credential check for Talko login. No session created."""
        from src.exceptions import AuthException as AuthExc

        try:
            profile = await auth_service.verify_talko_credentials(
                credential=request.credential,
                password=request.password,
            )
            return TalkoLoginResponse(
                message="Success",
                user_id=uuid_str(profile["user_id"]),
                partner_id=uuid_str(profile["partner_id"]),
                role_id=uuid_str(profile["role_id"]),
                role_hierarchy=profile["role_hierarchy"]
                if profile["role_hierarchy"] is not None
                else -1,
                email=profile["email"] or "",
                name=profile["name"] or "",
                is_active=bool(profile["is_active"]),
            )
        except AuthExc as exc:
            raise GrpcException(
                details=str(exc),
                status_code=StatusCode.UNAUTHENTICATED,
            )
        except Exception as exc:
            self.__logger.error(f"TalkoLogin unexpected error: {exc}")
            raise GrpcException(
                details=RPCExceptionMsg.ERROR_MSG,
                status_code=StatusCode.INTERNAL,
            )

    async def GetUserChildHierarchy(self, request, context):
        """
        Retrieve the hierarchy of child users for a list of user IDs using a single recursive Common Table Expression (CTE).

        This method constructs a recursive CTE to fetch all child users for the provided user IDs in a single query.
        The query starts by selecting users whose `parent_id` is in the input `user_ids`, tracking the original `user_id`.
        It recursively selects users whose `parent_id` matches the `id` of previously found users, maintaining the original
        `user_id`. The results are aggregated by `user_id`, collecting child user IDs into an array using array_agg.
        A LEFT JOIN ensures all input user_ids are included, even those with no children.

        Args:
            request: A GetUserChildHierarchyRequest object containing:
                - mcontext: Metadata context.
                - user_ids: A list of user IDs for which to retrieve child hierarchies.

        Returns:
            GetUserChildHierarchyResponse: An object containing:
                - message (str): A success message indicating the operation was successful.
                - child_hierarchy (list): A list of ChildHierarchy objects, each with a user ID and its child user IDs.
        """
        mcontext = request.mcontext
        user_ids = parse_uuid_list(request.user_ids, "user_ids")

        self.__logger.info(f"Fetching child user hierarchies for user_ids: {uuid_list_str(user_ids)}")

        if not user_ids:
            self.__logger.error("No user IDs provided in request")
            raise GrpcException(
                details=RPCExceptionMsg.USER_ID_NOT_FOUND,
                status_code=StatusCode.INVALID_ARGUMENT,
            )

        try:
            async with self.__db_session_manager.session() as session:
                user_ids_table = values(
                    column("user_id", User.id.type), name="input_users"
                ).data([(user_id,) for user_id in user_ids])

                child_users_cte = (
                    select(
                        user_ids_table.c.user_id.label("root_user_id"),
                        User.id.label("child_id"),
                    )
                    .select_from(user_ids_table)
                    .join(
                        User,
                        (User.parent_id == user_ids_table.c.user_id)
                        & (User.is_active.is_(True)),
                    )
                    .cte(name="child_users", recursive=True)
                )

                child_users_cte = child_users_cte.union_all(
                    select(
                        child_users_cte.c.root_user_id, User.id.label("child_id")
                    ).join(
                        User,
                        (User.parent_id == child_users_cte.c.child_id)
                        & (User.is_active.is_(True)),
                    )
                )

                query = (
                    select(
                        user_ids_table.c.user_id.label("user_id"),
                        func.coalesce(
                            func.array_agg(child_users_cte.c.child_id), []
                        ).label("child_ids"),
                    )
                    .select_from(user_ids_table)
                    .outerjoin(
                        child_users_cte,
                        child_users_cte.c.root_user_id == user_ids_table.c.user_id,
                    )
                    .group_by(user_ids_table.c.user_id)
                )

                result = await session.execute(query)
                rows = result.all()

                self.__logger.info(f"Found child hierarchies for {len(rows)} user IDs")
                self.__logger.debug(
                    f"Query results: {[dict(row._mapping) for row in rows]}"
                )

                child_hierarchy_list = []
                for row in rows:
                    user_id = row.user_id
                    child_ids = [uuid_str(cid) for cid in row.child_ids if cid] or []
                    child_hierarchy_list.append(
                        ChildHierarchy(user_id=uuid_str(user_id), child_ids=child_ids)
                    )

                return GetUserChildHierarchyResponse(
                    message="Success", child_hierarchy=child_hierarchy_list
                )

        except Exception as exc:
            self.__logger.error(f"Error fetching child user hierarchies: {exc}")
            raise GrpcException(
                details=RPCExceptionMsg.ERROR_MSG,
                status_code=StatusCode.INTERNAL,
            )

    async def GetUserChildDetails(self, request, context):
        """
        Retrieve the hierarchy of child users for a given user ID using a recursive Common Table Expression (CTE).

        This method uses a recursive CTE to fetch all child users for a specified user ID. The recursive query starts by
        selecting users whose `parent_id` matches the provided `user_id`. It then recursively selects users whose `parent_id`
        matches the `id` of the users found in the previous iteration.

        The results are returned as a list of child user objects wrapped in a response object.

        Args:
            user_id (int): The ID of the user for whom the child user hierarchy is to be retrieved.

        Returns:
            GetUserChildHierarchyResponse: An object containing:
                - message (str): A success message indicating the operation was successful.
                - user_detail (list): A list of child user objects retrieved from the database.
        """

        mcontext = request.mcontext
        if not request.user_id:
            self.__logger.error("User ID not provided in request")
            raise GrpcException(
                details=RPCExceptionMsg.USER_ID_NOT_FOUND,
                status_code=StatusCode.INVALID_ARGUMENT,
            )
        user_id = parse_uuid(request.user_id, "user_id")

        self.__logger.info(f"Fetching child user list for user_id: {user_id}")

        try:
            # Fetch child users from user service or database
            async with self.__db_session_manager.session() as session:

                # Base query: Select the initial set of child users for the given parent
                child_users_cte = (
                    select(
                        User.id.label("user_id"),
                        User.email.label("email"),
                        User.is_active.label("is_active"),
                        User.is_suspended.label("is_suspended"),
                        User.name.label("name"),
                    )
                    .where(User.parent_id == user_id)
                    .cte(name="result", recursive=True)
                )

                # Recursive part: Select users where the parent is in the previously selected set
                recursive_query = select(
                    User.id.label("user_id"),
                    User.email.label("email"),
                    User.is_active.label("is_active"),
                    User.is_suspended.label("is_suspended"),
                    User.name.label("name"),
                ).join(child_users_cte, User.parent_id == child_users_cte.c.user_id)

                # Combine the base and recursive queries
                child_users_cte = child_users_cte.union_all(recursive_query)

                # Query the CTE
                query = select(
                    child_users_cte.c.user_id,
                    child_users_cte.c.email,
                    child_users_cte.c.is_active,
                    child_users_cte.c.is_suspended,
                    child_users_cte.c.name,
                )
                result = await session.execute(query)

                result = result.mappings().all()

                # Map the results to UserDetail messages
                users_details = [
                    UserDetail(
                        user_id=uuid_str(row.get(UserKeys.USER_ID)),
                        name=row.get(UserKeys.NAME),
                        email=row.get(UserKeys.EMAIL),
                        is_active=row.get(UserKeys.IS_ACTIVE),
                    )
                    for row in result
                ]
                self.__logger.info(
                    f"Found {users_details} child users for user_id: {user_id}"
                )
                return GetUserChildDetailsResponse(
                    message="Success",
                    user_detail=users_details,
                )
        except Exception as exc:
            self.__logger.error(f"Error fetching child users: {exc}")
            raise GrpcException(
                details=RPCExceptionMsg.ERROR_MSG,
                status_code=StatusCode.INTERNAL,
            )

    async def GetUserDetails(
        self,
        request,
        context,
        entitlement_service: EntitlementService = Depends(
            Provide["entitlement_service"]
        ),
        grace_repo: GraceRepository = Depends(Provide["grace_repository"]),
    ):
        mcontext = request.mcontext
        if not request.user_id:
            self.__logger.error("User ID not provided in request")
            raise GrpcException(
                details=RPCExceptionMsg.USER_ID_NOT_FOUND,
                status_code=StatusCode.INVALID_ARGUMENT,
            )
        user_id = parse_uuid(request.user_id, "user_id")

        self.__logger.info(f"Fetching user details for user_id: {user_id}")

        try:
            async with self.__db_session_manager.session() as session:
                user_query = (
                    select(
                        User.id.label("user_id"),
                        User.name.label("name"),
                        User.email.label("email"),
                        User.partner_id.label("partner_id"),
                        Partner.name.label("partner_name"),
                        Role.hierarchy.label("role_hierarchy_level"),
                        Role.data_scope.label("role_data_scope"),
                        Role.name.label("role_name"),
                        User.phone_number.label("phone_number"),
                        User.is_active.label("is_active"),
                        User.is_email_verified.label("is_email_verified"),
                        User.is_phone_number_verified.label("is_phone_number_verified"),
                        User.is_walkthrough_completed.label("is_walkthrough_completed"),
                        User.cloud_agent_number.label("cloud_agent_number"),
                        User.additional_info.label("additional_info"),
                    )
                    .outerjoin(Partner, Partner.id == User.partner_id)
                    .outerjoin(Role, Role.id == User.role_id)
                    .where(User.id == user_id)
                )
                result = await session.execute(user_query)
                user_row = result.mappings().first()

                if not user_row:
                    self.__logger.error(f"User not found for user_id: {user_id}")
                    return {}

                user_row: dict = dict(user_row)

                partner_id: UUID = user_row.get("partner_id")
                role_hierarchy: int = user_row.get("role_hierarchy_level") or 99

                additional_info: dict = user_row.get("additional_info") or {}
                popup_last_closed: dict = additional_info.get("popup_last_closed") or {}
                popup_last_closed_clean: dict = {
                    k: int(v)
                    for k, v in popup_last_closed.items()
                    if isinstance(v, (int, float))
                }

                # ── Compute show_popup for all services ───────────────────────
                # Default: all services false
                show_popup_map: dict = {
                    Platform.CONSOLE: False,
                    Platform.OBOTAAI: False,
                }
                try:
                    subscription_status: Dict[str, Any] = (
                        await entitlement_service.get_subscription_status(
                            partner_id=partner_id,
                            grace_repo=grace_repo,
                        )
                    )
                    show_popup_map: Dict[str, bool] = (
                        EntitlementUtils.compute_show_popup(
                            user_hierarchy=role_hierarchy,
                            subscription_status=subscription_status,
                            popup_last_closed=popup_last_closed_clean,
                        )
                    )
                except Exception as exc:
                    self.__logger.warning(
                        "show_popup computation failed for user_id={} partner_id={}: {}. "
                        "Defaulting all services to false.".format(
                            user_id, partner_id, exc
                        )
                    )

                config_query = select(UserConfig.key, UserConfig.value).where(
                    UserConfig.user_id == user_id, UserConfig.key.in_(config_keys)
                )
                config_result = await session.execute(config_query)
                config_map: dict = {
                    row.key: str(row.value).lower() == "true"
                    for row in config_result.fetchall()
                }

                if not user_row.get(UserKeys.IS_ACTIVE):
                    user_row["name"] = f"{user_row.get('name')} (Inactive)"

                user_profile = UserProfile(
                    user_id=uuid_str(user_row.get(UserKeys.USER_ID)),
                    name=user_row.get(UserKeys.NAME),
                    email=user_row.get(UserKeys.EMAIL),
                    partner_id=uuid_str(user_row.get(UserKeys.PARTNER_ID)),
                    role_hierarchy_level=user_row.get(UserKeys.ROLE_HIERARCHY_LEVEL),
                    role_data_scope=user_row.get("role_data_scope") or "",
                    role_name=user_row.get("role_name") or "",
                    partner_name=user_row.get(UserKeys.PARTNER_NAME),
                    is_talko_enabled=config_map.get(UserKeys.IS_TALKO_ENABLED, False),
                    phone_number=user_row.get(UserKeys.PHONE_NUMBER),
                    is_active=user_row.get(UserKeys.IS_ACTIVE),
                    is_email_verified=user_row.get(UserKeys.IS_EMAIL_VERIFIED),
                    is_phone_number_verified=user_row.get(
                        UserKeys.IS_PHONE_NUMBER_VERIFIED
                    ),
                    is_walkthrough_completed=user_row.get(
                        UserKeys.IS_WALKTHROUGH_COMPLETED
                    ),
                    cloud_agent_number=user_row.get(UserKeys.CLOUD_AGENT_NUMBER),
                    is_gsm_calling_enabled=config_map.get(
                        UserKeys.IS_GSM_CALLING_ENABLED
                    ),
                    is_meeting_log_enabled=config_map.get(
                        UserKeys.IS_MEETING_LOG_ENABLED
                    ),
                    show_popup=show_popup_map,
                    enable_dialer=config_map.get(UserKeys.ENABLE_DIALER, False),
                    can_view_products=config_map.get("can_view_products", False),
                    can_view_inventory=config_map.get("can_view_inventory", False),
                    can_view_payment_history=config_map.get(
                        "can_view_payment_history", False
                    ),
                    can_view_report_management=config_map.get(
                        "can_view_report_management", False
                    ),
                    can_clone_service_board=config_map.get(
                        "can_clone_service_board", False
                    ),
                )

                self.__logger.info(f"User details retrieved for user_id: {user_id}")
                return GetUserDetailsResponse(
                    message="Success",
                    user_profile=user_profile,
                )

        except Exception as exc:
            self.__logger.error(f"Error fetching user details: {exc}")
            return None

    @inject
    async def GetUserPermissions(
        self,
        request,
        context,
        partner_config_service: PartnerConfigService = Depends(
            Provide[Container.partner_config_service]
        ),
    ):
        """
        Retrieve the permissions for a given user ID.
        """
        if not request.user_id:
            self.__logger.error("User ID not provided in request")
            raise GrpcException(
                details=RPCExceptionMsg.USER_ID_NOT_FOUND,
                status_code=StatusCode.INVALID_ARGUMENT,
            )
        user_id = parse_uuid(request.user_id, "user_id")

        self.__logger.info(f"Fetching permissions for user_id: {user_id}")
        try:
            # Fetch permissions from user
            user_permissions: list[str] = (
                await partner_config_service.custom_role_permission_check(user_id)
            )
            return GetUserPermissionsResponse(
                message="Success",
                permissions=user_permissions,
            )
        except Exception as exc:
            self.__logger.error(f"Error fetching permissions: {exc}")
            raise GrpcException(
                details=RPCExceptionMsg.ERROR_MSG,
                status_code=StatusCode.INTERNAL,
            )

    @inject
    async def GetUserRole(
        self, request, context, auth_service=Depends(Provide[Container.auth_service])
    ):
        """
        Retrieve the role for a given user ID.
        """
        if not request.user_id:
            self.__logger.error("User ID not provided in request")
            raise GrpcException(
                details=RPCExceptionMsg.USER_ID_NOT_FOUND,
                status_code=StatusCode.INVALID_ARGUMENT,
            )
        user_id = parse_uuid(request.user_id, "user_id")

        self.__logger.info(f"Fetching role for user_id: {user_id}")
        try:
            # Fetch role from user
            user_role = await auth_service.get_role_by_user_id(user_id)
            return GetUserRoleResponse(
                message="Success",
                role=user_role.get(RoleDictKeys.SLUG),
                hierarchy=user_role.get(RoleDictKeys.HIERARCHY),
            )
        except Exception as exc:
            self.__logger.error(f"Error fetching role: {exc}")
            raise GrpcException(
                details=RPCExceptionMsg.ERROR_MSG,
                status_code=StatusCode.INTERNAL,
            )

    @inject
    async def GetRolePermissions(
        self,
        request,
        context,
        partner_config_service: PartnerConfigService = Depends(
            Provide[Container.partner_config_service]
        ),
    ):
        """Return the configured permission slugs granted to a specific role."""
        if not request.role_id:
            raise GrpcException(
                details=RPCExceptionMsg.ROLE_ID_NOT_FOUND,
                status_code=StatusCode.INVALID_ARGUMENT,
            )
        role_id = parse_uuid(request.role_id, "role_id")
        self.__logger.info("GetRolePermissions called role_id={}".format(role_id))
        try:
            permissions: list[str] = (
                await partner_config_service.role_permission_check(role_id)
            )
            return GetRolePermissionsResponse(
                message="Success", permissions=permissions
            )
        except Exception as exc:
            self.__logger.error(f"Error fetching role permissions: {exc}")
            raise GrpcException(
                details=RPCExceptionMsg.ERROR_MSG,
                status_code=StatusCode.INTERNAL,
            )

    @inject
    async def GetServiceBoardUsersDetails(
        self, request, context, user_service=Depends(Provide[Container.console_service])
    ) -> List[UserDetail]:

        user_ids: List[UUID] = parse_uuid_list(request.user_ids, "user_ids")
        show_inactive_users: Optional[bool] = request.show_inactive_users
        self.__logger.info(f"Fetching service board users :{user_ids}, details.")

        if not user_ids:
            self.__logger.error("User IDs not provided in request")
            raise GrpcException(
                details=RPCExceptionMsg.USERS_IDS_NOT_FOUND,
                status_code=StatusCode.INVALID_ARGUMENT,
            )
        try:
            # Fetch role from user
            result = await user_service.get_service_board_users_details(
                user_ids, show_inactive_users
            )
            users_details = [
                UserDetail(
                    user_id=uuid_str(row.get(UserKeys.USER_ID)),
                    name=row.get(UserKeys.NAME),
                    email=row.get(UserKeys.EMAIL),
                    is_active=row.get(UserKeys.IS_ACTIVE),
                    role=row.get(UserKeys.ROLE),
                    role_hierarchy=row.get(UserKeys.ROLE_HIERARCHY_LEVEL),
                    current_status=row.get("current_status") or "Away",
                )
                for row in result
            ]

            return GetServiceBoardUserDetailsResponse(
                message="Success",
                user_detail=users_details,
            )
        except Exception as exc:
            self.__logger.error(f"Error fetching service board users details: {exc}")
            raise GrpcException(
                details=RPCExceptionMsg.ERROR_MSG,
                status_code=StatusCode.INTERNAL,
            )

    async def GetPartnerDetails(
        self,
        request,
        context,
        entitlement_service: EntitlementService = Depends(
            Provide["entitlement_service"]
        ),
        grace_repo: GraceRepository = Depends(Provide["grace_repository"]),
    ):
        mcontext = request.mcontext
        if not request.partner_id:
            self.__logger.error("Partner ID not provided in request")
            raise GrpcException(
                details="Partner ID not found",
                status_code=StatusCode.INVALID_ARGUMENT,
            )
        partner_id = parse_uuid(request.partner_id, "partner_id")

        self.__logger.info(f"Fetching partner details for partner_id: {partner_id}")

        try:
            # ── Fetch partner row ─────────────────────────────────────────────
            async with self.__db_session_manager.session() as session:
                address_exists_subquery = (
                    select(PartnerAddress.id)
                    .where(PartnerAddress.partner_id == partner_id)
                    .exists()
                    .select()
                )
                partner_query = (
                    select(
                        Partner.id.label("partner_id"),
                        Partner.name.label("name"),
                        Partner.company_legal_name.label("company_legal_name"),
                        Partner.cin_no.label("cin_no"),
                        Partner.gst_no.label("gst_no"),
                        Partner.is_active.label("is_active"),
                        Partner.created_at.label("created_at"),
                        Partner.partner_status.label("partner_status"),
                        Partner.is_feedback_enabled.label("is_feedback_enabled"),
                        Partner.active_license.label("active_license"),
                        address_exists_subquery.label("has_address"),
                    )
                    .select_from(Partner)
                    .where(Partner.id == partner_id)
                )

                result = await session.execute(partner_query)
                partner_row = result.mappings().first()

                if not partner_row:
                    self.__logger.error(
                        f"Partner not found for partner_id: {partner_id}"
                    )
                    raise GrpcException(
                        details="Partner not found",
                        status_code=StatusCode.NOT_FOUND,
                    )

                partner_logo: Optional[str] = None

                is_publisher_onboarding_completed: bool = bool(
                    partner_row.get("has_address")
                )

            # ── Fetch subscription status (outside db session) ────────────────
            subscription_status_map: Dict[str, Any] = {}
            try:
                raw_status: Dict[str, Any] = (
                    await entitlement_service.get_subscription_status(
                        partner_id=partner_id,
                        grace_repo=grace_repo,
                    )
                )
                for service_name, data in raw_status.items():
                    entry: Dict[str, Any] = {
                        "status": data.get("status", "suspended"),
                        "entitlement_start_date": data.get("entitlement_start_date"),
                        "entitlement_end_date": data.get("entitlement_end_date"),
                    }
                    # Grace dates are only present when status == "grace"
                    if data.get("grace_start_date") is not None:
                        entry["grace_start_date"] = data["grace_start_date"]
                    if data.get("grace_end_date") is not None:
                        entry["grace_end_date"] = data["grace_end_date"]

                    subscription_status_map[service_name] = entry

            except Exception as exc:
                self.__logger.warning(
                    "Failed to fetch subscription status for partner_id={}: {}. "
                    "Returning empty subscription_status.".format(partner_id, exc)
                )

            # ── Build and return response ─────────────────────────────────────
            partner_detail = {
                "partner_id": uuid_str(partner_row.get("partner_id")),
                "name": partner_row.get("name"),
                "company_legal_name": partner_row.get("company_legal_name"),
                "cin_no": partner_row.get("cin_no"),
                "gst_no": partner_row.get("gst_no"),
                "is_active": partner_row.get("is_active"),
                "partner_status": partner_row.get("partner_status"),
                "partner_logo": partner_logo,
                "created_at": partner_row.get("created_at"),
                "is_feedback_enabled": partner_row.get("is_feedback_enabled"),
                "is_publisher_onboarding_completed": is_publisher_onboarding_completed,
                "subscription_status": subscription_status_map,
                "active_license": partner_row.get("active_license"),
            }

            self.__logger.info(
                f"Partner details retrieved for partner_id: {partner_id}"
            )

            return GetPartnerDetailsResponse(
                message="Success",
                partner_detail=partner_detail,
            )

        except Exception as exc:
            self.__logger.error(f"Error fetching partner details: {exc}")
            raise GrpcException(
                details=RPCExceptionMsg.ERROR_MSG,
                status_code=StatusCode.INTERNAL,
            )

    async def GetActiveUsersByPartnerId(
        self,
        request,
        context,
        console_service: UserService = Depends(Provide[Container.console_service]),
    ):
        try:
            partner_id: UUID = parse_uuid(request.partner_id, "partner_id")
            self.__logger.info(
                "Get All Active User throough RPC for partner ID: {}".format(partner_id)
            )
            users: List[dict] = await console_service.get_users_by_partner_id(
                partner_id
            )
            result = [
                ActiveUserDetails(
                    id=uuid_str(user.get("id")),
                    name=user.get("name"),
                    email=user.get("email"),
                    phone_number=user.get("phone_number"),
                    role=user.get("role"),
                    role_hierarchy=user.get("role_hierarchy"),
                    role_data_scope=user.get("role_data_scope"),
                )
                for user in users
            ]
            return GetUserDetailsByPartnerIdResponse(
                message=f"Successfully fetched users for partner Id: {partner_id}",
                users=result,
            )
        except PartnerNotFoundError as exc:
            self.__logger.error(
                "An Error occured while fetching users for partner id: {} Exc: {}".format(
                    partner_id, exc
                )
            )
            return GetUserDetailsByPartnerIdResponse(
                message=f"Partner not found with  partner Id: {partner_id}", users=[]
            )
        except Exception as exc:
            self.__logger.error(
                "An Unexpected Error occured in GetAllActiveUsersByPartnerId RPC method: {}".format(
                    exc
                )
            )

    async def GetUserParentDetails(self, request, context):
        """
        Retrieve parent user details for a list of user IDs.

        This method fetches the user and their parent details (ID and name) for the provided user IDs.
        It performs a LEFT JOIN to include the parent user's details if they exist.

        Args:
            request: A GetUserParentDetailsRequest object containing:
                - user_ids: A list of user IDs for which to retrieve parent details.

        Returns:
            GetUserParentDetailsResponse: An object containing:
                - message (str): A success message indicating the operation was successful.
                - user_details (list): A list of UserParentDetail objects, each with user ID, name, parent ID, and parent name.
        """
        user_ids = parse_uuid_list(request.user_ids, "user_ids")
        self.__logger.info(f"Fetching parent details for user_ids: {uuid_list_str(user_ids)}")

        try:
            async with self.__db_session_manager.session() as session:
                # Alias for the parent User table
                parent_user = aliased(User, name="parent_user")

                query = (
                    select(
                        User.id.label("user_id"),
                        User.name.label("name"),
                        User.parent_id.label("parent_id"),
                        parent_user.name.label("parent_name"),
                    )
                    .outerjoin(parent_user, User.parent_id == parent_user.id)
                    .where(User.id.in_(user_ids))
                )

                result = await session.execute(query)
                rows = result.mappings().all()

                self.__logger.info(f"Found parent details for {len(rows)} user IDs")

                user_details = [
                    UserParentDetail(
                        user_id=uuid_str(row["user_id"]),
                        name=row["name"],
                        parent_id=uuid_str(row["parent_id"]),
                        parent_name=row["parent_name"] or "",
                    )
                    for row in rows
                ]

                return GetUserParentDetailsResponse(
                    message="Success",
                    user_details=user_details,
                )

        except Exception as exc:
            self.__logger.error(f"Error fetching parent details: {exc}")
            raise GrpcException(
                details=RPCExceptionMsg.ERROR_MSG,
                status_code=StatusCode.INTERNAL,
            )

    async def GetPartnerMetaDataDetails(
        self,
        request,
        context,
        partner_meta_data_service: PartnerMetaDataServices = Depends(
            Provide[Container.partner_meta_data_service]
        ),
        partner_config_service: PartnerConfigService = Depends(
            Provide[Container.partner_config_service]
        ),
    ):
        """
        RPC method for get partner meta data details
        """
        try:
            partner_id = parse_uuid(request.partner_id, "partner_id")
            meta_data = (
                await partner_meta_data_service.get_partner_meta_data_by_partner_id(
                    partner_id
                )
            )
            service_enabled_for_partner = (
                await partner_config_service.get_partner_configs_by_partner_id(
                    partner_id
                )
            )

            if service_enabled_for_partner and isinstance(
                service_enabled_for_partner[0], dict
            ):
                services_enabled_dict = {
                    item["key"]: item["value"] for item in service_enabled_for_partner
                }
            elif service_enabled_for_partner:
                services_enabled_dict = {
                    item.key: item.value for item in service_enabled_for_partner
                }
            else:
                services_enabled_dict = {}

            def get_str_value(key, default=""):
                value = services_enabled_dict.get(key, default)
                return value if isinstance(value, str) else default

            response = GetPartnerMetaDataDetailsResponse(
                type_of_business=meta_data.type_of_business,
                years_in_business=meta_data.years_in_business,
                annual_revenue=meta_data.annual_revenue,
                is_talko_enabled=services_enabled_dict.get("is_talko_enabled", False),
                can_create_deals=services_enabled_dict.get("can_create_deals", False),
                can_add_workflow=services_enabled_dict.get("can_add_workflow", False),
                can_view_workflow=services_enabled_dict.get("can_view_workflow", False),
                is_email_verification_enabled=services_enabled_dict.get(
                    "is_email_verification_enabled", False
                ),
                is_phone_number_verification_enabled=services_enabled_dict.get(
                    "is_phone_number_verification_enabled", False
                ),
                is_wallet_enabled=services_enabled_dict.get("is_wallet_enabled", False),
                email_config_key=get_str_value("email_config_key"),
                smtp_username=get_str_value("smtp_username"),
                smtp_password=get_str_value("smtp_password"),
                from_email=get_str_value("from_email"),
                subscription_mode=get_str_value("subscription_mode"),
                is_rule_based_assignment_enabled=services_enabled_dict.get(
                    "is_rule_based_assignment_enabled", False
                ),
                can_view_contact=services_enabled_dict.get("can_view_contact", False),
                can_view_organization=services_enabled_dict.get("can_view_organization", False),
                can_view_template_management=services_enabled_dict.get("can_view_template_management", False),
                can_view_product_management=services_enabled_dict.get("can_view_product_management", False),
                can_view_finance_management=services_enabled_dict.get("can_view_finance_management", False),
                is_add_number_enabled=services_enabled_dict.get("is_add_number_enabled", False),
                is_obotaai_enabled=services_enabled_dict.get("is_obotaai_enabled", False),
                is_user_tracker_enabled=services_enabled_dict.get("is_user_tracker_enabled", False),
                can_view_report_management=services_enabled_dict.get("can_view_report_management", False),
                can_view_helpdesk_management=services_enabled_dict.get("can_view_helpdesk_management", False),
                can_download_call_logs=services_enabled_dict.get("can_download_call_logs", False),
                is_agent_availability_based_assignment_enabled=services_enabled_dict.get("is_agent_availability_based_assignment_enabled", False),
                is_sticky_dids_enabled=services_enabled_dict.get("is_sticky_dids_enabled", False),
                is_assignee_sync_enabled=services_enabled_dict.get("is_assignee_sync_enabled", False),
            )
            return response
        except Exception as exc:
            self.__logger.error(f"Error fetching parent meta data details: {exc}")
            raise GrpcException(
                details=RPCExceptionMsg.ERROR_MSG,
                status_code=StatusCode.INTERNAL,
            )

    @inject
    async def GetWalletTransactionHistory(self, request, context):
        """
        Fetch wallet details and transaction history for a given partner using SQLAlchemy ORM.
        Returns plain dict (no schema).
        """
        try:
            partner_id = parse_uuid(request.partner_id, "partner_id")
            service_name = request.service_name or None
            transaction_type = request.transaction_type or None

            async with self.db_session() as session:
                # Fetch wallet
                wallet = await session.scalar(
                    select(Wallet).where(Wallet.partner_id == partner_id).limit(1)
                )

                if not wallet:
                    self.__logger.info("Wallet not found for given partner_id")
                    return {}

                # Fetch transactions
                query = (
                    select(WalletTransaction)
                    .where(WalletTransaction.partner_id == partner_id)
                    .order_by(WalletTransaction.created_at.desc())
                )

                if service_name:
                    query = query.where(WalletTransaction.service_name == service_name)
                if transaction_type:
                    query = query.where(
                        WalletTransaction.transaction_type == transaction_type
                    )

                result = await session.scalars(query)
                transactions = result.all()

            # Prepare plain dict response
            return {
                "wallet": {
                    "wallet_id": uuid_str(wallet.id),
                    "balance": wallet.balance,
                    "frozen_balance": wallet.frozen_balance,
                    "currency": wallet.currency,
                },
                "transactions": [
                    {
                        "id": uuid_str(tx.id),
                        "amount": tx.amount,
                        "service_name": tx.service_name,
                        "transaction_type": tx.transaction_type,
                        "remarks": tx.remarks,
                        "created_at": tx.created_at,
                    }
                    for tx in transactions
                ],
            }
        except Exception as e:
            self.__logger.error(
                "Error fetching wallet transaction history for partner_id={}, {}".format(
                    request.partner_id, e
                )
            )
            raise GrpcException(
                details=RPCExceptionMsg.ERROR_MSG,
                status_code=StatusCode.INTERNAL,
            )

    @inject
    async def GetPartnerApiKey(
        self,
        request,
        context,
        api_service: ApiKeyService = Depends(Provide[Container.api_key_service]),
    ):
        try:
            partner_id: UUID = parse_uuid(request.partner_id, "partner_id")
            self.__logger.info(f"Getting API Key for partner Partner ID: {partner_id}")
            api_key_response: ApiKeyResponse = await api_service.workflow_get_api_key(
                partner_id=partner_id
            )
            self.__logger.debug(f"Got the API Key response: {api_key_response}")

            if not api_key_response:
                return GetPartnerApiKeyResponse(api_key="None")

            api_key = api_key_response.key
            self.__logger.debug(f"Succesfully fetched the API Key: {api_key}")
            return GetPartnerApiKeyResponse(api_key=api_key)
        except Exception as exc:
            self.__logger.error(f"Got an unexpected Error: {exc}")
            return GetPartnerApiKeyResponse(api_key="None")

    async def GetUserParentHierarchy(self, request, context):
        if not request.user_id:
            raise GrpcException(
                details=RPCExceptionMsg.USER_ID_NOT_FOUND,
                status_code=StatusCode.INVALID_ARGUMENT,
            )
        user_id = parse_uuid(request.user_id, "user_id")

        try:
            async with self.__db_session_manager.session() as session:

                parent_cte = (
                    select(
                        User.id.label("user_id"),
                        User.name.label("name"),
                        User.parent_id.label("parent_id"),
                        Role.name.label("role"),
                        Role.hierarchy.label("role_hierarchy"),
                    )
                    .join(Role, Role.id == User.role_id)
                    .where(
                        User.id
                        == select(User.parent_id)
                        .where(User.id == user_id)
                        .scalar_subquery()
                    )
                    .cte(name="parent_cte", recursive=True)
                )

                parent_cte = parent_cte.union_all(
                    select(
                        User.id,
                        User.name,
                        User.parent_id,
                        Role.name,
                        Role.hierarchy,
                    )
                    .join(Role, Role.id == User.role_id)
                    .join(parent_cte, User.id == parent_cte.c.parent_id)
                    .where(User.is_active.is_(True))
                )

                query = select(
                    parent_cte.c.user_id,
                    parent_cte.c.name,
                    parent_cte.c.role,
                    parent_cte.c.role_hierarchy,
                ).order_by(parent_cte.c.role_hierarchy.desc())

                result = await session.execute(query)
                rows = result.all()

                parents = [
                    ParentUser(
                        user_id=uuid_str(row.user_id),
                        name=row.name,
                        role=row.role,
                        role_hierarchy=row.role_hierarchy,
                    )
                    for row in rows
                ]

                return GetUserParentHierarchyResponse(
                    message="Success",
                    parents=parents,
                )

        except Exception as exc:
            self.__logger.error("Error fetching parent hierarchy: {}".format(exc))
            raise GrpcException(
                details=RPCExceptionMsg.ERROR_MSG,
                status_code=StatusCode.INTERNAL,
            )

    async def GetCountriesByIds(self, request, context):
        """
        Accepts a list of country IDs.
        Returns CountryDetail (id, name, slug) for each found country.
        IDs not found in DB are silently omitted from the response.
        """
        ids = parse_uuid_list(request.ids, "ids")

        if not ids:
            raise GrpcException(
                details="ids must be a non-empty list of country IDs",
                status_code=StatusCode.INVALID_ARGUMENT,
            )

        try:
            async with self.__db_session_manager.session() as session:
                self.__logger.info("GetCountriesByIds called with ids: {}".format(uuid_list_str(ids)))

                query = select(Countries).where(Countries.id.in_(ids))
                result = await session.execute(query)
                rows = result.scalars().all()

                countries = [
                    CountryDetail(
                        id=uuid_str(row.id),
                        name=row.name,
                        slug=row.slug,
                    )
                    for row in rows
                ]

                self.__logger.info(
                    "GetCountriesByIds returning {} records for {} requested ids".format(
                        len(countries), len(ids)
                    )
                )

                return GetCountriesByIdsResponse(
                    message="Success",
                    countries=countries,
                )

        except Exception as exc:
            self.__logger.error(
                "Error in GetCountriesByIds for ids {}: {}".format(ids, exc)
            )
            raise GrpcException(
                details=RPCExceptionMsg.ERROR_MSG,
                status_code=StatusCode.INTERNAL,
            )

    async def GetStatesByIds(self, request, context):
        """
        Accepts a list of state IDs.
        Returns StateDetail (id, name, slug, country_id) for each found state.
        IDs not found in DB are silently omitted from the response.
        """
        ids = parse_uuid_list(request.ids, "ids")

        if not ids:
            raise GrpcException(
                details="ids must be a non-empty list of state IDs",
                status_code=StatusCode.INVALID_ARGUMENT,
            )

        try:
            async with self.__db_session_manager.session() as session:
                self.__logger.info("GetStatesByIds called with ids: {}".format(uuid_list_str(ids)))

                query = select(States).where(States.id.in_(ids))
                result = await session.execute(query)
                rows = result.scalars().all()

                states = [
                    StateDetail(
                        id=uuid_str(row.id),
                        name=row.name,
                        slug=row.slug,
                        country_id=uuid_str(row.country_id),
                    )
                    for row in rows
                ]

                self.__logger.info(
                    "GetStatesByIds returning {} records for {} requested ids".format(
                        len(states), len(ids)
                    )
                )

                return GetStatesByIdsResponse(
                    message="Success",
                    states=states,
                )

        except Exception as exc:
            self.__logger.error(
                "Error in GetStatesByIds for ids {}: {}".format(ids, exc)
            )
            raise GrpcException(
                details=RPCExceptionMsg.ERROR_MSG,
                status_code=StatusCode.INTERNAL,
            )

    async def GetCitiesByIds(self, request, context):
        """
        Accepts a list of city IDs.
        Returns CityDetail (id, name, slug, state_id) for each found city.
        IDs not found in DB are silently omitted from the response.
        """
        ids = parse_uuid_list(request.ids, "ids")

        if not ids:
            raise GrpcException(
                details="ids must be a non-empty list of city IDs",
                status_code=StatusCode.INVALID_ARGUMENT,
            )

        try:
            async with self.__db_session_manager.session() as session:
                self.__logger.info("GetCitiesByIds called with ids: {}".format(uuid_list_str(ids)))

                query = select(Cities).where(Cities.id.in_(ids))
                result = await session.execute(query)
                rows = result.scalars().all()

                cities = [
                    CityDetail(
                        id=uuid_str(row.id),
                        name=row.name,
                        slug=row.slug,
                        state_id=uuid_str(row.state_id),
                    )
                    for row in rows
                ]

                self.__logger.info(
                    "GetCitiesByIds returning {} records for {} requested ids".format(
                        len(cities), len(ids)
                    )
                )

                return GetCitiesByIdsResponse(
                    message="Success",
                    cities=cities,
                )

        except Exception as exc:
            self.__logger.error(
                "Error in GetCitiesByIds for ids {}: {}".format(ids, exc)
            )
            raise GrpcException(
                details=RPCExceptionMsg.ERROR_MSG,
                status_code=StatusCode.INTERNAL,
            )

    async def GetCountriesByNames(self, request, context):
        """
        Accepts a list of country name strings.
        Matching is case-insensitive with leading/trailing whitespace stripped.
        Names not found in DB are silently omitted from the response.
        """
        raw_names = list(request.names)
        if not raw_names:
            raise GrpcException(
                details="names must be a non-empty list of country name strings",
                status_code=StatusCode.INVALID_ARGUMENT,
            )
        normalized_names = [n.strip().lower() for n in raw_names]
        try:
            async with self.__db_session_manager.session() as session:
                self.__logger.info(
                    "GetCountriesByNames called with names: {}".format(raw_names)
                )
                query = select(Countries).where(
                    func.lower(func.trim(Countries.name)).in_(normalized_names)
                )
                result = await session.execute(query)
                rows = result.scalars().all()
                countries = [
                    CountryDetail(id=uuid_str(row.id), name=row.name, slug=row.slug)
                    for row in rows
                ]
                self.__logger.info(
                    "GetCountriesByNames returning {} records for {} requested names".format(
                        len(countries), len(raw_names)
                    )
                )
                return GetCountriesByNamesResponse(
                    message="Success", countries=countries
                )
        except Exception as exc:
            self.__logger.error(
                "Error in GetCountriesByNames for names {}: {}".format(raw_names, exc)
            )
            raise GrpcException(
                details=RPCExceptionMsg.ERROR_MSG, status_code=StatusCode.INTERNAL
            )

    async def GetStatesByNames(self, request, context):
        """
        Accepts a list of state name strings.
        Matching is case-insensitive with leading/trailing whitespace stripped.
        If country_ids is provided, results are filtered to those countries only —
        used to disambiguate states with identical names across countries.
        """
        raw_names = list(request.names)
        country_ids = parse_uuid_list(request.country_ids, "country_ids")
        if not raw_names:
            raise GrpcException(
                details="names must be a non-empty list of state name strings",
                status_code=StatusCode.INVALID_ARGUMENT,
            )
        normalized_names = [n.strip().lower() for n in raw_names]
        try:
            async with self.__db_session_manager.session() as session:
                self.__logger.info(
                    "GetStatesByNames called with names: {}, country_ids: {}".format(
                        raw_names, uuid_list_str(country_ids)
                    )
                )
                query = select(States).where(
                    func.lower(func.trim(States.name)).in_(normalized_names)
                )
                if country_ids:
                    query = query.where(States.country_id.in_(country_ids))
                result = await session.execute(query)
                rows = result.scalars().all()
                states = [
                    StateDetail(
                        id=uuid_str(row.id),
                        name=row.name,
                        slug=row.slug,
                        country_id=uuid_str(row.country_id),
                    )
                    for row in rows
                ]
                self.__logger.info(
                    "GetStatesByNames returning {} records for {} requested names".format(
                        len(states), len(raw_names)
                    )
                )
                return GetStatesByNamesResponse(message="Success", states=states)
        except Exception as exc:
            self.__logger.error(
                "Error in GetStatesByNames for names {}: {}".format(raw_names, exc)
            )
            raise GrpcException(
                details=RPCExceptionMsg.ERROR_MSG, status_code=StatusCode.INTERNAL
            )

    async def GetCitiesByNames(self, request, context):
        """
        Accepts a list of city name strings.
        Matching is case-insensitive with leading/trailing whitespace stripped.
        If state_ids is provided, results are filtered to those states only —
        used to disambiguate cities with identical names across states.
        """
        raw_names = list(request.names)
        state_ids = parse_uuid_list(request.state_ids, "state_ids")
        if not raw_names:
            raise GrpcException(
                details="names must be a non-empty list of city name strings",
                status_code=StatusCode.INVALID_ARGUMENT,
            )
        normalized_names = [n.strip().lower() for n in raw_names]
        try:
            async with self.__db_session_manager.session() as session:
                self.__logger.info(
                    "GetCitiesByNames called with names: {}, state_ids: {}".format(
                        raw_names, uuid_list_str(state_ids)
                    )
                )
                query = select(Cities).where(
                    func.lower(func.trim(Cities.name)).in_(normalized_names)
                )
                if state_ids:
                    query = query.where(Cities.state_id.in_(state_ids))
                result = await session.execute(query)
                rows = result.scalars().all()
                cities = [
                    CityDetail(
                        id=uuid_str(row.id),
                        name=row.name,
                        slug=row.slug,
                        state_id=uuid_str(row.state_id),
                    )
                    for row in rows
                ]
                self.__logger.info(
                    "GetCitiesByNames returning {} records for {} requested names".format(
                        len(cities), len(raw_names)
                    )
                )
                return GetCitiesByNamesResponse(message="Success", cities=cities)
        except Exception as exc:
            self.__logger.error(
                "Error in GetCitiesByNames for names {}: {}".format(raw_names, exc)
            )
            raise GrpcException(
                details=RPCExceptionMsg.ERROR_MSG, status_code=StatusCode.INTERNAL
            )

    async def GetAllRoles(
        self,
        request,
        context,
        auth_repository: AuthRepository = Depends(Provide["auth_repository"]),
    ):
        """
        Return all active, non-deleted roles.

        Called with an empty GetAllRolesRequest — no filter parameters.
        The caller fetches the full list and validates locally
        rather than making repeated per-ID calls.

        Response fields:
            message (str): "Success".
            roles (repeated RoleDetail): All active roles, each with
                id, name, slug, hierarchy, is_internal, is_active.

        Errors:
            INTERNAL: Unexpected DB error.
        """
        self.__logger.info("GetAllRoles called")

        try:

            role_dicts = await auth_repository.get_all_roles(is_internal_partner=False)

            role_details = [
                RoleDetail(
                    id=uuid_str(r["id"]),
                    name=r["name"],
                    slug=r["slug"],
                    hierarchy=r["hierarchy"],
                    is_internal=r["is_internal"],
                    is_active=r["is_active"],
                    data_scope=r["data_scope"],
                )
                for r in role_dicts
            ]

            self.__logger.info(
                "GetAllRoles returning {} roles".format(len(role_details))
            )

            return GetAllRolesResponse(
                message="Success",
                roles=role_details,
            )

        except Exception as exc:
            self.__logger.error("GetAllRoles unexpected error: {}".format(exc))
            await context.abort(StatusCode.INTERNAL, "Internal error fetching roles")

