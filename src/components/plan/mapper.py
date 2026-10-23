"""
Maps internal permission endpoints to
Platform → Modules → Features → Endpoints

Used for:
- Showing plan features on UI
- Determining what a user has access to
- Decoupling UI language from backend permission keys
"""

from src.components.plan.constants import Platform

SERVICE_FEATURE_MAPPER = {
}
