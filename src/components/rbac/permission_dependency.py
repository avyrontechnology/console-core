import json

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, HTTPException, Request

from src.components.auth.repositories import AuthRepository
from src.components.auth.util import AuthUtility
from src.components.common.constants import CurrentUserMap
from src.components.partner_config.constants import PartnerConfigEnum
from src.components.partner_config.schemas import PartnerConfigResponse
from src.components.partner_config.services import PartnerConfigService
from src.components.rbac.constant import PermissionErrorText
from src.core.container import Container
from src.core.redis import RedisCache
from src.loggers.console_service_logger import ConsoleServiceLogger
from src.middlewares.utils import MiddlewareUtils


class PermissionDependency:
    """
    This dependency dynamically checks the permission based on its own class name.
    """

    def __init__(self, permission_name: str):
        self.permission_name = permission_name

    @inject
    async def __call__(
        self,
        request: Request,
        auth_repo: AuthRepository = Provide[Container.auth_repository],
        partner_config_service: PartnerConfigService = Depends(
            Provide[Container.partner_config_service]
        ),
        redis_pool: RedisCache = Provide[Container.redis_pool],
        logger: ConsoleServiceLogger = Provide[Container.console_service_logger],
    ):

        logger.debug("checking permission: {}".format(self.permission_name))

        # Skip permission if optional auth endpoint & no user
        if MiddlewareUtils.is_optional_permission_path(request) and not getattr(
            request.state, "user", None
        ):
            logger.info(
                f"Skipping permission check for optional endpoint: {request.url.path}"
            )
            return

        try:
            # current_user is available in request's state (Extracted from the token)
            current_user: dict = await AuthUtility.get_current_user(request)
            current_user_id: int = current_user.get(CurrentUserMap.USER_ID)
            permission_list: list[str] = (
                await partner_config_service.custom_role_permission_check(
                    current_user_id
                )
            )
            logger.info(
                "user-{} have permissions {}".format(current_user_id, permission_list)
            )

            # Check if the required permission is in the user's permissions list
            if self.permission_name not in permission_list:
                logger.error(
                    f"Permission denied: {self.permission_name} not in user's permissions"
                )
                raise HTTPException(
                    status_code=403, detail=PermissionErrorText.PERMISSION_DENIED
                )

            logger.info(
                f"Permission granted for user: {current_user_id} with permission: {self.permission_name}"
            )
            pass
        except HTTPException as http_forbidden:
            raise http_forbidden

        except Exception as exc:
            logger.error(f"Permission check failed: {str(exc)}")
            raise HTTPException(
                status_code=404, detail=PermissionErrorText.INTERNAL_SERVER_ERROR
            )
