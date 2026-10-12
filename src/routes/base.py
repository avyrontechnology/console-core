from fastapi import APIRouter

from src.components.api_key.controllers import ApiKeysController
from src.components.auth.controller import AuthController
from src.components.common.controllers import AppConfigController
from src.components.default_role_permission.controllers import (
    DefaultRolePermissionController,
)
from src.components.location.controllers import LocationController
from src.components.partner_address.controllers import PartnerAddressController
from src.components.partner_config.controllers import PartnerConfigController
from src.components.partner_db_config.controllers import PartnerDBConfigController
from src.components.partner_home_page.controllers import PartnerHomePageController
from src.components.partner_meta_data.controller import PartnerMetaDataController
from src.components.partner_role_permission.controller import (
    PartnerPermissionController,
)
from src.components.release_note.controllers import ReleaseNoteController
from src.components.session_mangement.controllers import UserSessionController
from src.components.team.controllers import TeamController
from src.components.partner_role.controllers import PartnerRoleController

from ..components.api_logs.controllers import ApiLogsController
from ..components.db_constants.controllers import ConstantsController
from ..components.entitlement.controllers import EntitlementController
from ..components.grace.controllers import GraceController
from ..components.order.controllers import OrderController
from ..components.partner.controllers import PartnerController
from ..components.payment.controllers import PaymentController
from ..components.plan.controllers import PlanController
from ..components.user.controllers import UserController
from ..components.user_config.controllers import UserConfigController
from ..components.user_metadata.controllers import UserMetadataController
from src.components.user_tracker.controllers import UserTrackerController
from ..components.wallet.controllers import WalletController
from ..components.notifications.controllers import NotificationController


class Router:
    @staticmethod
    def register_all_routes(router: APIRouter):
        """register all routers here."""
        router.include_router(UserController.user_router, prefix="", tags=["Users"])

        router.include_router(
            PartnerController.partner_router, prefix="", tags=["Partners"]
        )

        router.include_router(AuthController.auth_router, prefix="", tags=["Auth"])
        router.include_router(
            PartnerPermissionController.partner_role_permission_router,
            prefix="",
            tags=["Partner Role Permission"],
        )
        router.include_router(
            TeamController.team_router,
            prefix="",
            tags=["Teams"],
        )
        router.include_router(
            PartnerRoleController.partner_role_router,
            prefix="",
            tags=["Partner Roles"],
        )
        router.include_router(
            PartnerAddressController.partner_address_router,
            prefix="",
            tags=["Partner Address"],
        )

        router.include_router(
            PartnerMetaDataController.partner_meta_data_router,
            prefix="",
            tags=["Partner MetaData"],
        )
        router.include_router(
            UserMetadataController.user_metadata_router,
            prefix="",
            tags=["usermetadata"],
        )

        router.include_router(
            ReleaseNoteController.release_note_router,
            prefix="",
            tags=["Release Notes"],
        )

        router.include_router(
            ConstantsController.constants_router,
            prefix="",
            tags=["Constants"],
        )
        router.include_router(
            AppConfigController.app_config_router,
            prefix="",
            tags=["App Config"],
        )
        router.include_router(
            LocationController.location_router,
            prefix="",
            tags=["Location"],
        )
        router.include_router(
            PartnerHomePageController.partner_home_page_router,
            prefix="",
            tags=["Partner Home Page"],
        )
        router.include_router(
            PartnerConfigController.partner_config_router,
            prefix="",
            tags=["Partner Config"],
        )
        router.include_router(
            DefaultRolePermissionController.default_role_permission_router,
            prefix="",
            tags=["Default Role Permission"],
        )
        router.include_router(
            UserConfigController.user_config_router, prefix="", tags=["User Config"]
        )
        router.include_router(
            PaymentController.payment_router,
            prefix="",
            tags=["Payment"],
        )
        router.include_router(
            ApiKeysController.api_key_router, prefix="", tags=["Api Keys"]
        )
        router.include_router(
            WalletController.wallet_router, prefix="/wallet", tags=["Wallet"]
        )
        router.include_router(
            ApiLogsController.api_log_router, prefix="", tags=["Api Logs"]
        )
        router.include_router(PlanController.plan_router, prefix="", tags=["Plans"])
        router.include_router(OrderController.order_router, prefix="", tags=["Orders"])
        router.include_router(GraceController.grace_router, prefix="", tags=["Grace"])
        router.include_router(
            EntitlementController.entitlement_router, prefix="", tags=["Entitlements"]
        )
        router.include_router(
            UserSessionController.user_session_router,
            prefix="",
            tags=["User session managment"],
        )
        router.include_router(
        UserTrackerController.user_tracker_router,
        prefix="",
        tags=["User Tracker"],
        )

        router.include_router(
            NotificationController.notification_router,
            prefix="",
            tags=["Notification Routes"]
        )

        router.include_router(
            PartnerDBConfigController.partner_db_config_router,
            prefix="",
            tags=["Partner DB Config"],
        )
