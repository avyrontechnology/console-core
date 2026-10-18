from uuid import UUID

from pydantic import ValidationError
import pytest

from src.components.notifications.schemas import MarkReadRequest


class TestMarkReadRequest:
    def test_accepts_uuid_ids(self):
        payload = MarkReadRequest(
            notification_ids=[
                "11111111-1111-1111-1111-111111111111",
                "22222222-2222-2222-2222-222222222222",
            ]
        )
        assert payload.notification_ids == [
            UUID("11111111-1111-1111-1111-111111111111"),
            UUID("22222222-2222-2222-2222-222222222222"),
        ]

    def test_empty_list_marks_everything_read(self):
        assert MarkReadRequest(notification_ids=[]).notification_ids == []

    def test_rejects_non_uuid(self):
        with pytest.raises(ValidationError):
            MarkReadRequest(notification_ids=[1, 2])