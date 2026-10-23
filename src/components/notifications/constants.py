from typing import List
from enum import Enum

SERVICES : List[str] = ["talko", "obotaai", "console"]

class NotificationServiceType(str, Enum):
    TALKO = "talko"
    OBOTAAI = "obotaai"