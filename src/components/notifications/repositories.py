from uuid import UUID
from contextlib import AbstractAsyncContextManager
from typing import Callable, Dict, List, Optional, Tuple
from sqlalchemy import select, update, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.components.notifications.models import NotificationSubscription, NotificationHistory
from src.components.notifications.schemas import (
    NotificationPreferenceItem,
    NotificationPreferenceStateEnum,
    NotificationScopeEnum,
    NotificationSourceEnum,
)
from src.components.user.models import User
from src.components.user_config.constants import UserConfigEnum
from src.components.user_config.models import UserConfig
from src.loggers.console_service_logger import ConsoleServiceLogger
from src.components.common.datetime import DateTimeUtil
from src.components.notifications.constants import NotificationServiceType
from src.components.notifications.scope_mapper import SOURCE_SCOPE_TO_CONFIG_KEY

CONFIG_KEY_TO_SOURCE_SCOPE: Dict[str, Tuple[str, Optional[str]]] = {
    value: key for key, value in SOURCE_SCOPE_TO_CONFIG_KEY.items()
}

EVENT_TO_SCOPE: Dict[str, NotificationScopeEnum] = {
    # event_name(s) producers send for whatsapp messages
    "WHATSAPP_MESSAGE_RECEIVED": NotificationScopeEnum.WHATSAPP,
}
from src.components.notifications.constants import NotificationServiceType 

class NotificationRepository:
    ...
    def __init__(
        self,
        session_factory: Callable[..., AbstractAsyncContextManager[AsyncSession]],
        console_service_logger: ConsoleServiceLogger,
    ):
        self.__session_factory = session_factory
        self.__logger = console_service_logger

    async def upsert_subscription(
        self, user_id: UUID, channel_type: str, identifier: str, meta_data: dict, service_type: NotificationServiceType,
    ) -> None:
        async with self.__session_factory() as session:
            stmt = insert(NotificationSubscription).values(
                user_id=user_id,
                channel_type=channel_type,
                identifier=identifier,
                meta_data=meta_data,
                service_type=service_type,
                created_at= DateTimeUtil.get_current_time(),
                updated_at= DateTimeUtil.get_current_time()
            )

            # If user already registered this device token, just reactivate it
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_id", "identifier","service_type"],
                set_=dict(
                    is_active=True,
                    meta_data=stmt.excluded.meta_data,
                    updated_at=DateTimeUtil.get_current_time()
                )
            )
            await session.execute(stmt)

            await session.commit()

    async def get_active_subscriptions(self, user_id: UUID, service_type: str | None = None,) -> List[NotificationSubscription]:
        async with self.__session_factory() as session:
            query = select(NotificationSubscription).where(
                NotificationSubscription.user_id == user_id,
                NotificationSubscription.is_active == True
            )
            if service_type:
                query = query.where(
                    NotificationSubscription.service_type == service_type.value
                )
            result = await session.execute(query)
            rows = result.scalars().all()
            self.__logger.info(
                f"get_active_subscriptions(user_id={user_id}) returned {len(rows)} rows"
            )
            return rows


    async def deactivate_subscription(self, user_id: UUID, identifier: str, service_type: NotificationServiceType) -> None:
        async with self.__session_factory() as session:
            stmt = update(NotificationSubscription).where(
                NotificationSubscription.user_id == user_id,
                NotificationSubscription.identifier == identifier,
                NotificationSubscription.service_type == service_type.value,
            ).values(is_active=False, updated_at=DateTimeUtil.get_current_time())
            await session.execute(stmt)
            await session.commit()

    async def insert_history(self, user_id: UUID, title: str, body: str, data: dict, service_type: NotificationServiceType) -> None:
        async with self.__session_factory() as session:
            history = NotificationHistory(
                user_id=user_id,
                title=title,
                body=body,
                data_payload=data,
                service_type= service_type.value,
                created_at=DateTimeUtil.get_current_time(),
                updated_at=DateTimeUtil.get_current_time(),
            )

            session.add(history)
            await session.commit()
            await session.refresh(history)

            return history

    async def get_notification_preferences(
        self, user_id: UUID
    ) -> List[NotificationPreferenceItem]:
        """
        Resolve the source-level and sub-scope delivery state from the
        shared user-config table.

        We default to ENABLED for missing rows so existing users keep the current
        behavior until they explicitly opt out.
        """
        config_keys = list(dict.fromkeys(SOURCE_SCOPE_TO_CONFIG_KEY.values()))

        async with self.__session_factory() as session:
            query = select(UserConfig).where(
                UserConfig.user_id == user_id,
                UserConfig.key.in_(config_keys),
                UserConfig.is_active.is_(True),
            )
            result = await session.execute(query)
            rows = result.scalars().all()

        preference_map = {
            (source, scope): NotificationPreferenceItem(
                source=NotificationSourceEnum(source),
                scope=scope,
                state=NotificationPreferenceStateEnum.ENABLED,
            )
            for (source, scope), _ in SOURCE_SCOPE_TO_CONFIG_KEY.items()
        }

        rows_by_config_key = {row.key: row for row in rows}

        for (source, scope), config_key in SOURCE_SCOPE_TO_CONFIG_KEY.items():
            row = rows_by_config_key.get(config_key)
            if not row:
                continue

            is_enabled = self._coerce_enabled_value(row.value)
            preference_map[(source, scope)] = NotificationPreferenceItem(
                source=NotificationSourceEnum(source),
                scope=scope,
                state=(
                    NotificationPreferenceStateEnum.ENABLED
                    if is_enabled
                    else NotificationPreferenceStateEnum.DISABLED
                ),
            )

        return [
            preference_map[(source, scope)]
            for (source, scope) in SOURCE_SCOPE_TO_CONFIG_KEY.keys()
        ]

    async def upsert_notification_preferences(
        self, user_id: UUID, preferences: List[NotificationPreferenceItem]
    ) -> List[NotificationPreferenceItem]:
        """
        Store application-level preferences in the shared user-config table.

        The existing JSON history on UserConfig keeps the audit trail without a new table.
        """
        if not preferences:
            return await self.get_notification_preferences(user_id)

        async with self.__session_factory() as session:
            keys = []
            for p in preferences:
                config_key = self._resolve_config_key(
                    source=p.source.value,
                    scope=p.scope.value if p.scope else None,
                )
                if config_key:
                    keys.append(config_key)
            query = select(UserConfig).where(
                UserConfig.user_id == user_id,
                UserConfig.key.in_(keys),
            )
            result = await session.execute(query)
            existing_configs = result.scalars().all()
            existing_map = {config.key: config for config in existing_configs}

            for preference in preferences:
                config_key = self._resolve_config_key(
                    source=preference.source.value,
                    scope=preference.scope.value if preference.scope else None,
                )
                if not config_key:
                    continue

                new_value = preference.state == NotificationPreferenceStateEnum.ENABLED
                config = existing_map.get(config_key)
                if config:
                    old_value = config.value
                    config.update_history(old_value, new_value)
                    config.value = new_value
                else:
                    session.add(
                        UserConfig(
                            user_id=user_id,
                            key=config_key,
                            value=new_value,
                        )
                    )

            await session.commit()

        return await self.get_notification_preferences(user_id)

    async def get_user_history(self, user_id: UUID, limit: int = 50, offset: int = 0, state:Optional[str] = None, service_type: NotificationServiceType = NotificationServiceType.TALKO,) -> Tuple[List[NotificationHistory], int]:
        async with self.__session_factory() as session:
        
            # Base query
            base_query = select(NotificationHistory).where(
                NotificationHistory.user_id == user_id,
                NotificationHistory.service_type == service_type.value,
            )

            count_query = select(func.count()).select_from(NotificationHistory).where(
                NotificationHistory.user_id == user_id,
                NotificationHistory.service_type == service_type.value,
            )

            # Apply state filter
            if state == "unread":
                base_query = base_query.where(NotificationHistory.is_read.is_(False))
                count_query = count_query.where(NotificationHistory.is_read.is_(False))

            elif state == "read":
                base_query = base_query.where(NotificationHistory.is_read.is_(True))
                count_query = count_query.where(NotificationHistory.is_read.is_(True))

            # Add ordering + pagination
            base_query = (
                base_query
                .order_by(NotificationHistory.created_at.desc())
                .limit(limit)
                .offset(limit * offset)
            )

            # Execute queries
            result = await session.execute(base_query)
            count_result = await session.execute(count_query)

            data = result.scalars().all()
            total_count = count_result.scalar_one()

            return data, total_count

    async def get_unread_count(self, user_id: UUID, service_type: NotificationServiceType) -> int:
        async with self.__session_factory() as session:
            query = select(func.count(NotificationHistory.id)).where(
                NotificationHistory.user_id == user_id,
                NotificationHistory.service_type == service_type.value,
                NotificationHistory.is_read == False
            )
            result = await session.execute(query)
            return result.scalar() or 0

    async def mark_as_read(self, user_id: UUID, notification_ids: List[UUID]) -> None:
        async with self.__session_factory() as session:
            stmt = update(NotificationHistory).where(NotificationHistory.user_id == user_id)
            
            # If specific IDs are provided, only marking those. Otherwise, marking all as read.
            if notification_ids:
                stmt = stmt.where(NotificationHistory.id.in_(notification_ids))
            else:
                stmt = stmt.where(NotificationHistory.is_read == False)
                
            stmt = stmt.values(is_read=True, updated_at=DateTimeUtil.get_current_time())
            await session.execute(stmt)
            await session.commit()

    async def unsubscribe_all_users_from_partner(self, partner_id: UUID):
        try:
            async with self.__session_factory() as session:
                stmt = (
                    update(NotificationSubscription)
                    .where(
                        NotificationSubscription.channel_type == "FCM",
                        NotificationSubscription.user_id.in_(
                            select(User.id).where(User.partner_id == partner_id)
                        )
                    )
                    .values(is_active=False)
                )
                await session.execute(stmt)
                await session.commit()
            ...
        except Exception as exp:
            self.__logger.info(f"got an error while deactivating FCM tokens for partner : {exp}")
            ...
    async def is_notification_enabled(
        self, user_id: UUID, source: str, event_name: Optional[str] = None
    ) -> bool:
        source_key = self._resolve_config_key(source=source)
        if not source_key:
            self.__logger.info(
                f"Unknown notification source '{source}', defaulting delivery to enabled."
            )
            return True

        scoped_key = self._resolve_config_key(
            source=source, scope=self._resolve_scope_from_event(event_name)
        )
        keys_to_fetch = {source_key} | ({scoped_key} if scoped_key and scoped_key != source_key else set())

        async with self.__session_factory() as session:
            query = select(UserConfig.key, UserConfig.value).where(
                UserConfig.user_id == user_id,
                UserConfig.key.in_(keys_to_fetch),
                UserConfig.is_active.is_(True),
            )
            result = await session.execute(query)
            values = dict(result.all())

        source_enabled = self._coerce_enabled_value(values[source_key]) if source_key in values else True
        if not source_enabled:
            return False

        if not scoped_key or scoped_key == source_key:
            return source_enabled

        if scoped_key not in values:
            return True

        return self._coerce_enabled_value(values[scoped_key])
            
    @staticmethod
    def _coerce_enabled_value(value: object) -> bool:
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"enabled", "enable", "true", "1", "yes"}:
                return True
            if normalized in {"disabled", "disable", "false", "0", "no"}:
                return False

        return bool(value)

    @staticmethod
    def _resolve_scope_from_event(event_name: Optional[str]) -> Optional[str]:
        if not event_name:
            return None
        scope = EVENT_TO_SCOPE.get(event_name)
        return scope.value if scope else None

    @staticmethod
    def _resolve_config_key(source: str, scope: Optional[str] = None) -> Optional[str]:
        return SOURCE_SCOPE_TO_CONFIG_KEY.get((source, scope))