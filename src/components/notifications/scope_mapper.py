from src.components.user_config.constants import UserConfigEnum
from typing import Callable, Dict, List, Optional, Tuple
from src.components.notifications.schemas import (

    NotificationScopeEnum,
    NotificationSourceEnum,
)




SOURCE_SCOPE_TO_CONFIG_KEY: Dict[Tuple[str, Optional[str]], str] = {
    # Source-wide switches
    (NotificationSourceEnum.TALKO.value, None): UserConfigEnum.NOTIFICATION_TALKO.value,
    (NotificationSourceEnum.OBOTAAI.value, None): UserConfigEnum.NOTIFICATION_OBOTAAI.value,
}