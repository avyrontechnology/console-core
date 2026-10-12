import pytest
from unittest.mock import MagicMock, patch

import firebase_admin

from src.core.firebase import firebase_init
from src.components.notifications.constants import NotificationServiceType


class FakeUnsupportedServiceType:
    """Stand-in for a retired service type."""
    value = "console"


class TestFirebaseInit:

    def test_returns_existing_app_if_already_initialized(self):
        mock_app = MagicMock()

        with patch.object(firebase_admin, "_apps", {"talko": object()}), patch.object(
            firebase_admin, "get_app", return_value=mock_app
        ) as mock_get_app:
            result = firebase_init(NotificationServiceType.TALKO)

        assert result == mock_app
        mock_get_app.assert_called_once_with("talko")

    def test_unsupported_service_type_raises_value_error(self):
        with patch.object(firebase_admin, "_apps", {}):
            with pytest.raises(ValueError, match="Unsupported notification service type: console"):
                firebase_init(FakeUnsupportedServiceType())

