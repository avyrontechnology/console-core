from uuid import UUID
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict
from src.components.notifications.constants import NotificationServiceType

class ChannelTypeEnum(str, Enum):
    FCM = "FCM"
    WEBHOOK = "WEBHOOK"
    IN_APP = "IN_APP"


class NotificationSourceEnum(str, Enum):
    """Sources that are allowed to control notification delivery."""

    OBOTAAI = "obotaai"
    TALKO  = "talko"


class NotificationPreferenceStateEnum(str, Enum):
    """Application-level notification states kept in the DB."""

    ENABLED = "enabled"
    DISABLED = "disabled"


class NotificationScopeEnum(str, Enum):
    """
    Optional fine-grained notification scopes.

    `all` is the source-wide default, while scoped controls let producers control
    single-assignment, bulk-assignment, and followup notifications separately
    without changing the producer payload shape.
    """

    ALL = "all"
    LEAD_ASSIGNED = "lead_assigned"
    BULK_LEAD_ASSIGNED = "bulk_lead_assigned"
    FOLLOWUP = "followup"
    WHATSAPP = "whatsapp" 

class RegisterSubscriptionRequest(BaseModel):
    channel_type: ChannelTypeEnum
    identifier: str
    service_type: NotificationServiceType = NotificationServiceType.TALKO
    meta_data: Optional[Dict[str, Any]] = None


class NotificationPreferenceItem(BaseModel):
    """
    One preference entry per source.

    The API stays list-based so we can add new sources or state values later
    without changing the storage model or the surrounding workflow.
    """

    source: NotificationSourceEnum
    scope: Optional[NotificationScopeEnum] = None
    state: NotificationPreferenceStateEnum

    model_config = ConfigDict(from_attributes=True)


class NotificationPreferenceRequest(BaseModel):
    preferences: List[NotificationPreferenceItem]


class NotificationPreferenceResponse(BaseModel):
    user_id: UUID
    preferences: List[NotificationPreferenceItem]

    model_config = ConfigDict(from_attributes=True)


class CommonNotificationMessage(BaseModel):
    """
    Canonical queue payload consumed by the console listener.

    Keeping this shape in one model makes the queue contract explicit and
    keeps Swagger-friendly schema generation available for future API reuse.
    """

    source: NotificationSourceEnum
    event_name: str
    payload: Dict[str, Any]
    created_at: int
    heading: str
    body: str

    model_config = ConfigDict(from_attributes=True)

class NotificationHistoryResponse(BaseModel):
    id: UUID
    title: str
    body: str
    data_payload: Optional[Dict[str, Any]] = None
    service_type: Optional[NotificationServiceType] = None
    is_read: bool
    created_at: int

    model_config = ConfigDict(from_attributes=True)

class UnreadCountResponse(BaseModel):
    unread_count: int
    service_type: Optional[NotificationServiceType] = None

class MarkReadRequest(BaseModel):
    notification_ids: List[UUID]