import uuid
from sqlalchemy import Boolean, Column, String, UniqueConstraint, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from src.components.database.base_model import MetaData


class NotificationSubscription(MetaData):
    __tablename__ = 'console_notification_serivce'

    user_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    channel_type = Column(String(50), nullable=False, index=True) # e.g., 'FCM', 'WEBHOOK'
    identifier = Column(String, nullable=False, index=True) # The FCM Token or URL
    is_active = Column(Boolean, default=True, index=True)
    meta_data = Column(JSONB, nullable=True) # e.g., {"device_os": "ios"}
    service_type = Column(String(50), nullable=True, index=True) # eg {talko, obotaai}

    __table_args__ = (
        UniqueConstraint("user_id", "identifier", "service_type", name="uq_user_notification_identifier"),
    )


class NotificationHistory(MetaData):
    __tablename__ = 'console_notification_history'

    user_id = Column(UUID(as_uuid=True), index=True, nullable=False)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)
    data_payload = Column(JSONB, nullable=True) # e.g., {"lead_id": "123"}
    is_read = Column(Boolean, default=False, index=True)
    service_type = Column(String(50), nullable=True, index=True) # e.g talko, obotaai