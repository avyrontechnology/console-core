from uuid import UUID
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import SQLAlchemyError
from src.components.partner.constant import DashboardFilters
from src.components.partner_home_page.constants import PartnerDashboardCardsAttributes
from src.components.partner_home_page.repositories import PartnerHomePageRepositories


@pytest.mark.asyncio
class TestPartnerHomePageRepositories:

    @pytest.fixture(autouse=True)
    def setup_class(self):
        """Set up the repository and mocks for the test class."""
        self.session_factory_mock = MagicMock()
        self.session_mock = AsyncMock()
        self.session_factory_mock.return_value.__aenter__.return_value = (
            self.session_mock
        )
        self.logger_mock = MagicMock()

        self.repository = PartnerHomePageRepositories(
            session_factory=self.session_factory_mock,
            console_service_logger=self.logger_mock,
        )

    async def test_get_partner_homepage_details_success(self):
        """Test successful retrieval of partner homepage details."""
        # Arrange
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_user = {"name": "John Doe", "designation": "Manager"}
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = mock_user
        self.session_mock.execute.return_value = mock_result

        # Act
        result = await self.repository.get_partner_homepage_details(user_id)

        # Assert
        assert result == mock_user
        self.session_mock.execute.assert_called_once()
        self.logger_mock.info.assert_any_call(
            f"Attempting to get partner homepage details by user_id {user_id}"
        )

    async def test_get_partner_homepage_details_unexpected_error(self):
        """Test unexpected error during retrieval of partner homepage details."""
        # Arrange
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        self.session_mock.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(SQLAlchemyError, match="Database error"):
            await self.repository.get_partner_homepage_details(user_id)

        self.session_mock.execute.assert_called_once()
        self.logger_mock.info.assert_any_call(
            f"Unexpected error occurred while getting partner homepage details by user_id {user_id}"
        )

    async def test_get_user_hierarchy_success(self):
        """Test successful retrieval of user hierarchy."""
        # Arrange
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_hierarchy = {"role_hierarchy_level": 3}
        mock_result = MagicMock()
        mock_result.mappings.return_value.first.return_value = mock_hierarchy
        self.session_mock.execute.return_value = mock_result

        # Act
        result = await self.repository.get_user_hierarchy(user_id)

        # Assert
        assert result == mock_hierarchy
        self.session_mock.execute.assert_called_once()
        self.logger_mock.info.assert_any_call(
            f"Attempting to get the user hierarchy for the user id: {user_id}"
        )

    async def test_get_user_hierarchy_unexpected_error(self):
        """Test unexpected error during retrieval of user hierarchy."""
        # Arrange
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        self.session_mock.execute.side_effect = SQLAlchemyError("Database error")

        # Act & Assert
        with pytest.raises(SQLAlchemyError, match="Database error"):
            await self.repository.get_user_hierarchy(user_id)

        self.session_mock.execute.assert_called_once()
        self.logger_mock.info.assert_any_call(
            f"Unexpected error occurred while getting user hierarchy by user_id {user_id}"
        )



    async def test_partner_dashboard_cards_internal_user_success(self):
        """Test successful retrieval of partner dashboard cards for an internal user."""
        current_user_id= UUID("11111111-1111-1111-1111-111111111111")

        # Mock the user as internal
        mock_user = MagicMock()
        mock_user.is_internal = True

        # Mock execute for user check → returns mock_user
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none.return_value = mock_user
        self.session_mock.execute = AsyncMock(side_effect=[mock_user_result])

        # Mock scalar() calls (only 3 calls now: total, last_week, >50 licenses)
        self.session_mock.scalar = AsyncMock(side_effect=[
            100,  # total_partners
            10,   # last_week_partners
            5,    # partners_with_50_licenses
        ])

        # Mock execute for combined config query → returns (2,)
        mock_config_result = MagicMock()
        mock_config_result.one.return_value = (2,)
        # append this to execute side_effect
        self.session_mock.execute.side_effect = [mock_user_result, mock_config_result]

        # Act
        result = await self.repository.partner_dashboard_cards(current_user_id)

        # Assert
        expected = [
            {"title": PartnerDashboardCardsAttributes.TOTAL_PARTNERS, "key": None, "count": 100},
            {"title": PartnerDashboardCardsAttributes.LAST_WEEK_PARTNERS, "key": DashboardFilters.PARTNERS_LAST_SEVEN_DAYS, "count": 10},
            {"title": PartnerDashboardCardsAttributes.PARTNERS_MORE_THAN_FIFTY_LICENSES, "key": DashboardFilters.PARTNERS_GT_FIFTY_LICENSES, "count": 5},
            {"title": PartnerDashboardCardsAttributes.PARTNERS_USING_HOLLAR, "key": DashboardFilters.PARTNERS_USING_TALKO, "count": 2},
        ]
        assert result == expected

        # One call for user check, one for combined config counts
        assert self.session_mock.execute.await_count == 2
        # Three scalar calls (total, last_week, >50 licenses)
        assert self.session_mock.scalar.await_count == 3
        self.logger_mock.info.assert_any_call("Fetching partner dashboard cards data.")



    async def test_get_partner_by_id_success(self):
        """Test successful retrieval of partner by id."""
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        mock_partner = MagicMock()
        
        mock_scalars_result = MagicMock()
        mock_scalars_result.first.return_value = mock_partner
        self.session_mock.execute.return_value.scalars = MagicMock(
            return_value=mock_scalars_result
        )

        result = await self.repository._get_parnter_by_id(partner_id)

        self.session_mock.execute.assert_called_once()
        self.logger_mock.info.assert_any_call(
            f"Getting Parnter with id: {partner_id}"
        )
        assert result == mock_partner

    async def test_get_partner_by_id_unexpected_error(self):
        """Test unexpected error during retrieval of partner by id."""
        partner_id= UUID("11111111-1111-1111-1111-111111111111")
        self.session_mock.execute.side_effect = Exception("Unexpected error")

        with pytest.raises(Exception, match="Unexpected error"):
            await self.repository._get_parnter_by_id(partner_id)

        self.session_mock.execute.assert_called_once()
        self.logger_mock.info.assert_any_call(
            f"Getting Parnter with id: {partner_id}"
        )
        self.logger_mock.info.assert_any_call(
            f"Un Expected Error came while getting Parnter with id: {partner_id}"
        )
