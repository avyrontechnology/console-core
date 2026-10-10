from src.components.common.errors import NotFoundError


class UserConfigKeyError(NotFoundError):
    entity_name: str = "user_config_key"
