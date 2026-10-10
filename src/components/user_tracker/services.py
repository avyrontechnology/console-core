import uuid
from typing import Dict, List, Optional, Set

from src.components.common.constants import CurrentUserMap
from src.components.user_tracker.constants import (
    StandardStatuses,
    UserTrackerResponseMsg,
    UserTrackerValidation,
)
from src.components.user_tracker.errors import (
    CustomStatusAlreadyExistsError,
    CustomStatusValidationError,
    InvalidStatusError,
    UnauthorizedCustomStatusAccessError,
    UserTrackerNotFoundError,
)
from src.components.user_tracker.helpers import can_manage_custom_statuses
from src.components.user_tracker.repositories import UserTrackerRepository
from src.components.user_tracker.schema import (
    CustomStatusAddItem,
    CustomStatusEditItem,
    CustomStatusItem,
    StandardStatusItem,
    UpdateCustomStatusesResponse,
    UpdateUserStatusResponse,
    UserAvailabilityStatusResponse,
)
from src.loggers.console_service_logger import ConsoleServiceLogger


class UserTrackerService:

    def __init__(
        self,
        user_tracker_repository: UserTrackerRepository,
        console_service_logger: ConsoleServiceLogger,
    ) -> None:
        self.__repository = user_tracker_repository
        self.__console_service_logger = console_service_logger

    # ── Helpers ───────────────────────────────────────────────────────────────

    def __validate_status_string(self, status: str) -> str:
        """
        Validate a status string — not empty, min 2, max 50 chars.
        Returns stripped value. Raises CustomStatusValidationError if invalid.
        """
        stripped: str = status.strip() if status else ""
        if not stripped:
            raise CustomStatusValidationError(
                UserTrackerResponseMsg.EMPTY_STATUS_NOT_ALLOWED
            )
        if len(stripped) < UserTrackerValidation.STATUS_MIN_LENGTH:
            raise CustomStatusValidationError(
                UserTrackerResponseMsg.STATUS_TOO_SHORT
            )
        if len(stripped) > UserTrackerValidation.STATUS_MAX_LENGTH:
            raise CustomStatusValidationError(
                UserTrackerResponseMsg.STATUS_TOO_LONG
            )
        return stripped

    def __get_next_display_id(self, existing_data: Dict[str, dict]) -> str:
        """
        Generate next human-readable display_id (custom_1, custom_2, ...).
        Finds the highest existing custom_N number and increments by 1.
        Soft-deleted entries included — display_ids never reused.
        """
        max_n: int = 0
        for entry in existing_data.values():
            display_id: str = entry.get("display_id", "")
            if display_id.startswith("custom_"):
                try:
                    num: int = int(display_id.split("_")[1])
                    if num > max_n:
                        max_n = num
                except (IndexError, ValueError):
                    pass
        return f"custom_{max_n + 1}"

    def __get_active_display_map(self, data: Dict[str, dict]) -> Dict[str, str]:
        """
        From raw DB data {uuid: {display_id, name}},
        return only active (non-empty name) entries as {display_id: name}.
        """
        return {
            entry["display_id"]: entry["name"]
            for entry in data.values()
            if entry.get("name", "").strip()
        }

    def __get_active_status_items(self, data: Dict[str, dict]) -> Dict[str, CustomStatusItem]:
        """
        From raw DB data {uuid: {display_id, name, status_icon}},
        return only active (non-empty name) entries as {display_id: CustomStatusItem}.
        """
        return {
            entry["display_id"]: CustomStatusItem(
                name=entry["name"], status_icon=entry.get("status_icon") or None
            )
            for entry in data.values()
            if entry.get("name", "").strip()
        }

    def __process_single_edit(
        self,
        display_id: str,
        edit_item: CustomStatusEditItem,
        raw_data: Dict[str, dict],
        display_id_to_uuid: Dict[str, str],
        active_names_lower: Set[str],
        fixed_lower: Set[str],
    ) -> None:
        """
        Process a single edit entry — soft-delete, rename, and/or icon update.
        Extracted from update_custom_statuses to reduce cognitive complexity.

        edit_item.is_soft_delete → soft delete (UUID stays, name = "")
        edit_item.is_rename      → rename
        neither                  → name untouched (icon-only edit)

        Raises:
            CustomStatusValidationError    : display_id not found or fixed-name conflict.
            CustomStatusAlreadyExistsError : new name already exists.
        """
        uid: str = display_id_to_uuid.get(display_id, "")
        if not uid:
            raise CustomStatusValidationError(
                f"Custom status '{display_id}' not found."
            )

        old_name: str = raw_data[uid].get("name", "")

        if edit_item.is_soft_delete:
            # Soft delete — name set to "", UUID key preserved in DB
            if old_name:
                active_names_lower.discard(old_name.lower())
            raw_data[uid]["name"] = ""
            return

        if edit_item.is_rename:
            # Rename — validate new name
            cleaned_name: str = self.__validate_status_string(edit_item.name)

            if cleaned_name.lower() in fixed_lower:
                raise CustomStatusValidationError(
                    UserTrackerResponseMsg.FIXED_STATUS_CONFLICT
                )

            # Allow renaming to same name (no-op) — skip duplicate check
            if cleaned_name.lower() != old_name.lower():
                if cleaned_name.lower() in active_names_lower:
                    raise CustomStatusAlreadyExistsError(cleaned_name)
                active_names_lower.discard(old_name.lower())
                active_names_lower.add(cleaned_name.lower())

            raw_data[uid]["name"] = cleaned_name

        if edit_item.status_icon is not None:
            raw_data[uid]["status_icon"] = edit_item.status_icon

    def __process_single_addition(
        self,
        addition_item: CustomStatusAddItem,
        raw_data: Dict[str, dict],
        active_names_lower: Set[str],
        fixed_lower: Set[str],
    ) -> None:
        """
        Process a single addition — validate, generate UUID + display_id, insert.
        Extracted from update_custom_statuses to reduce cognitive complexity.

        Raises:
            CustomStatusValidationError    : empty, too short, too long, fixed-name conflict.
            CustomStatusAlreadyExistsError : name already exists.
        """
        cleaned_name: str = self.__validate_status_string(addition_item.name)

        if cleaned_name.lower() in fixed_lower:
            raise CustomStatusValidationError(
                UserTrackerResponseMsg.FIXED_STATUS_CONFLICT
            )

        if cleaned_name.lower() in active_names_lower:
            raise CustomStatusAlreadyExistsError(cleaned_name)

        # UUID = internal DB key (permanent, collision-proof)
        # display_id = human readable (custom_N, always increments, never reused)
        # raw_data updated before next iteration so display_id increments correctly
        new_uuid: str = str(uuid.uuid4())
        display_id: str = self.__get_next_display_id(raw_data)

        raw_data[new_uuid] = {
            "display_id": display_id,
            "name": cleaned_name,
            "status_icon": addition_item.status_icon,
        }
        active_names_lower.add(cleaned_name.lower())

    # Service methods 

    async def get_user_availability_status(
        self,
        user_id: int,
        partner_id: int,
    ) -> UserAvailabilityStatusResponse:
        """
        Returns current_status (with icon), standard_statuses, and active custom
        statuses — each with a status_icon (null/empty until set). Soft-deleted
        custom entries excluded.

        current_status_icon resolution for a custom status prefers this user's
        own icon override (set via update_user_status) over the partner-wide
        default icon, so one user personalizing their icon never changes what
        other users on the same custom status see.
        """
        try:
            self.__console_service_logger.info(
                f"[UserTrackerService] get_user_availability_status for user_id: {user_id}"
            )
            current_status, status_icon_override = await self.__repository.get_user_current_status(
                user_id
            )
            raw_data: Dict[str, dict] = await self.__repository.get_custom_statuses(partner_id)
            active_items: Dict[str, CustomStatusItem] = self.__get_active_status_items(raw_data)

            current_status_icon: Optional[str] = StandardStatuses.default_icon(current_status)
            if current_status_icon is None:
                if status_icon_override:
                    current_status_icon = status_icon_override
                else:
                    for item in active_items.values():
                        if item.name == current_status:
                            current_status_icon = item.status_icon
                            break

            standard_statuses: List[StandardStatusItem] = [
                StandardStatusItem(name=name, status_icon=StandardStatuses.default_icon(name))
                for name in StandardStatuses.all()
            ]

            return UserAvailabilityStatusResponse(
                current_status=current_status,
                current_status_icon=current_status_icon,
                standard_statuses=standard_statuses,
                custom_statuses=active_items,
            )
        except UserTrackerNotFoundError:
            raise
        except Exception as exc:
            self.__console_service_logger.error(
                f"[UserTrackerService] Error in get_user_availability_status: {exc}"
            )
            raise

    async def is_valid_status(self, partner_id: int, status: str) -> bool:
        """
        Return whether `status` is a standard status or an active custom status
        for this partner. Used by other components (e.g. user profile update)
        to validate a current_status value against user_tracker's status list.
        """
        raw_data: Dict[str, dict] = await self.__repository.get_custom_statuses(partner_id)
        active_map: Dict[str, str] = self.__get_active_display_map(raw_data)
        return status in StandardStatuses.all() + list(active_map.values())

    async def update_user_status(
        self,
        user_id: int,
        partner_id: int,
        new_status: str,
        status_icon: Optional[str] = None,
    ) -> UpdateUserStatusResponse:
        """
        Validates status string then checks against standard + active custom status values.

        Icon behavior: standard statuses are fixed (name and icon both immutable
        — status_icon is ignored for them). For a custom status, status_icon is
        a per-user override — it's stored on this user's own row only, never
        written back to the partner-wide custom status catalog, so setting your
        own icon never changes what other users see for the same custom status.
        When status_icon isn't provided, the partner-wide default icon (set by
        an Admin via update_custom_statuses) is used.
        """
        try:
            self.__console_service_logger.info(
                f"[UserTrackerService] update_user_status for user_id: {user_id}, "
                f"new_status: '{new_status}'"
            )

            cleaned_status: str = self.__validate_status_string(new_status)

            raw_data: Dict[str, dict] = await self.__repository.get_custom_statuses(partner_id)
            active_map: Dict[str, str] = self.__get_active_display_map(raw_data)
            all_valid: List[str] = StandardStatuses.all() + list(active_map.values())

            if cleaned_status not in all_valid:
                raise InvalidStatusError(cleaned_status)

            resolved_icon: Optional[str] = StandardStatuses.default_icon(cleaned_status)
            persisted_icon_override: Optional[str] = None

            if resolved_icon is None:
                # Not a standard status — a custom status. status_icon, if
                # given, is this user's own override (persisted per-user only).
                if status_icon:
                    resolved_icon = status_icon
                    persisted_icon_override = status_icon
                else:
                    for entry in raw_data.values():
                        if entry.get("name") == cleaned_status:
                            resolved_icon = entry.get("status_icon")
                            break

            previous_status: str = await self.__repository.update_user_current_status(
                user_id, cleaned_status, persisted_icon_override
            )

            return UpdateUserStatusResponse(
                previous_status=previous_status,
                updated_status=cleaned_status,
                status_icon=resolved_icon,
            )
        except (CustomStatusValidationError, InvalidStatusError, UserTrackerNotFoundError):
            raise
        except Exception as exc:
            self.__console_service_logger.error(
                f"[UserTrackerService] Error in update_user_status: {exc}"
            )
            raise

    async def update_custom_statuses(
        self,
        current_user: dict,
        partner_id: int,
        updated_by: int,
        edit_custom_statuses: Dict[str, CustomStatusEditItem],
        add_custom_statuses: List[CustomStatusAddItem],
    ) -> UpdateCustomStatusesResponse:
        """
        PUT /user-tracker/custom-status — Admin role only.

        Handles edit, soft-delete, add, and status_icon updates in one call.
        Each operation delegated to helper methods to keep complexity low.

        Edit flow (edit_custom_statuses: {display_id: CustomStatusEditItem}):
          - name=""   → soft delete (UUID stays, name = "")
          - name=None → icon-only edit (name untouched)
          - name=str  → rename (status_icon updated too if provided)

        Add flow (add_custom_statuses: [CustomStatusAddItem, ...]):
          - Validate, generate UUID + display_id, append to raw_data
        """
        try:
            if not can_manage_custom_statuses(current_user):
                self.__console_service_logger.warning(
                    "[UserTrackerService] Forbidden custom status update by "
                    "user_id=%s with hierarchy=%s",
                    current_user.get(CurrentUserMap.USER_ID),
                    current_user.get(CurrentUserMap.ROLE_HIERARCHY_LEVEL),
                )
                raise UnauthorizedCustomStatusAccessError()

            self.__console_service_logger.info(
                f"[UserTrackerService] update_custom_statuses for partner_id: {partner_id}"
            )

            fixed_lower: Set[str] = {status.lower() for status in StandardStatuses.all()}

            # Fetch current raw DB data: {uuid: {display_id, name}}
            raw_data: Dict[str, dict] = await self.__repository.get_custom_statuses(partner_id)

            # Build reverse map: display_id → uuid for edit lookups
            display_id_to_uuid: Dict[str, str] = {
                entry["display_id"]: uid
                for uid, entry in raw_data.items()
            }

            # Collect active names for duplicate checking throughout the operation
            active_names_lower: Set[str] = {
                entry["name"].lower()
                for entry in raw_data.values()
                if entry.get("name", "").strip()
            }

            # Process edits — delegated to helper to reduce complexity
            for display_id, edit_item in edit_custom_statuses.items():
                self.__process_single_edit(
                    display_id=display_id,
                    edit_item=edit_item,
                    raw_data=raw_data,
                    display_id_to_uuid=display_id_to_uuid,
                    active_names_lower=active_names_lower,
                    fixed_lower=fixed_lower,
                )

            # Process additions — delegated to helper to reduce complexity
            for addition_item in add_custom_statuses:
                self.__process_single_addition(
                    addition_item=addition_item,
                    raw_data=raw_data,
                    active_names_lower=active_names_lower,
                    fixed_lower=fixed_lower,
                )

            # Save full updated data back to DB
            saved: Dict[str, dict] = await self.__repository.upsert_custom_statuses(
                partner_id, raw_data, updated_by
            )

            active_items: Dict[str, CustomStatusItem] = self.__get_active_status_items(saved)

            return UpdateCustomStatusesResponse(
                message=UserTrackerResponseMsg.CUSTOM_STATUSES_UPDATED,
                custom_statuses=active_items,
            )

        except (
            CustomStatusValidationError,
            CustomStatusAlreadyExistsError,
            UnauthorizedCustomStatusAccessError,
        ):
            raise
        except Exception as exc:
            self.__console_service_logger.error(
                f"[UserTrackerService] Error in update_custom_statuses: {exc}"
            )
            raise