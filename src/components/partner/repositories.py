from contextlib import AbstractContextManager
from typing import Any, Callable, List, Optional, Set, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from src.components.common.datetime import DateTimeUtil
from src.components.partner import messages
from src.components.partner.constant import (
    TrialPartnerConstant,
    TrialPartnerExceptionMessage,
)
from src.components.partner.error import InvalidPartnerIdsError, PartnerNotFoundError
from src.components.partner.models import Partner
from src.components.partner.schema import (
    BasePartnerData,
    PartnerOnboardingDetails,
    TogglePartnerActivation,
    UpdatePartnerRequest,
)
from src.components.partner_config.constants import (
    PartnerConfigEnum,
    SubscriptionModeEnum,
)
from src.components.partner_config.models import PartnerConfig
from src.components.partner_meta_data.models import PartnerMetaData
from src.components.user.models import User
from src.components.user_config.models import UserConfig
from src.exceptions import PartnerException
from src.loggers.console_service_logger import ConsoleServiceLogger


class PartnerRepository:

    def __init__(
        self,
        session_factory: Callable[..., AbstractContextManager[Session]],
        console_service_logger: ConsoleServiceLogger,
    ) -> None:
        self.__session_factory: Callable[..., AbstractContextManager[Session]] = (
            session_factory
        )
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger

    async def get_by_id(self, partner_id: int) -> Partner:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Getting partner with id :{}".format(partner_id)
                )
                # Eagerly load the partner_logo to avoid lazy load issues
                result = await session.execute(
                    select(Partner)
                    .options(joinedload(Partner.partner_logo))
                    .filter(Partner.id == partner_id)
                )

                partner = result.scalars().first()
                if not partner or partner.is_active == False:
                    self.__console_service_logger.error(
                        "partner not found, id {}".format(partner_id)
                    )
                    raise PartnerNotFoundError(partner_id)
                self.__console_service_logger.info(
                    "Partner fetched successfully :{}".format(partner.__dict__)
                )
                return partner
        except PartnerNotFoundError as ex:
            raise ex
        except Exception as ex:
            self.__console_service_logger.error(
                "Error while get Partner by id: {}".format(str(ex))
            )
            raise ex

    async def add_partner(self, partner_data: BasePartnerData) -> Partner:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.debug(
                    f"Checking for existing partner with name: {partner_data.name}"
                )
                existing_partner = await session.scalar(
                    select(Partner).where(
                        or_(
                            func.lower(Partner.name) == partner_data.name.lower(),
                            func.lower(Partner.company_legal_name)
                            == partner_data.company_legal_name.lower(),
                        )
                    )
                )

                if existing_partner:
                    is_maglo_publisher = bool(partner_data.is_maglo_publisher)
                    existing_is_maglo_publisher = bool(
                        existing_partner.is_maglo_publisher
                    )
                    self.__console_service_logger.debug(
                        f"Existing partner found: ID={existing_partner.id}, is_maglo_publisher={existing_is_maglo_publisher}"
                    )

                    conflict_field = None
                    if existing_partner.name.lower() == partner_data.name.lower():
                        conflict_field = "name"
                    elif (
                        existing_partner.company_legal_name.lower()
                        == partner_data.company_legal_name.lower()
                    ):
                        conflict_field = "company_legal_name"
                    else:
                        self.__console_service_logger.error(
                            f"No matching field found for existing partner ID {existing_partner.id}"
                        )
                        raise PartnerException(
                            message="no matching field found for existing data: {}".format(
                                existing_partner.id
                            )
                        )
                    is_publisher_conflict = (
                        not is_maglo_publisher and existing_is_maglo_publisher
                    ) or (is_maglo_publisher and existing_is_maglo_publisher)

                    error_message_map = {
                        (True, "name"): messages.PUBLISHER_ALREADY_EXISTS,
                        (False, "name"): messages.PARTNER_ALREADY_EXISTS,
                        (
                            True,
                            "company_legal_name",
                        ): messages.PUBLISHER_COMPANY_LEGAL_NAME_ALREADY_EXISTS,
                        (
                            False,
                            "company_legal_name",
                        ): messages.PARTNER_COMPANY_LEGAL_NAME_ALREADY_EXISTS,
                    }
                    error_message = error_message_map[
                        (is_publisher_conflict, conflict_field)
                    ]

                    self.__console_service_logger.info(
                        f"{'Publisher' if is_publisher_conflict else 'Partner'} with {conflict_field} already exists with ID: {existing_partner.id}"
                    )
                    if not (is_maglo_publisher and not existing_is_maglo_publisher):
                        raise PartnerException(
                            message=error_message, id=existing_partner.id
                        )

                    # Update to maglo publisher
                    self.__console_service_logger.debug(
                        f"Updating partner ID {existing_partner.id} to maglo publisher"
                    )
                    existing_partner.is_maglo_publisher = True
                    await session.commit()
                    await session.refresh(existing_partner)
                    self.__console_service_logger.info(
                        f"Updated partner ID {existing_partner.id} to maglo publisher"
                    )
                    return existing_partner

                # Create new partner
                self.__console_service_logger.debug(
                    f"Creating new partner: {partner_data.model_dump()}"
                )
                partner = Partner(
                    **partner_data.model_dump(
                        exclude_unset=True,
                        exclude={
                            "is_free_trail_enabled",
                            "is_email_verification_enabled",
                            "is_phone_number_verification_enabled",
                            "subscription_mode",
                        },
                    )
                )
                self.__console_service_logger.info(
                    f"Adding partner to the database: {partner.__dict__}"
                )
                session.add(partner)
                await session.flush()
                partner_id: int = partner.id
                self.__console_service_logger.info(
                    f"Generated Partner ID before commit: {partner_id}"
                )
                await session.commit()
                self.__console_service_logger.info(
                    f"Partner with ID {partner_id} is now added to the database"
                )

                email_verification_enabled: bool = bool(
                    partner_data.is_email_verification_enabled
                    if partner_data.is_email_verification_enabled is not None
                    else partner_data.is_free_trail_enabled
                )

                session.add(
                    PartnerConfig(
                        partner_id=partner_id,
                        key=PartnerConfigEnum.IS_EMAIL_VERIFICATION_ENABLED.value,
                        value=email_verification_enabled,
                        is_active=True,
                    )
                )

                session.add(
                    PartnerConfig(
                        partner_id=partner_id,
                        key=PartnerConfigEnum.SUBSCRIPTION_MODE.value,
                        value=partner_data.subscription_mode
                        or SubscriptionModeEnum.SELF_SERVED.value,
                        is_active=True,
                    )
                )

                await session.commit()
                await session.refresh(partner)
                self.__console_service_logger.info(
                    f"Created PartnerConfig for Partner ID {partner_id} with key {PartnerConfigEnum.IS_EMAIL_VERIFICATION_ENABLED.value}"
                )

                return partner
        except IntegrityError as exec:
            self.__console_service_logger.error(
                f"IntegrityError while creating partner: {str(exec)}"
            )
            raise exec
        except PartnerException as px:
            self.__console_service_logger.error(
                f"Error while creating Partner: {str(px)}"
            )
            raise px
        except Exception as ex:
            self.__console_service_logger.error(
                f"Error while creating Partner: {str(ex)}"
            )
            raise

    async def delete_by_id(self, partner_id: int, user_id: int) -> Partner:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "deleting partner with id : {}".format(partner_id)
                )
                query = select(Partner).where(Partner.id == partner_id)
                result = await session.execute(query)
                entity = result.scalars().first()
                if not entity or entity.is_active == False:
                    self.__console_service_logger.error(
                        "Partner not found, id {}".format(partner_id)
                    )
                    raise PartnerNotFoundError(partner_id)

                entity.is_active = False
                entity.is_deleted = True
                entity.deleted_by = user_id
                base_name = entity.name.split("_")[0]
                unique_name = base_name + "_" + str(partner_id)
                entity.name = unique_name
                entity.deleted_at = DateTimeUtil.get_current_time()
                self.__console_service_logger.info(
                    "partner deleted successfully:{}".format(entity.__dict__)
                )
                session.add(entity)
                await session.commit()
                return entity
        except PartnerNotFoundError as ex:
            self.__console_service_logger.error(
                "Error while deleting Partner: {}".format(str(ex))
            )
            raise ex
        except Exception as ex:
            self.__console_service_logger.error(
                "Error while deleting Partner: {}".format(str(ex))
            )
            raise ex

    async def update(
        self,
        user_id: int,
        partner_id: int,
        partner_data=UpdatePartnerRequest,
    ) -> Partner:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Updating partner with id : {}".format(partner_id)
                )
                # Fetch the existing partner
                result = await session.execute(select(Partner).filter_by(id=partner_id))
                partner = result.scalars().first()
                # Update partner details
                partner_updates = partner_data.model_dump(
                    exclude_unset=True
                )  # Convert to dictionary
                for key, value in partner_updates.items():
                    setattr(
                        partner, key, value
                    )  # Use setattr to update fields dynamically

                partner.updated_by = user_id

                self.__console_service_logger.info(
                    "Updating partner in the database: {}".format(partner.__dict__)
                )
                await session.commit()
                await session.refresh(partner)
                return partner

        except IntegrityError as ex:
            self.__console_service_logger.error(
                "IntegrityError while creating partner: {}".format(str(ex))
            )
            await session.rollback()
            raise ex
        except Exception as ex:
            self.__console_service_logger.error(
                "Error while updating Partner: {}".format(str(ex))
            )
            raise ex

    async def update_partner_logo(
        self,
        partner_id: int,
        partner_logo_id: int,
        user_id: int,
    ) -> Partner:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Updating logo for partner_id: {}".format(partner_id)
                )

                result = await session.execute(select(Partner).filter_by(id=partner_id))
                partner = result.scalars().first()

                if not partner:
                    raise PartnerNotFoundError(
                        "Partner not found with id: {}".format(partner_id)
                    )

                partner.partner_logo_id = partner_logo_id
                partner.updated_by = user_id

                await session.commit()
                await session.refresh(partner)
                return partner
        except PartnerNotFoundError as ex:
            self.__console_service_logger.error(
                "Error while updating partner logo: {}".format(str(ex))
            )
            raise ex
        except Exception as ex:
            self.__console_service_logger.error(
                "Error while updating partner logo: {}".format(str(ex))
            )
            raise ex

    async def change_partner_status(
        self,
        partner_id: int,
        status: Optional[str],
        is_feedback_enabled: Optional[bool],
    ) -> Optional[Partner]:
        """
        Update the status and/or is_feedback_enabled flag of a partner in the database.

        Args:
            partner_id: ID of the partner to update.
            status: New status for the partner (optional).
            is_feedback_enabled: New value for the is_feedback_enabled flag (optional).

        Returns:
            Optional[Partner]: The updated Partner object, or None if not found.
        """
        self.__console_service_logger.info(
            f"Updating partner_id={partner_id} with status={status}, is_feedback_enabled={is_feedback_enabled}"
        )
        async with self.__session_factory() as session:
            try:
                # Fetch the partner
                stmt = select(Partner).where(
                    Partner.id == partner_id, Partner.is_active.is_(True)
                )
                result = await session.execute(stmt)
                partner = result.scalar_one_or_none()

                if status is not None:
                    partner.partner_status = status
                if is_feedback_enabled is not None:
                    partner.is_feedback_enabled = is_feedback_enabled

                await session.commit()
                await session.refresh(partner)
                self.__console_service_logger.info(
                    f"Partner_id={partner_id} updated successfully"
                )
                return partner
            except Exception as exc:
                self.__console_service_logger.error(
                    f"Error updating partner_id={partner_id}: {exc}"
                )
                await session.rollback()
                raise

    async def onboard_partner(self, partner_data: PartnerOnboardingDetails) -> Partner:
        try:
            async with self.__session_factory() as session:
                partner_details = partner_data.partner_details
                partner_meta_data_details = partner_data.partner_meta_data
                user_details = partner_data.user_details
                # Step 1: Create Partner
                self.__console_service_logger.debug(
                    f"Creating new partner: {partner_details.model_dump()}"
                )
                partner = Partner(
                    **partner_details.model_dump(exclude_unset=True),
                    active_license=TrialPartnerConstant.ALLOWED_USER,
                )
                session.add(partner)
                await session.flush()

                self.__console_service_logger.info(
                    f"Generated Partner ID before commit: {partner.id}"
                )

                # Step 2: Create PartnerMetaData linked to Partner
                partner_meta_data = PartnerMetaData(
                    **partner_meta_data_details.model_dump(
                        exclude_unset=True,
                        exclude={
                            "is_maglo_free_trial_enabled",
                            "is_talko_free_trial__enabled",
                            "is_babbler_free_trial__enabled",
                            "is_email_verification_enabled",
                            "is_phone_number_verification_enabled",
                            "is_maglo_app_free_trail_enabled",
                            "subscription_mode",
                        },
                    ),
                    partner_id=partner.id,
                )
                session.add(partner_meta_data)

                # Step 3: Create User linked to Partner
                user = User(
                    **user_details.model_dump(exclude_unset=True, exclude={"password"}),
                    partner_id=partner.id,
                )
                session.add(user)

                await session.flush()
                trial_flags: dict = {
                    "is_maglo_enabled": partner_meta_data_details.is_maglo_free_trial_enabled,
                    "is_talko_enabled": partner_meta_data_details.is_talko_free_trial__enabled,
                    "is_babbler_enabled": partner_meta_data_details.is_babbler_free_trial__enabled,
                    "is_maglo_app_enabled": partner_meta_data_details.is_maglo_app_free_trail_enabled,
                }

                for key, enabled in trial_flags.items():
                    if enabled:
                        session.add(UserConfig(key=key, value=True, user_id=user.id))

                session.add(
                    PartnerConfig(
                        partner_id=partner.id,
                        key=PartnerConfigEnum.IS_EMAIL_VERIFICATION_ENABLED.value,
                        value=partner_meta_data_details.is_email_verification_enabled,
                        is_active=True,
                    )
                )

                session.add(
                    PartnerConfig(
                        partner_id=partner.id,
                        key=PartnerConfigEnum.SUBSCRIPTION_MODE.value,
                        value=partner_meta_data_details.subscription_mode
                        or SubscriptionModeEnum.SELF_SERVED.value,
                        is_active=True,
                    )
                )

                await session.commit()
                await session.refresh(partner)
                self.__console_service_logger.info(
                    "Partner with ID {} successfully onboarded and PartnerConfig '{}' created".format(
                        partner.id,
                        PartnerConfigEnum.IS_EMAIL_VERIFICATION_ENABLED.value,
                    )
                )
                return partner

        except Exception as exc:
            await session.rollback()
            self.__console_service_logger.error(
                f"Error while creating Partner: {str(exc)}"
            )
            raise exc

    async def check_partner_free_trial_eligible(
        self, partner_data: PartnerOnboardingDetails
    ) -> bool:
        async with self.__session_factory() as session:
            self.__console_service_logger.info("Checking partner and user are eligable")
            partner_details = partner_data.partner_details
            user_details = partner_data.user_details

            # Check Partner Uniqueness
            partner_eligible_check = [
                Partner.name == partner_details.name,
                Partner.company_legal_name == partner_details.company_legal_name,
            ]

            if partner_details.cin_no:
                partner_eligible_check.append(Partner.cin_no == partner_details.cin_no)
            if partner_details.gst_no:
                partner_eligible_check.append(Partner.gst_no == partner_details.gst_no)

            partner_eligible_query = select(Partner).where(or_(*partner_eligible_check))
            partner_query = await session.execute(partner_eligible_query)
            existing_partner = partner_query.scalars().first()
            if existing_partner:
                self.__console_service_logger.error(
                    "Partner is already exist with details {}".format(partner_details)
                )
                raise PartnerException(TrialPartnerExceptionMessage.PARTNER_EXISTS)

            # Check User Uniqueness
            user_eligible_check = or_(
                User.email == user_details.email,
                User.phone_number == str(user_details.phone_number),
            )

            user_query = await session.execute(select(User).where(user_eligible_check))
            existing_user = user_query.scalars().first()
            if existing_user:
                self.__console_service_logger.info(
                    "User is already exists with same email: {}, or same phone_number: {}".format(
                        user_details.email, user_details.phone_number
                    )
                )
                raise PartnerException(TrialPartnerExceptionMessage.USER_EXISTS)
            return True

    async def execure_partner_filter_query(self, query) -> List[Tuple]:

        async with self.__session_factory() as session:
            try:
                result = await session.execute(query)
                return result.fetchall()
            except SQLAlchemyError as exec:
                self.__console_service_logger.error(
                    "Database error while executing query: {}".format(exec)
                )
                raise exec

    async def execute_partner_filter_scalar_query(self, query) -> Any:
        async with self.__session_factory() as session:
            try:
                result = await session.execute(query)
                return result.scalar()
            except SQLAlchemyError as exec:
                self.__console_service_logger.error(
                    "Database error while executing scalar query: {}".format(exec)
                )
                raise exec

    async def toggle_partner_activation(
        self, partner_id: int, partner_data: TogglePartnerActivation
    ) -> tuple[Any, list[dict[str, Any]]]:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Updating the partner active status to: {}".format(
                        partner_data.is_active
                    )
                )
                result = await session.execute(select(Partner).filter_by(id=partner_id))
                partner = result.scalars().first()
                if not partner:
                    self.__console_service_logger.error(
                        "Partner not found with id: {}".format(partner_id)
                    )
                    raise PartnerNotFoundError(partner_id)
                users_query = select(User).where(
                    User.partner_id == partner_id, User.is_active == True
                )
                user_query_result = await session.execute(users_query)
                users = user_query_result.scalars().all()
                users_data = [{"id": user.id} for user in users]
                for key, value in partner_data.dict().items():
                    setattr(partner, key, value)
                partner.is_deleted = not partner_data.is_active
                await session.commit()
                await session.refresh(partner)
                return partner.is_active, users_data
        except PartnerNotFoundError as exec:
            self.__console_service_logger.error(
                "Partner not found error occured while updating the active status of partner id: {}".format(
                    partner_id
                )
            )
            raise exec
        except Exception as exec:
            self.__console_service_logger.error(
                "An unexpected error occured while updating the active status of partner id: {}".format(
                    partner_id
                )
            )
            raise exec

    async def validate_partner_ids(self, partner_ids: List[int]) -> None:
        if not partner_ids:
            return

        async with self.__session_factory() as session:
            try:
                stmt = select(Partner.id).where(
                    Partner.id.in_(partner_ids),
                    Partner.is_active.is_(True),
                )
                result = await session.execute(stmt)
                valid_ids: Set[int] = {row[0] for row in result.fetchall()}

                invalid_ids = set(partner_ids) - valid_ids
                if invalid_ids:
                    self.__console_service_logger.warning(
                        f"Invalid partner IDs detected: {invalid_ids}"
                    )
                    raise InvalidPartnerIdsError(sorted(invalid_ids))

            except InvalidPartnerIdsError:
                raise
            except Exception as ex:
                self.__console_service_logger.error(
                    f"Error while validating partner IDs {partner_ids}: {str(ex)}"
                )
                raise
