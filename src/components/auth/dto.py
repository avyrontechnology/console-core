from dataclasses import dataclass, field
from typing import Optional
from src.components.user.models import User   

@dataclass
class ServiceAccessDTO:
    user: User
    svc_name: str
    config_map: dict
    partner_config_map: dict = field(default_factory=dict)
    is_assume_user: Optional[bool] = False
    trial_expiry: Optional[int] = None
    is_trial_active: Optional[bool] = None