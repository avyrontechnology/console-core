from uuid import UUID
import copy
import json
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from src.components.audit_log.schema import AuditLogSchema
from src.components.audit_log.services import AuditService
from src.components.common.actions import AuditActions
from src.components.common.resources import Resource
from src.components.user.errors import UserNotFoundError
from src.components.user_metadata.errors import (
    UnauthorizedUserException,
    UserMatadataNotFoundError,
)
from src.components.user_metadata.models import UserMetadata
from src.components.user_metadata.repositories import UserMetadataRepository
from src.components.user_metadata.schema import (
    CreateUserMetaDataSchema,
    UpdateUserMetadataSchema,
    UserMetadataSchema,
)
from src.exceptions import UserMetadataAlreadyExistsException, UserMetadataException
from src.loggers.console_service_logger import ConsoleServiceLogger


class UserMetadataService:

    def __init__(
        self,
        audit_service: AuditService,
        user_metadata_repository: UserMetadataRepository,
        console_service_logger: ConsoleServiceLogger,
    ):
        self.__user_metadata_repository: UserMetadataRepository = (
            user_metadata_repository
        )
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger
        self.__audit_service: AuditService = audit_service

    async def get_user_metadata(self) -> List[UserMetadataSchema]:
        """
        Fetches all user metadata and returns them in a schema format.
        """
        try:
            metadata_list = (
                await self.__user_metadata_repository.get_all_user_metadata()
            )
            if not metadata_list:
                self.__console_service_logger.warning("No user metadata found.")
                raise UserMatadataNotFoundError("No user metadata found.")
            return [
                UserMetadataSchema.model_validate(metadata)
                for metadata in metadata_list
            ]

        except UserMetadataException as ex:
            raise ex

    async def get_user_metadata_by_user_id(self, user_id: UUID):
        self.__console_service_logger.info(
            "Fetching metadata for user_id={}".format(user_id)
        )
        try:
            meta_data = (
                await self.__user_metadata_repository.get_user_metadata_by_user_id(
                    user_id
                )
            )

            return meta_data

        except UserMatadataNotFoundError as ex:
            self.__console_service_logger.warning(
                "User meta data not found for user_id={}: {}".format(user_id, str(ex))
            )
            raise ex

        except Exception as ex:
            self.__console_service_logger.error(
                "Error fetching metadata for user_id={}: {}".format(user_id, str(e))
            )
            raise ex

    async def add_user_metadata(
        self, user_id: UUID, user_metadata: CreateUserMetaDataSchema, current_user: dict
    ) -> UserMetadataSchema:
        """
        Creates user metadata after validating the input.
        """
        try:
            self.__console_service_logger.info(
                "Attempting to add metadata for user_id: {}".format(user_id)
            )

            # Call the repository add method
            new_metadata = await self.__user_metadata_repository.add_user_metadata(
                user_id, user_metadata
            )

            # Log the successful addition of metadata
            self.__console_service_logger.info(
                "Successfully added metadata for user_id: {}".format(user_id)
            )
            log_entry = AuditLogSchema(
                action=AuditActions.create,
                resource=Resource.user_meta_data,
                resource_id=new_metadata.id,
                performed_by=current_user.get("user_id"),
                resource_previous_state=None,
                resource_current_state=str(user_metadata),
                details="The user metadata with id {} is created successfully".format(
                    new_metadata.id
                ),
            )
            await self.__audit_service.log_action(log_entry)
            return new_metadata

        except UserMetadataAlreadyExistsException as ex:
            self.__console_service_logger.error(
                f"Metadata already exists for user_id={user_id}: {str(ex)}"
            )
            raise ex

        except UserNotFoundError as exec:
            self.__console_service_logger.error(
                f"User not found for user_id={user_id}: {str(exec)}"
            )
            raise exec

        except Exception as ex:
            # Log any unexpected exceptions
            self.__console_service_logger.error(
                f"Unexpected error occurred while adding user metadata: {str(ex)}"
            )
            raise ex

    async def update_user_metadata(
        self, current_user: dict, user_id: UUID, user_metadata: UpdateUserMetadataSchema
    ) -> UserMetadataSchema:
        """
        Updates user metadata for a given user ID.
        """
        try:
            # Fetch the existing metadata by its id, not user_id
            existing_user_meta_data = (
                await self.__user_metadata_repository.get_user_metadata_by_user_id(
                    user_id
                )
            )
            resource_previous_state = copy.deepcopy(existing_user_meta_data)

            self.__console_service_logger.info(
                "Attempting to update metadata for user_id: {}".format(user_id)
            )

            # Log before fetching user metadata
            self.__console_service_logger.info(
                "Fetching metadata for user_id: {}".format(user_id)
            )
            metadata = (
                await self.__user_metadata_repository.get_user_metadata_by_user_id(
                    user_id
                )
            )

            if metadata:
                self.__console_service_logger.info(
                    "Fetched metadata: {}".format(metadata)
                )
            else:
                self.__console_service_logger.error(
                    "User ID: {} not found.".format(user_id)
                )
                raise UserNotFoundError(user_id)

            # Proceed with updating the metadata using the id
            updated_metadata: UserMetadata = (
                await self.__user_metadata_repository.update_user_meta_data(
                    user_id=user_id, user_metadata=user_metadata
                )
            )

            resource_previous_state_json = json.dumps(
                resource_previous_state, default=str
            )
            resource_current_state_json = json.dumps(updated_metadata, default=str)
            log_entry = AuditLogSchema(
                action=AuditActions.update,
                resource=Resource.user_meta_data,
                resource_id=updated_metadata.id,
                resource_previous_state=resource_previous_state_json,
                resource_current_state=resource_current_state_json,
                performed_by=current_user.get("user_id"),
                details="The user metadata with id {} is now updated".format(
                    updated_metadata.id
                ),
            )
            await self.__audit_service.log_action(log_entry)
            return updated_metadata

        except UserNotFoundError as ex:
            self.__console_service_logger.error(
                f"User ID: {user_id} not found: {str(ex)}"
            )
            raise ex

        except UserMatadataNotFoundError as ex:
            self.__console_service_logger.error(
                f"User metadata not found for user_id={user_id}."
            )
            raise ex

        except Exception as ex:
            self.__console_service_logger.error(
                f"Unexpected error occurred while updating metadata for user_id={user_id}: {str(ex)}"
            )
            raise ex

    async def delete_user_metadata_by_id(
        self, user_id: UUID, current_user: dict
    ) -> dict:
        """Deletes user metadata for a given user ID."""
        try:
            self.__console_service_logger.info(
                "Attempting to delete metadata for user_id: {}".format(user_id)
            )
            await self.__user_metadata_repository.delete_umetadata_by_user_id(
                current_user, user_id
            )

            # Log the successful deletion
            self.__console_service_logger.info(
                f"Deleted metadata for user_id={user_id}."
            )

            # Create the audit log entry
            log_entry = AuditLogSchema(
                action=AuditActions.delete,
                resource=Resource.user_meta_data,
                resource_id=user_id,
                resource_previous_state=None,
                resource_current_state=None,
                performed_by=current_user.get("user_id"),
                details=f"The user metadata with user id {user_id} is now deleted successfully",
            )
            await self.__audit_service.log_action(log_entry)

        except UnauthorizedUserException as ex:
            self.__console_service_logger.error(f"Unauthorized user: {str(ex)}")
            raise ex

        except UserMatadataNotFoundError as ex:
            self.__console_service_logger.error(
                f" user metadata for User ID: {user_id} not found: {str(ex)}"
            )

            raise ex

        except Exception as ex:
            self.__console_service_logger.error(
                f"Unexpected error occurred while deleting metadata for user_id={user_id}: {str(ex)}"
            )
            raise ex
