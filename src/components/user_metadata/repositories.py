from uuid import UUID
from contextlib import AbstractAsyncContextManager
from typing import Callable, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.user.errors import UserNotFoundError
from src.components.user.models import User
from src.components.user_metadata.errors import (
    UnauthorizedUserException,
    UserMatadataNotFoundError,
)
from src.components.user_metadata.models import UserMetadata
from src.components.user_metadata.schema import (
    CreateUserMetaDataSchema,
    UpdateUserMetadataSchema,
    UserMetadataSchema,
)
from src.exceptions import UserMetadataAlreadyExistsException, UserMetadataException
from src.loggers.console_service_logger import ConsoleServiceLogger


class UserMetadataRepository:

    def __init__(
        self,
        session_factory: Callable[..., AbstractAsyncContextManager[AsyncSession]],
        console_service_logger: ConsoleServiceLogger,
    ) -> None:
        self.__session_factory: Callable[
            ..., AbstractAsyncContextManager[AsyncSession]
        ] = session_factory
        self.__console_service_logger: ConsoleServiceLogger = console_service_logger

    async def _check_user_exists(self, session: AsyncSession, user_id: UUID) -> bool:
        """
        Check if the user exists in the User table.
        """
        self.__console_service_logger.info(
            "Checking if user exists with user_id={}".format(user_id)
        )
        result = await session.execute(
            select(User).where(User.id == user_id, User.is_active == True)
        )

        return result.scalar_one_or_none() is not None

    async def _check_metadata_exists(self, session: AsyncSession, user_id: UUID) -> bool:
        """
        Check if metadata already exists for the user in UserMetadata table.
        """
        self.__console_service_logger.info(
            "Checking if metadata exists for user_id={}".format(user_id)
        )
        result = await session.execute(
            select(UserMetadata).where(
                UserMetadata.user_id == user_id, User.is_active == True
            )
        )
        return result.scalars().first() is not None

    async def get_all_user_metadata(self) -> List[UserMetadataSchema]:
        """
        Fetch all user metadata.
        """
        async with self.__session_factory() as session:
            try:
                self.__console_service_logger.info("Fetching all user metadata.")
                active_user_subquery = (
                    select(User.id).filter(User.is_active == True).subquery()
                )
                metadata_list = (
                    (
                        await session.execute(
                            select(UserMetadata).where(
                                UserMetadata.user_id.in_(active_user_subquery)
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                if not metadata_list:
                    self.__console_service_logger.error("User metadata not found")
                    raise UserMatadataNotFoundError("User metadata not found")
                self.__console_service_logger.info(
                    "Fetched all the user metadata successfully"
                )
                return metadata_list

            except UserMatadataNotFoundError as ex:
                self.__console_service_logger.error(
                    "User metadata not found: {}".format(str(ex))
                )
                raise ex

            except Exception as ex:
                self.__console_service_logger.error(
                    "Error fetching all user metadata: {}".format(str(ex))
                )
                raise UserMetadataException(
                    "User metadata not found: {}".format(str(ex))
                )

    async def get_user_metadata_by_user_id(
        self, user_id: UUID
    ) -> Optional[List[UserMetadata]]:
        """
        Fetch metadata by user ID.
        """

        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Fetching metadata for user_id={}".format(user_id)
                )
                query = (
                    select(UserMetadata)
                    .filter(UserMetadata.user_id == user_id)
                    .filter(
                        exists()
                        .where(User.id == user_id)
                        .where(User.is_deleted == False)
                    )
                )

                result = await session.execute(query)
                meta_data = result.scalars().one_or_none()

                if not meta_data:
                    self.__console_service_logger.error(
                        "User ID: {} not found.".format(user_id)
                    )
                    raise UserMatadataNotFoundError(user_id)

                return meta_data

        except UserMatadataNotFoundError as ex:
            self.__console_service_logger.error(
                "User not found for user_id={}: {}".format(user_id, str(ex))
            )
            raise ex

        except Exception as ex:
            self.__console_service_logger.error(
                "Error fetching metadata for user_id={}: {}".format(user_id, str(ex))
            )
            raise ex

    async def add_user_metadata(
        self, user_id: UUID, user_metadata: CreateUserMetaDataSchema
    ) -> UserMetadata:
        """
        Add user metadata after validating the user and checking for duplicate entries.
        """

        try:

            async with self.__session_factory() as session:
                user_exists: bool = await self._check_user_exists(session, user_id)
                if not user_exists:
                    raise UserNotFoundError(user_id)

                # Check for duplicate metadata
                if await self._check_metadata_exists(session, user_id):
                    raise UserMetadataAlreadyExistsException(
                        "Metadata already exists for user_id={}".format(user_id)
                    )

                # Create and save new UserMetadata instance
                user_metadata_dict = user_metadata.model_dump(exclude_unset=True)
                user_metadata_dict.update({"user_id": user_id})
                new_metadata = UserMetadata(**user_metadata_dict)

                session.add(new_metadata)
                await session.commit()
                await session.refresh(new_metadata)
                return new_metadata
        except UserMetadataAlreadyExistsException as exec:
            self.__console_service_logger.error(
                "Metadata already exists for user_id={}: {}".format(user_id, str(exec))
            )
            raise exec

        except UserNotFoundError as ex:
            self.__console_service_logger.error(
                "User ID: {} not found: {}".format(user_id, str(ex))
            )
            raise ex

        except Exception as ex:
            self.__console_service_logger.error(
                "Unexpected error: {} while adding metadata for user_id={}".format(
                    str(ex), user_id
                )
            )
            raise HTTPException("Failed to add metadata for user_id={}".format(user_id))

    async def update_user_meta_data(
        self,
        user_id: UUID,
        user_metadata: UpdateUserMetadataSchema,
    ) -> UserMetadata:
        try:
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting update partner metadata for partner id: {}".format(
                        user_id
                    )
                )

                query = (
                    select(UserMetadata)
                    .filter(UserMetadata.user_id == user_id)
                    .filter(
                        exists()
                        .where(User.id == user_id)
                        .where(User.is_deleted == False)
                    )
                )

                result = await session.execute(query)
                user_meta_data = result.scalars().one_or_none()
                if not user_meta_data:
                    self.__console_service_logger.error(
                        "Error occurred while update user metadata for user id : {} not found".format(
                            user_id
                        )
                    )
                    raise UserMatadataNotFoundError(user_id)

                # check which value get for update
                if user_metadata.meta_value is not None:
                    user_meta_data.meta_value = user_metadata.meta_value

                # Commit the changes to the database
                await session.commit()
                await session.refresh(user_meta_data)
                self.__console_service_logger.info(
                    "Partner metadata updated successfully: {}".format(result)
                )

                return user_meta_data

        except UserMatadataNotFoundError as exec:
            self.__console_service_logger.error(
                "Error occurred while update partner metadata for partner_id {}".format(
                    exec
                )
            )
            raise exec
        except Exception as ex:
            self.__console_service_logger.error(
                "Error occurred while update partner metadata for partner_id {}".format(
                    ex
                )
            )
            raise

    async def delete_umetadata_by_user_id(
        self, current_user: dict, user_id: UUID
    ) -> None:
        """
        Delete metadata by user_id.
        """
        try:
            # Authorization check
            if user_id != current_user["user_id"]:
                raise UnauthorizedUserException(
                    "Unauthorized: Cannot delete metadata for another user."
                )
            async with self.__session_factory() as session:
                self.__console_service_logger.info(
                    "Attempting to delete metadata for user_id={}".format(user_id)
                )
                result = await session.execute(
                    select(UserMetadata).filter_by(user_id=user_id)
                )
                metadata = result.scalars().one_or_none()

                if not metadata:
                    self.__console_service_logger.error(
                        "User ID {} not found.".format(user_id)
                    )
                    raise UserMatadataNotFoundError(user_id)

                await session.delete(metadata)
                await session.commit()
                self.__console_service_logger.info(
                    "Successfully deleted metadata for user_id={}".format(user_id)
                )
        except UnauthorizedUserException as ex:
            self.__console_service_logger.error(
                "Unauthorized access: {}".format(str(ex))
            )
            raise ex
        except UserMatadataNotFoundError as ex:
            self.__console_service_logger.error(
                "Attempted to delete non-existent user ID {}: {}".format(
                    user_id, str(ex)
                )
            )
            raise ex
        except Exception as ex:
            self.__console_service_logger.error(
                "Error deleting metadata for user_id={}: {}".format(user_id, str(ex))
            )
            raise ex
