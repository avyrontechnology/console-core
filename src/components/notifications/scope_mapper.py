from src.components.user_config.constants import UserConfigEnum
from typing import Callable, Dict, List, Optional, Tuple
from src.components.notifications.schemas import (

    NotificationScopeEnum,
    NotificationSourceEnum,
)




SOURCE_SCOPE_TO_CONFIG_KEY: Dict[Tuple[str, Optional[str]], str] = {
    # Source-wide switches
    (NotificationSourceEnum.MAGLO.value, None): UserConfigEnum.NOTIFICATION_MAGLO.value,
    (NotificationSourceEnum.MAGLO_APP.value, None): UserConfigEnum.NOTIFICATION_MAGLO_APP.value,
    (NotificationSourceEnum.BABBLER.value, None): UserConfigEnum.NOTIFICATION_BABBLER.value,
    (NotificationSourceEnum.BABBLER_APP.value, None): UserConfigEnum.NOTIFICATION_BABBLER_APP.value,
    (NotificationSourceEnum.TALKO.value, None): UserConfigEnum.NOTIFICATION_TALKO.value,
    (NotificationSourceEnum.OBOTAAI.value, None): UserConfigEnum.NOTIFICATION_OBOTAAI.value,

    # Babbler (web + app) both get the whatsapp scope
    (NotificationSourceEnum.BABBLER.value, NotificationScopeEnum.WHATSAPP.value): UserConfigEnum.NOTIFICATION_WHATSAPP.value,
    (NotificationSourceEnum.BABBLER_APP.value, NotificationScopeEnum.WHATSAPP.value): UserConfigEnum.NOTIFICATION_WHATSAPP.value,

    # Maglo (web) scoped controls
    (NotificationSourceEnum.MAGLO.value, NotificationScopeEnum.LEAD_ASSIGNED.value): UserConfigEnum.NOTIFICATION_MAGLO_LEAD_ASSIGNED.value,
    (NotificationSourceEnum.MAGLO.value, NotificationScopeEnum.BULK_LEAD_ASSIGNED.value): UserConfigEnum.NOTIFICATION_MAGLO_BULK_LEAD_ASSIGNED.value,
    (NotificationSourceEnum.MAGLO.value, NotificationScopeEnum.FOLLOWUP.value): UserConfigEnum.NOTIFICATION_MAGLO_FOLLOWUP.value,

    # Maglo App gets the same scoped controls as Maglo web
    (NotificationSourceEnum.MAGLO_APP.value, NotificationScopeEnum.LEAD_ASSIGNED.value): UserConfigEnum.NOTIFICATION_MAGLO_LEAD_ASSIGNED.value,
    (NotificationSourceEnum.MAGLO_APP.value, NotificationScopeEnum.BULK_LEAD_ASSIGNED.value): UserConfigEnum.NOTIFICATION_MAGLO_BULK_LEAD_ASSIGNED.value,
    (NotificationSourceEnum.MAGLO_APP.value, NotificationScopeEnum.FOLLOWUP.value): UserConfigEnum.NOTIFICATION_MAGLO_FOLLOWUP.value,
}