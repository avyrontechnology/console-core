from unittest.mock import AsyncMock, MagicMock

import pytest

from src.components.partner.models import Partner
from src.components.partner_config.constants import (
    PartnerConfigEnum,
    SubscriptionModeEnum,
)
from src.components.partner_home_page.constants import RoleActionFlagKeys
from src.components.partner_home_page.repositories import PartnerHomePageRepositories
from src.components.partner_home_page.role_mapper import RoleFlagMapper
from src.components.partner_home_page.schemas import UserEntityData
from src.components.partner_home_page.services import PartnerHomePageService


@pytest.mark.asyncio
class TestPartnerHomePageService:

    @pytest.fixture(autouse=True)
    def setup_class(self):
        """Set up the service and mocks for the test class."""
        self.repository_mock = AsyncMock(spec=PartnerHomePageRepositories)
        self.logger_mock = MagicMock()
        self.audit_service_mock = MagicMock()

        self.service = PartnerHomePageService(
            partner_home_page_repository=self.repository_mock,
            audit_service=self.audit_service_mock,
            console_service_logger=self.logger_mock,
        )

    def _mock_common_homepage_repositories(self):
        """Shared repository/role-mapper scaffolding used by every
        get_partner_homepage_details() happy-path test (user_id=partner_id=1)."""
        self.repository_mock.get_user_hierarchy = AsyncMock(
            return_value={"role_hierarchy_level": 2}
        )
        self.repository_mock.get_partner_homepage_details = AsyncMock(
            return_value={
                "id": 1,
                "name": "John Doe",
                "designation": "Manager",
                "email": "jhon@exam.com",
            }
        )
        self.repository_mock._get_parnter_by_id = AsyncMock(
            return_value=Partner(is_internal=True)
        )
        RoleFlagMapper.get_flags = MagicMock(
            return_value={
                RoleActionFlagKeys.CAN_VIEW_DASHBOARD: True,
                RoleActionFlagKeys.CAN_VIEW_PARTNERS: True,
                RoleActionFlagKeys.CAN_VIEW_PERMISSIONS: True,
                RoleActionFlagKeys.CAN_VIEW_USERS: True,
            }
        )

    def _mock_partner_config_service(self, configs, subscription_mode=SubscriptionModeEnum.SELF_SERVED):
        """Builds a partner_config_service mock; both methods must be AsyncMock
        since get_partner_homepage_details gathers them concurrently."""
        subscription_mode_mock = MagicMock()
        subscription_mode_mock.value = subscription_mode

        partner_config_service_mock = MagicMock()
        partner_config_service_mock.get_partner_config_by_key = AsyncMock(
            return_value=subscription_mode_mock
        )
        partner_config_service_mock.get_partner_configs_by_partner_id = AsyncMock(
            return_value=configs
        )
        return partner_config_service_mock

    @pytest.mark.asyncio
    async def test_get_partner_homepage_details_success(self):
        """Test successful retrieval of partner homepage details."""
        user_id = partner_id = 1
        self._mock_common_homepage_repositories()
        partner_config_service_mock = self._mock_partner_config_service(
            [
                {"key": "is_maglo_enabled", "value": True},
                {"key": "is_talko_enabled", "value": False},
                {"key": "is_babbler_enabled", "value": True},
            ]
        )

        # Act
        result = await self.service.get_partner_homepage_details(
            user_id, partner_id, partner_config_service=partner_config_service_mock
        )

        # Assert
        assert isinstance(result, UserEntityData)

        assert result.partner_info.partner_id == partner_id
        assert result.partner_info.subscription_mode == SubscriptionModeEnum.SELF_SERVED

        assert result.services_info.is_maglo_enabled is True
        assert result.services_info.is_talko_enabled is False
        assert result.services_info.is_babbler_enabled is True

        assert result.user_permissions.can_view_dashboard is True
        assert result.user_permissions.can_view_partners is True

        self.repository_mock.get_user_hierarchy.assert_called_once_with(user_id)
        self.repository_mock.get_partner_homepage_details.assert_called_once_with(
            user_id
        )
        self.repository_mock._get_parnter_by_id.assert_called_once_with(partner_id)
        partner_config_service_mock.get_partner_config_by_key.assert_called_once_with(
            partner_id=partner_id,
            key=PartnerConfigEnum.SUBSCRIPTION_MODE.value,
        )
        partner_config_service_mock.get_partner_configs_by_partner_id.assert_called_once_with(
            partner_id
        )

    @pytest.mark.asyncio
    async def test_get_partner_homepage_details_add_number_and_obotaai_enabled(self):
        """New code: is_add_number_enabled must be surfaced in services_info,
        same as is_obotaai_enabled, so the home page reflects the live
        partner-config toggle rather than a stale value."""
        user_id = partner_id = 1
        self._mock_common_homepage_repositories()
        partner_config_service_mock = self._mock_partner_config_service(
            [
                {"key": "is_maglo_enabled", "value": True},
                {"key": "is_add_number_enabled", "value": True},
                {"key": "is_obotaai_enabled", "value": True},
            ]
        )

        result = await self.service.get_partner_homepage_details(
            user_id, partner_id, partner_config_service=partner_config_service_mock
        )

        assert result.services_info.is_add_number_enabled is True
        assert result.services_info.is_obotaai_enabled is True

    @pytest.mark.asyncio
    async def test_get_partner_homepage_details_without_partner_config(self):
        """Test homepage details when no partner config is found."""
        user_id = partner_id = 1
        self._mock_common_homepage_repositories()

        # get_partner_config_by_key must be AsyncMock even when
        # get_partner_configs_by_partner_id returns nothing, since both
        # are gathered concurrently.
        partner_config_service_mock = MagicMock()
        partner_config_service_mock.get_partner_config_by_key = AsyncMock(
            return_value=None
        )
        partner_config_service_mock.get_partner_configs_by_partner_id = AsyncMock(
            return_value=None
        )

        # Act
        result = await self.service.get_partner_homepage_details(
            user_id, partner_id, partner_config_service=partner_config_service_mock
        )

        # Assert — services_info should remain defaults (all False)
        assert result.services_info.is_maglo_enabled is False
        assert result.services_info.is_talko_enabled is False
        assert result.services_info.is_babbler_enabled is False
        assert result.services_info.is_add_number_enabled is False
        assert result.services_info.is_obotaai_enabled is False

        # subscription_mode falls back to SELF_SERVED when config returns None
        assert result.partner_info.subscription_mode == SubscriptionModeEnum.SELF_SERVED

        self.repository_mock.get_user_hierarchy.assert_called_once_with(user_id)
        self.repository_mock.get_partner_homepage_details.assert_called_once_with(
            user_id
        )
        self.repository_mock._get_parnter_by_id.assert_called_once_with(partner_id)
        partner_config_service_mock.get_partner_config_by_key.assert_called_once_with(
            partner_id=partner_id,
            key=PartnerConfigEnum.SUBSCRIPTION_MODE.value,
        )
        partner_config_service_mock.get_partner_configs_by_partner_id.assert_called_once_with(
            partner_id
        )

    async def test_get_partner_homepage_details_unexpected_error(self):
        """Test unexpected error during retrieval of partner homepage details."""
        # Arrange
        user_id = 1
        partner_id = 1
        self.repository_mock.get_user_hierarchy.side_effect = Exception(
            "Unexpected error"
        )

        # Act & Assert
        with pytest.raises(Exception, match="Unexpected error"):
            await self.service.get_partner_homepage_details(user_id, partner_id)

        self.repository_mock.get_user_hierarchy.assert_called_once_with(user_id)
        self.logger_mock.error.assert_called_once_with(
            f"Unexpected error occurred while getting partner homepage details by user_id {user_id}"
        )

    async def test_partner_dashboard_cards_success(self):
        """Test successful retrieval of partner dashboard cards."""
        # Arrange
        current_user_id = 1
        mock_dashboard_cards = [
            {"title": "Total Partners", "count": 100},
            {"title": "Last Week Partners", "count": 10},
            {"title": "Partners > 50 Licenses", "count": 5},
        ]
        self.repository_mock.partner_dashboard_cards.return_value = mock_dashboard_cards

        # Act
        result = await self.service.partner_dashboard_cards(current_user_id)

        # Assert
        self.repository_mock.partner_dashboard_cards.assert_called_once_with(
            current_user_id
        )
        self.logger_mock.info.assert_any_call(
            "trying to get partner dashboard card counts."
        )
        self.logger_mock.info.assert_any_call(
            "successfully fetched partner dashboard card counts: {}".format(
                mock_dashboard_cards
            )
        )
        assert result == mock_dashboard_cards

    async def test_partner_dashboard_cards_unexpected_error(self):
        """Test unexpected error during retrieval of partner dashboard cards."""
        # Arrange
        current_user_id = 1
        self.repository_mock.partner_dashboard_cards.side_effect = Exception(
            "Unexpected error"
        )

        # Act & Assert
        with pytest.raises(Exception, match="Unexpected error"):
            await self.service.partner_dashboard_cards(current_user_id)

        self.repository_mock.partner_dashboard_cards.assert_called_once_with(
            current_user_id
        )
        self.logger_mock.info.assert_called_once_with(
            "trying to get partner dashboard card counts."
        )
        self.logger_mock.error.assert_called_once_with(
            "Error fetching partner dashboard card counts: Unexpected error"
        )

    async def test_get_partner_homepage_details_partner_fetch_failure(self):
        """Test unexpected error during partner fetch inside homepage details."""

        user_id = 1
        partner_id = 1

        mock_hierarchy_details = {"role_hierarchy_level": 2}
        mock_user_information = {
            "id": 1,
            "name": "John Doe",
            "designation": "Manager",
            "email": "jhon@exam.com",
        }

        self.repository_mock.get_user_hierarchy = AsyncMock(
            return_value=mock_hierarchy_details
        )
        self.repository_mock.get_partner_homepage_details = AsyncMock(
            return_value=mock_user_information
        )
        self.repository_mock._get_parnter_by_id.side_effect = Exception(
            "Unexpected partner error"
        )

        with pytest.raises(Exception, match="Unexpected partner error"):
            await self.service.get_partner_homepage_details(user_id, partner_id)

        self.repository_mock.get_user_hierarchy.assert_called_once_with(user_id)
        self.repository_mock.get_partner_homepage_details.assert_called_once_with(
            user_id
        )
        self.repository_mock._get_parnter_by_id.assert_called_once_with(partner_id)

        self.logger_mock.error.assert_called_once_with(
            f"Unexpected error occurred while getting partner homepage details by user_id {user_id}"
        )
