import pytest
from unittest.mock import MagicMock, patch

import firebase_admin

from src.core.firebase import firebase_init
from src.components.notifications.constants import NotificationServiceType


class FakeUnsupportedServiceType:
    """Stand-in for a service type that isn't MAGLO or BABBLER."""
    value = "console"


class TestFirebaseInit:

    def test_returns_existing_app_if_already_initialized(self):
        mock_app = MagicMock()

        with patch.object(firebase_admin, "_apps", {"maglo": object()}), patch.object(
            firebase_admin, "get_app", return_value=mock_app
        ) as mock_get_app:
            result = firebase_init(NotificationServiceType.MAGLO)

        assert result == mock_app
        mock_get_app.assert_called_once_with("maglo")

    def test_maglo_success_initializes_new_app(self):
        mock_cred = MagicMock()
        mock_app = MagicMock()
        mock_app.name = "maglo"

        with patch.object(firebase_admin, "_apps", {}), patch(
            "src.core.environment.ENV.FIREBASE_CREDENTIALS_MAGLO_JSON",
            '{"project_id": "maglo-project"}',
        ), patch(
            "firebase_admin.credentials.Certificate", return_value=mock_cred
        ) as mock_certificate, patch.object(
            firebase_admin, "initialize_app", return_value=mock_app
        ) as mock_initialize_app:
            result = firebase_init(NotificationServiceType.MAGLO)

        assert result == mock_app
        mock_certificate.assert_called_once_with({"project_id": "maglo-project"})
        mock_initialize_app.assert_called_once_with(mock_cred, name="maglo")

    def test_babbler_success_initializes_new_app(self):
        mock_cred = MagicMock()
        mock_app = MagicMock()
        mock_app.name = "babbler"

        with patch.object(firebase_admin, "_apps", {}), patch(
            "src.core.environment.ENV.FIREBASE_CREDENTIALS_BABBLER_JSON",
            '{"project_id": "babbler-project"}',
        ), patch(
            "firebase_admin.credentials.Certificate", return_value=mock_cred
        ) as mock_certificate, patch.object(
            firebase_admin, "initialize_app", return_value=mock_app
        ) as mock_initialize_app:
            result = firebase_init(NotificationServiceType.BABBLER)

        assert result == mock_app
        mock_certificate.assert_called_once_with({"project_id": "babbler-project"})
        mock_initialize_app.assert_called_once_with(mock_cred, name="babbler")

    def test_unsupported_service_type_raises_value_error(self):
        with patch.object(firebase_admin, "_apps", {}):
            with pytest.raises(ValueError, match="Unsupported notification service type: console"):
                firebase_init(FakeUnsupportedServiceType())

    def test_missing_credentials_raises_value_error(self):
        with patch.object(firebase_admin, "_apps", {}), patch(
            "src.core.environment.ENV.FIREBASE_CREDENTIALS_MAGLO_JSON", ""
        ):
            with pytest.raises(
                ValueError, match="Firebase credentials missing for service: maglo"
            ):
                firebase_init(NotificationServiceType.MAGLO)

    def test_initialization_failure_is_reraised(self):
        with patch.object(firebase_admin, "_apps", {}), patch(
            "src.core.environment.ENV.FIREBASE_CREDENTIALS_MAGLO_JSON",
            '{"project_id": "maglo-project"}',
        ), patch(
            "firebase_admin.credentials.Certificate", return_value=MagicMock()
        ), patch.object(
            firebase_admin, "initialize_app", side_effect=RuntimeError("bad credentials")
        ):
            with pytest.raises(RuntimeError, match="bad credentials"):
                firebase_init(NotificationServiceType.MAGLO)
