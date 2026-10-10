from src.pub.user_pb2 import (
    UserDetail,
    GetPartnerUserDetailsByHierarchyResponse,
    UserAvailabilityStatus,
    GetUsersAvailabilityStatusResponse,
)
from src.pub.user_pb2_grpc import UserServiceServicer
from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from grpc import StatusCode
from grpc_interceptor.exceptions import GrpcException
from typing import Any, List, Optional
from src.components.user.services import UserService
from src.core.container import Container


class UserServiceGRPC(UserServiceServicer):

    def __init__(self, logger):
        self.__logger = logger

    @inject
    async def GetPartnerUserDetailsByHierarchy(
        self,
        request,
        context,
        user_service: UserService = Depends(Provide[Container.console_service]),
    ):
        partner_id = request.partner_id
        role_hierarchy_level = request.role_hierarchy_level

        try:
            self.__logger.info(f"[gRPC]: Attempting to get user details by hierarchy: {role_hierarchy_level}, for partner: {partner_id}")
            users_details = await user_service.get_admin_credentials_by_hierarchy(
                user_hierarchy=role_hierarchy_level, partner_id=partner_id
            )

            response = [
                UserDetail(
                    user_id=user.user_id,
                    email=user.email,
                    name=user.name,
                    role=user.role,
                )
                for user in users_details
            ]

            return GetPartnerUserDetailsByHierarchyResponse(users_details=response)
        except Exception as exc:
            self.__logger.error(f"[gRPC]: Error occurred while get users details by hierarchy: {role_hierarchy_level} for partner: {partner_id}. error: {exc}")
            raise GrpcException(
                details=str(exc),
                status_code=StatusCode.INTERNAL,
            )

    @inject
    async def GetUsersAvailabilityStatus(
        self,
        request,
        context,
        user_service: UserService = Depends(Provide[Container.console_service]),
    ):
        user_ids: List[int] = list(request.user_ids)

        try:
            self.__logger.info(f"[gRPC]: Attempting to get current status for user_ids: {user_ids}")
            users_status: List[Any] = await user_service.get_users_availability_status(
                user_ids
            )

            response: List[UserAvailabilityStatus] = [
                UserAvailabilityStatus(
                    user_id=user.user_id,
                    current_status=user.current_status,
                )
                for user in users_status
            ]

            return GetUsersAvailabilityStatusResponse(users_availability_status=response)
        except Exception as exc:
            self.__logger.error(f"[gRPC]: Error occurred while getting current status for user_ids: {user_ids}. error: {exc}")
            raise GrpcException(
                details=str(exc),
                status_code=StatusCode.INTERNAL,
            )
