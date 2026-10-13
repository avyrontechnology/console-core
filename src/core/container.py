"""Containers module."""

from dependency_injector import containers, providers

from src.components.api_key.repositories import ApiKeyRepository
from src.components.api_key.services import ApiKeyService
from src.components.api_logs.repositories import APILogRepository
from src.components.api_logs.services import APILogService
from src.components.audit_log.repositories import AuditLogRepository
from src.components.audit_log.services import AuditService
from src.components.auth.repositories import AuthRepository
from src.components.auth.service import AuthService
from src.components.auth.util import AuthUtility
from src.components.cache.helper import CacheHelper
from src.components.db_constants.repositories import ConstantsRepository
from src.components.db_constants.services import ConstantsService
from src.components.default_role_permission.repositories import (
    DefaultRolePermissionRepository,
)
from src.components.default_role_permission.services import DefaultRolePermissionService
from src.components.entitlement.repositories import EntitlementRepository
from src.components.entitlement.services import EntitlementService
from src.components.grace.repositories import GraceRepository
from src.components.grace.services import GraceService
from src.components.location.repositories import LocationRepository
from src.components.location.services import LocationService
from src.components.notifications.channels.fcm_channel import FCMChannel
from src.components.notifications.factory import NotificationChannelFactory
from src.components.notifications.repositories import NotificationRepository
from src.components.notifications.services import NotificationService
from src.components.order.repositories import OrderRepository
from src.components.order.services import OrderService
from src.components.partner.partner_filter_service import PartnerFilterService
from src.components.partner.repositories import PartnerRepository
from src.components.partner.services import PartnerService
from src.components.partner_address.repositories import AddressRepository
from src.components.partner_address.services import PartnerAddressService
from src.components.partner_config.repositories import PartnerConfigRepository
from src.components.partner_config.services import PartnerConfigService
from src.components.partner_db_config.services import PartnerDBConfigService
from src.components.partner_home_page.repositories import PartnerHomePageRepositories
from src.components.partner_home_page.services import PartnerHomePageService
from src.components.partner_meta_data.repositories import PartnerMetaDataRepository
from src.components.partner_meta_data.services import PartnerMetaDataServices
from src.components.partner_role_permission.repositories import (
    PartnerPermissionRepository,
)
from src.components.partner_role_permission.service import PartnerPermissionService
from src.components.partner_role.repositories import PartnerRoleRepository
from src.components.partner_role.service import PartnerRoleService
from src.components.payment.repositories import PaymentRepository
from src.components.payment.services import PaymentService
from src.components.plan.repositories import PlanRepository
from src.components.plan.services import PlanService
from src.components.release_note.repositories import ReleaseNotesRepository
from src.components.release_note.services import ReleaseNotesService
from src.components.session_mangement.repositories import UserSessionRepository
from src.components.session_mangement.services import UserSessionService
from src.components.user.filter_service import FilterService
from src.components.user.repositories import UserRepository
from src.components.user.services import UserService
from src.components.user_config.repositories import UserConfigRepository
from src.components.user_config.services import UserConfigService
from src.components.user_metadata.repositories import UserMetadataRepository
from src.components.user_metadata.services import UserMetadataService
from src.components.user_tracker.repositories import UserTrackerRepository
from src.components.user_tracker.services import UserTrackerService
from src.components.wallet.repository import WalletRepository
from src.components.wallet.services import WalletService
from src.config import settings
from src.core.app_env import AppEnvironment
from src.core.db import DatabaseSessionManager
from src.core.environment import ENV
from src.core.mongo_db import MongoDatabaseSessionManager
from src.core.redis import RedisCache
from src.loggers.console_service_logger import ConsoleServiceLogger

logger = ConsoleServiceLogger.get_logger()


class Container(containers.DeclarativeContainer):

    # @staticmethod
    # def __get_config():
    #     return providers.Configuration(json_files=[])

    @staticmethod
    def __add_wiring():
        return containers.WiringConfiguration(
            modules=[
                "..middlewares.allowed_hosts",
                "..components.auth.rpc",
                "..components.user.controllers",
                "..components.user.repositories",
                "..components.user.filter_service",
                "..components.auth.controller",
                "..components.auth.repositories",
                "..components.partner.controllers",
                "..components.partner.repositories",
                "..components.partner.partner_filter_service",
                "..components.partner_role_permission.controller",
                "..components.partner_role_permission.repositories",
                "..components.partner_role.controllers",
                "..components.partner_role.repositories",
                "..components.partner_role.service",
                "..middlewares.authentication",
                "..components.partner_meta_data.controller",
                "..components.partner_meta_data.repositories",
                "..components.partner_address.repositories",
                "..components.partner_address.controllers",
                "..middlewares.logging_request_and_response",
                "..components.user_metadata.controllers",
                "..components.user_metadata.repositories",
                "..components.session_mangement.repositories",
                "..components.release_note.controllers",
                "..components.db_constants.controllers",
                "..components.db_constants.repositories",
                "..components.auth.rpc",
                "..components.location.controllers",
                "..components.partner_home_page.repositories",
                "..components.partner_home_page.services",
                "..components.partner_home_page.controllers",
                "..components.partner_config.repositories",
                "..components.partner_config.services",
                "..components.partner_config.controllers",
                "..components.default_role_permission.repositories",
                "..components.default_role_permission.services",
                "..components.default_role_permission.controllers",
                "..components.user_config.controllers",
                "..components.user_config.repositories",
                "..components.partner_meta_data.rpc",
                "..components.user.rpc",
                "..components.payment.controllers",
                "..components.api_key.controllers",
                "..components.api_key.rpc",
                "..components.wallet.controllers",
                "..components.wallet.rpc",
                "..components.api_logs.controllers",
                "..components.api_logs.services",
                "..components.api_logs.repositories",
                "..components.plan.repositories",
                "..components.entitlement.repositories",
                "..components.order.repositories",
                "..components.plan.services",
                "..components.entitlement.services",
                "..components.order.services",
                "..components.plan.controllers",
                "..components.order.controllers",
                "..components.entitlement.controllers",
                "..components.user_config.services",
                "..components.session_mangement.controllers",
                "..components.order.tasks",
                "..components.entitlement.tasks",
                "..components.common.controllers",
                "..components.grace.controllers",
                "..components.user_tracker.controllers",
                "..components.user_tracker.repositories",
                "..components.user_tracker.services",
                "..components.notifications.tasks",
                "..components.notifications.services",
                "..components.notifications.listeners",
                "..components.notifications.factory",
                "..components.notifications.controllers",
                "..components.grace.tasks",
                "..components.user.tasks",
                "..components.wallet.tasks",
                "..components.partner_db_config.controllers"
            ]
        )

    wiring_config = __add_wiring()
    console_service_logger = providers.Singleton(ConsoleServiceLogger)

    auth_service_utility = providers.Factory(
        AuthUtility,
        console_service_logger=console_service_logger,
    )

    db = providers.Singleton(
        DatabaseSessionManager,
        "postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}{ssl}".format(
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
        ),
        {"echo": settings.echo_sql},
    )

    mongo_db = providers.Singleton(
        MongoDatabaseSessionManager, logger=console_service_logger
    )

    release_notes_repository = providers.Factory(
        ReleaseNotesRepository,
        session_factory=db.provided.session,
    )

    release_notes_service = providers.Factory(
        ReleaseNotesService,
        release_notes_repository=release_notes_repository,
    )

    redis_pool = providers.Resource(
        RedisCache.init_redis_pool,
    )

    cache_helper = providers.Singleton(
        CacheHelper,
        redis_pool=redis_pool,
        console_service_logger=console_service_logger,
    )

    cache_helper = providers.Singleton(
        CacheHelper,
        redis_pool=redis_pool,
        console_service_logger=console_service_logger,
    )

    user_repository = providers.Factory(
        UserRepository,
        console_service_logger=console_service_logger,
        session_factory=db.provided.session,
    )

    partner_repository = providers.Factory(
        PartnerRepository,
        session_factory=db.provided.session,
        console_service_logger=console_service_logger,
    )

    address_repository = providers.Factory(
        AddressRepository,
        session_factory=db.provided.session,
        console_service_logger=console_service_logger,
    )

    audit_log_repository = providers.Factory(
        AuditLogRepository,
        session_factory=db.provided.session,
    )

    auth_repository = providers.Factory(
        AuthRepository,
        session_factory=db.provided.session,
    )

    partner_meta_data_repository = providers.Factory(
        PartnerMetaDataRepository,
        session_factory=db.provided.session,
    )

    partner_perm_repository = providers.Factory(
        PartnerPermissionRepository,
        session_factory=db.provided.session,
    )
    user_session_repository = providers.Factory(
        UserSessionRepository,
        session_factory=db.provided.session,
    )

    audit_service = providers.Factory(
        AuditService,
        audit_log_repository=audit_log_repository,
    )

    constants_repository = providers.Factory(
        ConstantsRepository,
        session_factory=db.provided.session,
        console_service_logger=console_service_logger,
    )

    constants_service = providers.Factory(
        ConstantsService,
        constants_repository=constants_repository,
        console_service_logger=console_service_logger,
        audit_service=audit_service,
    )


    partner_role_perm_service = providers.Factory(
        PartnerPermissionService,
        console_service_logger=console_service_logger,
        partner_perm_repository=partner_perm_repository,
        audit_service=audit_service,
    )

    console_service = providers.Factory(
        UserService,
        user_repository=user_repository,
        console_service_logger=console_service_logger,
        console_service_cache=cache_helper,
        audit_service=audit_service,
        auth_service_utility=auth_service_utility,
        session_factory=db.provided.session,
    )

    partner_service = providers.Factory(
        PartnerService,
        partner_repository=partner_repository,
        console_service_logger=console_service_logger,
        partner_service_cache=cache_helper,
        audit_service=audit_service,
    )


    address_service = providers.Factory(
        PartnerAddressService,
        address_repository=address_repository,
        console_service_logger=console_service_logger,
        audit_service=audit_service,
        partner_address_service_cache=cache_helper,
    )

    partner_meta_data_service = providers.Factory(
        PartnerMetaDataServices,
        partner_meta_data_repository=partner_meta_data_repository,
        console_service_logger=console_service_logger,
        audit_service=audit_service,
    )
    user_session_service = providers.Factory(
        UserSessionService,
        user_session_repository=user_session_repository,
        console_service_logger=console_service_logger,
        user_session_service_cache=cache_helper,
    )

    auth_service = providers.Factory(
        AuthService,
        auth_repository=auth_repository,
        auth_service_logger=console_service_logger,
        auth_service_cache=cache_helper,
        auth_service_utility=auth_service_utility,
        audit_service=audit_service,
        user_session_service=user_session_service,
    )

    user_metadata_repository = providers.Factory(
        UserMetadataRepository,
        session_factory=db.provided.session,
        console_service_logger=console_service_logger,
    )

    user_metadata_service = providers.Factory(
        UserMetadataService,
        user_metadata_repository=user_metadata_repository,
        console_service_logger=console_service_logger,
        audit_service=audit_service,
    )

    location_repository = providers.Factory(
        LocationRepository,
        session_factory=db.provided.session,
        console_service_logger=console_service_logger,
    )

    location_service = providers.Factory(
        LocationService,
        location_repository=location_repository,
        console_service_logger=console_service_logger,
        console_service_cache=cache_helper,
    )

    partner_home_page_repository = providers.Factory(
        PartnerHomePageRepositories,
        session_factory=db.provided.session,
        console_service_logger=console_service_logger,
    )

    partner_home_page_service = providers.Factory(
        PartnerHomePageService,
        partner_home_page_repository=partner_home_page_repository,
        console_service_logger=console_service_logger,
        audit_service=audit_service,
    )

    partner_config_repository = providers.Factory(
        PartnerConfigRepository,
        session_factory=db.provided.session,
        console_service_logger=console_service_logger,
    )

    partner_db_config_service = providers.Factory(
        PartnerDBConfigService,
        partner_config_repository=partner_config_repository,
        console_service_logger=console_service_logger,
    )

    partner_config_service = providers.Factory(
        PartnerConfigService,
        partner_config_repository=partner_config_repository,
        console_service_logger=console_service_logger,
        console_service_cache=cache_helper,
    )

    partner_role_repository = providers.Factory(
        PartnerRoleRepository,
        session_factory=db.provided.session,
        console_service_logger=console_service_logger,
    )

    partner_role_service = providers.Factory(
        PartnerRoleService,
        partner_role_repository=partner_role_repository,
        console_service_logger=console_service_logger,
        audit_service=audit_service,
        partner_config_service=partner_config_service,
    )

    default_role_permission_repository = providers.Factory(
        DefaultRolePermissionRepository,
        session_factory=db.provided.session,
        console_service_logger=console_service_logger,
    )

    default_role_permission_service = providers.Factory(
        DefaultRolePermissionService,
        default_role_permission_repository=default_role_permission_repository,
        console_service_logger=console_service_logger,
        audit_service=audit_service,
        partner_config_service=partner_config_service,
    )

    user_config_repository = providers.Factory(
        UserConfigRepository,
        session_factory=db.provided.session,
        console_service_logger=console_service_logger,
    )
    user_config_service = providers.Factory(
        UserConfigService,
        user_config_repository=user_config_repository,
        console_service_logger=console_service_logger,
        console_service_cache=cache_helper,
        user_repository=user_repository,
        audit_service=audit_service,
    )
    filter_service = providers.Factory(
        FilterService,
        user_repository=user_repository,
        console_service_logger=console_service_logger,
    )
    partner_filter_service = providers.Factory(
        PartnerFilterService,
        partner_repository=partner_repository,
        console_service_logger=console_service_logger,
    )

    api_key_repository = providers.Factory(
        ApiKeyRepository,
        session_factory=db.provided.session,
        console_service_logger=console_service_logger,
    )

    api_key_service = providers.Factory(
        ApiKeyService,
        api_key_repository=api_key_repository,
        console_service_logger=console_service_logger,
        cache_helper=cache_helper,
        auth_service=auth_service,
        user_repository=user_repository,
    )

    wallet_repository = providers.Factory(
        WalletRepository,
        session_factory=db.provided.session,
        logger=console_service_logger,
    )

    wallet_service = providers.Factory(
        WalletService,
        wallet_repository=wallet_repository,
        logger=console_service_logger,
    )

    api_log_repository = providers.Factory(
        APILogRepository,
        mongo_db_session=mongo_db,
        logger=console_service_logger,
    )

    api_log_service = providers.Factory(
        APILogService,
        api_log_repository=api_log_repository,
        console_service_logger=console_service_logger,
    )

    plan_repository = providers.Factory(
        PlanRepository,
        session_factory=db.provided.session,
        logger=console_service_logger,
    )

    plan_service = providers.Factory(
        PlanService,
        plan_repository=plan_repository,
        logger=console_service_logger,
    )
    entitlement_repository = providers.Factory(
        EntitlementRepository,
        session_factory=db.provided.session,
        logger=console_service_logger,
    )

    entitlement_service = providers.Factory(
        EntitlementService,
        entitlement_repository=entitlement_repository,
        logger=console_service_logger,
    )

    payment_repository = providers.Factory(
        PaymentRepository,
        session_factory=db.provided.session,
        logger=console_service_logger,
    )

    order_repository = providers.Factory(
        OrderRepository,
        session_factory=db.provided.session,
        logger=console_service_logger,
    )

    # Services
    payment_service = providers.Factory(
        PaymentService,
        repository=payment_repository,
        logger=console_service_logger,
    )

    order_service = providers.Factory(
        OrderService,
        order_repo=order_repository,
        payment_service=payment_service,
        logger=console_service_logger,
    )

    notification_repository = providers.Factory(
        NotificationRepository,
        session_factory=db.provided.session,
        console_service_logger=console_service_logger,
    )

    fcm_notification_channel = providers.Singleton(FCMChannel)

    notification_channel_factory = providers.Factory(
        NotificationChannelFactory,
        fcm_channel=fcm_notification_channel,
        # webhook_channel=webhook_notification_channel
    )

    notification_service = providers.Factory(
        NotificationService,
        notification_repository=notification_repository,
        console_service_logger=console_service_logger,
        user_session_service=user_session_service
    )

    grace_repository = providers.Factory(
        GraceRepository,
        session_factory=db.provided.session,
        logger=console_service_logger,
    )

    grace_service = providers.Factory(
        GraceService,
        grace_repository=grace_repository,
        logger=console_service_logger,
    )
    user_tracker_repository = providers.Factory(
        UserTrackerRepository,
        session_factory=db.provided.session,
        console_service_logger=console_service_logger,
    )

    user_tracker_service = providers.Factory(
        UserTrackerService,
        user_tracker_repository=user_tracker_repository,
        console_service_logger=console_service_logger,
    )
