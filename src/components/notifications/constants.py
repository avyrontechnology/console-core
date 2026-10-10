from typing import List
from enum import Enum

SERVICES : List[str] = ["maglo", "maglo_app", "babbler", "console"]

class NotificationServiceType(str, Enum):
    MAGLO = "maglo"
    BABBLER = "babbler"