from typing import Any, Dict, List, Optional

from src.components.audit_log.schema import AuditLogSchema
from src.components.audit_log.services import AuditService
from src.components.auth.models import Role
from src.components.cache.helper import CacheHelper
from src.components.common.actions import AuditActions
from src.components.common.constants import CurrentUserMap
from src.components.common.resources import Resource
from src.components.partner.models import Partner
from src.components.partner_config.constants import PartnerConfigEnum
from src.components.partner_config.schemas import PartnerConfigResponse
from src.components.partner_config.services import PartnerConfigService
from src.components.partner_role.constants import (
    HIERARCHY_SPACING,
    MAX_PARTNER_HIERARCHY,
    MIN_PARTNER_HIERARCHY,
    PartnerRoleExceptionMsg,
    RolePlacement,
)
from src.components.partner_role.error import (
    PartnerRoleException,
    PartnerRoleNotFoundError,
)
from src.components.partner_role.repositories import PartnerRoleRepository
from src.components.partner_role.schema import (
    CreatePartnerRole,
    PartnerRolePaginatedResponse,
    PartnerRoleResponse,
    UpdatePartnerRole,
)
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerRoleService:
    def __init__(
        self,
        partner_role_repository: PartnerRoleRepository,
        console_service_logger: ConsoleServiceLogger,
        audit_service: AuditService,
        partner_config_service: PartnerConfigService,
        cache_helper: CacheHelper,
    ) -> None:
        self.__repo: PartnerRoleRepository = partner_role_repository
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger
        self.__audit_service: AuditService = audit_service
        self.__partner_config_service: PartnerConfigService = partner_config_service
        self.__cache: CacheHelper = cache_helper

    # ------------------------------ helpers ------------------------------- #

    async def __invalidate_partner_teams_cache(self, partner_id: int) -> None:
        await self.__cache.invalidate_partner_teams_cache(partner_id)

    async def __ensure_enabled(self, partner_id: int) -> None:
        config: Optional[PartnerConfigResponse] = (
            await self.__partner_config_service.get_partner_config_by_key(
                partner_id, PartnerConfigEnum.IS_PARTNER_CUSTOM_ROLES_ENABLED.value
            )
        )
        if not (config and getattr(config, "value", False)):
            raise PartnerRoleException(
                PartnerRoleExceptionMsg.CUSTOM_ROLES_NOT_ENABLED
            )

    @staticmethod
    def __compute_hierarchy(
        roles_sorted: List[Role], reference: Role, placement: RolePlacement
    ) -> Optional[int]:
        """Return a hierarchy integer for a new role next to ``reference`` by
        bisecting the gap, or ``None`` when the gap between two real neighbors
        is exhausted (rebalance can help — caller retries).

        Raises PartnerRoleException immediately, without going through
        rebalance, when ``reference`` has no neighbor in the requested
        direction AND the unbounded fallback would cross
        MIN_PARTNER_HIERARCHY/MAX_PARTNER_HIERARCHY — rebalancing renumbers
        everything but cannot create room beyond the partner's own
        most-senior/most-junior role, so retrying after a rebalance would
        just fail again after wastefully renumbering the whole catalog.
        """
        hierarchies: List[int] = [r.hierarchy for r in roles_sorted]
        ref_h: int = reference.hierarchy
        if placement == RolePlacement.BELOW:
            higher: List[int] = [h for h in hierarchies if h > ref_h]
            if not higher:
                candidate: int = ref_h + HIERARCHY_SPACING
                if candidate > MAX_PARTNER_HIERARCHY:
                    raise PartnerRoleException(
                        PartnerRoleExceptionMsg.NO_ROOM_BELOW.format(reference.name)
                    )
                return candidate
            nxt: int = min(higher)
            mid: int = (ref_h + nxt) // 2
            return None if (mid <= ref_h or mid >= nxt) else mid
        # ABOVE
        lower: List[int] = [h for h in hierarchies if h < ref_h]
        if not lower:
            candidate = ref_h - HIERARCHY_SPACING
            if candidate < MIN_PARTNER_HIERARCHY:
                raise PartnerRoleException(
                    PartnerRoleExceptionMsg.NO_ROOM_ABOVE.format(reference.name)
                )
            return candidate
        prev: int = max(lower)
        mid = (prev + ref_h) // 2
        return None if (mid <= prev or mid >= ref_h) else mid

    async def ensure_partner_catalog(
        self, partner_id: int, current_user: Dict[str, Any]
    ) -> None:
        """Public hook: materialize the partner's catalog (copy-on-customize).

        Internal users may materialize any partner's catalog; external users
        may only materialize their own partner's catalog.
        """
        user_id: int = current_user.get(CurrentUserMap.USER_ID)
        is_internal: bool = bool(current_user.get("is_internal"))
        if not is_internal and partner_id != current_user.get(CurrentUserMap.PARTNER_ID):
            raise PartnerRoleException(PartnerRoleExceptionMsg.UNAUTHORIZED_PARTNER_ACCESS)

        await self.__ensure_enabled(partner_id)
        partner: Optional[Partner] = await self.__repo.get_partner(partner_id)
        if partner is None:
            raise PartnerRoleException(PartnerRoleExceptionMsg.PARTNER_NOT_FOUND)
        if partner.is_internal:
            raise PartnerRoleException(
                PartnerRoleExceptionMsg.INTERNAL_NOT_SUPPORTED
            )
        await self.__repo.materialize_catalog(
            partner_id, bool(partner.is_internal), user_id
        )
        await self.__invalidate_partner_teams_cache(partner_id)

    # ------------------------------ CRUD ---------------------------------- #

    @staticmethod
    def __normalize_name(name: str) -> str:
        return "_".join(name.strip().split())

    @staticmethod
    def __build_slug(normalized_name: str, role_id: int) -> str:
        """Derive a partner role's slug from its own name and id: ``{normalized_name}_{id}``."""
        return "{}_{}".format(normalized_name, role_id)

    async def create_partner_role(
        self, data: CreatePartnerRole, current_user: Dict[str, Any]
    ) -> Role:
        partner_id: int = current_user.get(CurrentUserMap.PARTNER_ID)
        user_id: int = current_user.get(CurrentUserMap.USER_ID)

        await self.__ensure_enabled(partner_id)
        partner: Optional[Partner] = await self.__repo.get_partner(partner_id)
        if partner is None:
            raise PartnerRoleException(PartnerRoleExceptionMsg.PARTNER_NOT_FOUND)
        if partner.is_internal:
            raise PartnerRoleException(
                PartnerRoleExceptionMsg.INTERNAL_NOT_SUPPORTED
            )

        # Copy-on-customize: ensure the partner owns its catalog first.
        await self.__repo.materialize_catalog(
            partner_id, bool(partner.is_internal), user_id
        )

        roles: List[Role] = await self.__repo.get_partner_roles_ordered(partner_id)
        reference: Optional[Role] = next(
            (r for r in roles if r.id == data.reference_role_id), None
        )
        if reference is None:
            raise PartnerRoleException(
                PartnerRoleExceptionMsg.REFERENCE_ROLE_NOT_FOUND
            )

        # Permission source must be one of this partner's roles. Role ids are
        # stable across a rebalance, so validating against the current list is
        # sufficient even if a rebalance renumbers hierarchies below.
        if not any(r.id == data.base_role_id for r in roles):
            raise PartnerRoleException(
                PartnerRoleExceptionMsg.BASE_ROLE_NOT_FOUND
            )

        new_hierarchy: Optional[int] = self.__compute_hierarchy(
            roles, reference, data.placement
        )
        if new_hierarchy is None:
            # Gap exhausted -> rebalance the partner catalog and retry once.
            self.__console_service_logger.info(
                "Rebalancing partner {} role hierarchy (gap exhausted)".format(
                    partner_id
                )
            )
            roles = await self.__repo.rebalance(partner_id, user_id)
            reference = next(
                (r for r in roles if r.id == data.reference_role_id), None
            )
            new_hierarchy = self.__compute_hierarchy(
                roles, reference, data.placement
            )
            if new_hierarchy is None:
                raise PartnerRoleException(
                    "Unable to allocate a hierarchy slot after rebalance."
                )

        normalized_name: str = self.__normalize_name(data.name)
        values: Dict[str, Any] = {
            "name": data.name,
            # Placeholder: Role.slug is NOT NULL and has no default, so a valid
            # value must exist before the initial insert. Replaced below with
            # the real {name}_{id} slug once the row's id is known.
            "slug": normalized_name,
            "description": data.description,
            "hierarchy": new_hierarchy,
            "partner_id": partner_id,
            "data_scope": data.data_scope.value,
            "is_internal": bool(partner.is_internal),
            "base_role_id": data.base_role_id,
        }
        role: Role = await self.__repo.create_role(
            values,
            user_id,
            lambda r: self.__build_slug(normalized_name, r.id),
            base_role_id=data.base_role_id,
        )

        await self.__invalidate_partner_teams_cache(partner_id)
        # A rebalance (above) renumbers the whole catalog's hierarchy, so every
        # assigned user's cached role_hierarchy_level can go stale in maglo.
        await self.__cache.invalidate_role_derived_user_caches()

        await self.__audit_service.log_action(
            AuditLogSchema(
                action=AuditActions.create,
                resource=Resource.role,
                resource_id=role.id,
                resource_current_state=str({**values, "slug": role.slug}),
                performed_by=user_id,
                details="Partner custom role created id: {}".format(role.id),
            )
        )
        return role

    async def list_partner_roles(
        self,
        current_user: Dict[str, Any],
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> PartnerRolePaginatedResponse:
        """Pagination is zero-based and optional: pass both ``limit`` and
        ``offset`` to page (row_offset = offset * limit), or neither to get
        everything."""
        partner_id: int = current_user.get(CurrentUserMap.PARTNER_ID)
        partner: Optional[Partner] = await self.__repo.get_partner(partner_id)
        if partner is None:
            raise PartnerRoleException(PartnerRoleExceptionMsg.PARTNER_NOT_FOUND)

        if await self.__repo.has_partner_roles(partner_id):
            roles, total_count, total_active, total_inactive = (
                await self.__repo.get_partner_roles_paginated(
                    partner_id, limit, offset
                )
            )
        else:
            # Not customized yet -> show the shared defaults that would apply.
            roles, total_count, total_active, total_inactive = (
                await self.__repo.get_default_roles_paginated(
                    bool(partner.is_internal), limit, offset
                )
            )

        return PartnerRolePaginatedResponse(
            total_count=total_count,
            total_active=total_active,
            total_inactive=total_inactive,
            limit=limit,
            offset=offset,
            data=[PartnerRoleResponse.model_validate(r) for r in roles],
        )

    async def update_partner_role(
        self, role_id: int, data: UpdatePartnerRole, current_user: Dict[str, Any]
    ) -> Role:
        partner_id: int = current_user.get(CurrentUserMap.PARTNER_ID)
        user_id: int = current_user.get(CurrentUserMap.USER_ID)

        await self.__ensure_enabled(partner_id)
        role: Optional[Role] = await self.__repo.get_partner_role(role_id, partner_id)
        if role is None:
            raise PartnerRoleNotFoundError(role_id)

        values: Dict[str, Any] = data.model_dump(exclude_unset=True)
        if "data_scope" in values:
            if values["data_scope"] is not None:
                values["data_scope"] = values["data_scope"].value
            else:
                del values["data_scope"]

        updated: Role = await self.__repo.update_role(role_id, values, user_id)
        await self.__invalidate_partner_teams_cache(partner_id)
        # data_scope / hierarchy edits change every assigned user's effective
        # scope, which maglo reads from GRPC_GET_USER_DETAILS / GRPC_GET_USER_ROLE.
        await self.__cache.invalidate_role_derived_user_caches()
        await self.__audit_service.log_action(
            AuditLogSchema(
                action=AuditActions.update,
                resource=Resource.role,
                resource_id=role_id,
                resource_current_state=str(values),
                performed_by=user_id,
                details="Partner custom role updated id: {}".format(role_id),
            )
        )
        return updated

    async def delete_partner_role(self, role_id: int, current_user: Dict[str, Any]) -> None:
        partner_id: int = current_user.get(CurrentUserMap.PARTNER_ID)
        user_id: int = current_user.get(CurrentUserMap.USER_ID)

        await self.__ensure_enabled(partner_id)
        role: Optional[Role] = await self.__repo.get_partner_role(role_id, partner_id)
        if role is None:
            raise PartnerRoleNotFoundError(role_id)

        if await self.__repo.count_users_with_role(role_id) > 0:
            raise PartnerRoleException(PartnerRoleExceptionMsg.ROLE_IN_USE)

        await self.__repo.soft_delete_role(role_id, user_id)
        await self.__invalidate_partner_teams_cache(partner_id)
        await self.__audit_service.log_action(
            AuditLogSchema(
                action=AuditActions.delete,
                resource=Resource.role,
                resource_id=role_id,
                performed_by=user_id,
                details="Partner custom role deleted id: {}".format(role_id),
            )
        )
