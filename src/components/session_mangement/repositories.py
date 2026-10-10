from contextlib import AbstractAsyncContextManager
from typing import Callable, Dict, List, Optional, Tuple, Union

from sqlalchemy import select, update, exists
from sqlalchemy.engine import Result
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.auth.constant import TokenKeys
from src.components.session_mangement.models import UserSession
from src.components.user.models import User
from src.components.user_config.models import UserConfig

class UserSessionRepository:
    """Repository for handling CRUD operations for the UserSession model."""

    def __init__(
        self, session_factory: Callable[..., AbstractAsyncContextManager[AsyncSession]]
    ) -> None:
        self.__session_factory = session_factory

    async def create_user_session(self, **user_session_data: Dict) -> UserSession:
        """
        Create a new user session record.
        """
        async with self.__session_factory() as session:
            user_session = UserSession(**user_session_data)
            session.add(user_session)
            await session.commit()
            await session.refresh(user_session)
            return user_session

    async def get_user_session(self, session_id: str) -> Optional[UserSession]:
        """
        Retrieve a user session by session ID.
        """
        async with self.__session_factory() as session:
            query = select(UserSession).where(UserSession.session_id == session_id)
            result: Result = await session.execute(query)
            return result.scalar_one_or_none()

    async def update_user_session(
        self, session_id: str, update_data: Dict
    ) -> Optional[UserSession]:
        """

        Update specific attributes of a user session.
        """
        async with self.__session_factory() as session:
            query = (
                update(UserSession)
                .where(UserSession.session_id == session_id)
                .values(**update_data)
                .returning(UserSession)
            )
            result: Result = await session.execute(query)
            await session.commit()

            # Refresh the session to get the latest state after the update
            refreshed_session = await session.execute(
                select(UserSession).where(UserSession.session_id == session_id)
            )
            updated_session: Optional[UserSession] = result.scalar_one_or_none()
            return updated_session

    async def deactivate_all_sessions_by_user_id(
        self,
        user_id: int | list[int],
        service_name:str | list[str] | None = None,
    ) -> int:
        """
        Deactivate all active sessions for given user(s) and optional service(s).
        """
        async with self.__session_factory() as session:
            filters = self._build_session_deactive_filters(user_id, service_name)

            query = (
                update(UserSession)
                .where(*filters)
                .values(is_active=False)
            )

            result: Result = await session.execute(query)
            await session.commit()
            return result.rowcount


    async def deactivate_all_sessions_by_partner_id(
        self, partner_id: int, service_name: str = None
    ) -> Tuple[int, List[int]]:
        """
        Deactivate all active user sessions belonging to a specific partner.
        Returns a tuple: (count of deactivated sessions, list of affected user IDs).
        Executes as a single DB transaction without looping.
        """
        async with self.__session_factory() as session:
            # Step 1: Get all active user IDs for that partner
            user_ids_stmt = select(User.id).where(User.partner_id == partner_id)
            user_result = await session.execute(user_ids_stmt)
            user_ids = [row[0] for row in user_result.fetchall()]

            if not user_ids:
                return 0, []

            # Step 2: Deactivate all active sessions for those user IDs
            conditions = [
                UserSession.user_id.in_(user_ids),
                UserSession.is_active.is_(True),
            ]

            # Apply service_name filter
            if service_name is not None:
                conditions.append(UserSession.service_name == service_name)

            # Step 3: Deactivate sessions
            deactivate_stmt = (
                update(UserSession)
                .where(*conditions)
                .values(is_active=False)
                .execution_options(synchronize_session=False)
            )

            result = await session.execute(deactivate_stmt)
            await session.commit()

            deactivated_count = result.rowcount or 0

            return deactivated_count, user_ids

    async def deactivate_or_create_user_configs_by_user_ids(
        self, user_ids: list[int], config: bool
    ) -> int:
        """
        For given user_ids:
        - If a UserConfig exists for key='is_maglo_enabled', set its value to False.
        - If not exists, create it with value=False.
        Returns total number of affected/created rows.
        """
        if not user_ids:
            return 0

        async with self.__session_factory() as session:
            # 1️⃣ Fetch all configs where key='is_maglo_enabled' for given users
            existing_configs = (
                (
                    await session.execute(
                        select(UserConfig.user_id).where(
                            UserConfig.user_id.in_(user_ids),
                            UserConfig.key == TokenKeys.IS_MAGLO_ENABLED,
                            UserConfig.is_active == True,
                        )
                    )
                )
                .scalars()
                .all()
            )

            existing_user_ids = set(existing_configs)
            missing_user_ids = set(user_ids) - existing_user_ids

            # 2️⃣ Update existing configs
            update_stmt = (
                update(UserConfig)
                .where(
                    UserConfig.user_id.in_(existing_user_ids),
                    UserConfig.key == TokenKeys.IS_MAGLO_ENABLED,
                )
                .values(value=config)
                .execution_options(synchronize_session=False)
            )
            update_result = await session.execute(update_stmt)

            # 3️⃣ Create configs for users who don't have it
            new_configs = [
                UserConfig(
                    user_id=uid,
                    key=TokenKeys.IS_MAGLO_ENABLED,
                    value=config,
                    is_active=True,
                )
                for uid in missing_user_ids
            ]
            session.add_all(new_configs)

            await session.commit()

            total_affected = (update_result.rowcount or 0) + len(new_configs)
            return total_affected


    async def deactivate_all_sessions_by_service_name(
        self,
        service_name: str,
    ) -> int:
        """
        Deactivate all active sessions for a specific service.
        """
        async with self.__session_factory() as session:
            filters = [
                UserSession.is_active.is_(True),
                UserSession.service_name == service_name,
            ]

            query = (
                update(UserSession)
                .where(*filters)
                .values(
                    is_active=False,
                )
            )

            result: Result = await session.execute(query)
            await session.commit()
            return result.rowcount


    def _build_session_deactive_filters(
        self,
        user_id: int | list[int],
        service_names: str | list[str] | None = None,
    ):
        filters = [UserSession.is_active.is_(True)]

        if isinstance(user_id, list):
            filters.append(UserSession.user_id.in_(user_id))
        else:
            filters.append(UserSession.user_id == user_id)

        if service_names:
            if isinstance(service_names, list):
                filters.append(UserSession.service_name.in_(service_names))
            else:
                filters.append(UserSession.service_name == service_names)

        return filters

    async def has_active_session(
            self, 
            user_id: int, 
            current_time: int,
            service_name: str
        ) -> bool:
        async with self.__session_factory() as session:
            query = select(
                exists().where(
                    UserSession.user_id == user_id,
                    UserSession.service_name == service_name,
                    UserSession.is_active.is_(True),
                    UserSession.expiry_time > current_time   
                )
            )
            result = await session.execute(query)
            return result.scalar()