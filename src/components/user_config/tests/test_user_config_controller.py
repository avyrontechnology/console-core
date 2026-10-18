from typing import List, get_type_hints
from uuid import UUID

from src.components.user_config.controllers import UserConfigController


def test_upsert_user_config_accepts_uuid_lists():
    """user_ids is a UUID list after the PK migration: int would 422 every call."""
    hints = get_type_hints(UserConfigController.upsert_user_config)
    assert hints["user_ids"] == List[UUID]


def test_upsert_user_config_partner_id_is_uuid():
    hints = get_type_hints(UserConfigController.upsert_user_config)
    assert hints["partner_id"] is UUID