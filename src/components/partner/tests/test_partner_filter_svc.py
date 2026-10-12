from uuid import UUID
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from src.components.partner.constant import DashboardFilters
from src.components.partner.models import Partner
from src.components.partner.partner_filter_service import PartnerFilterService
from src.components.partner.schema import (
    PaginatedPartnerResponse,
    PartnerFilterRequest,
    PartnerResponse,
)
from src.exceptions import PartnerException

from pydantic import ValidationError

MAX_INT = 2147483647


@pytest.mark.asyncio
class TestPartnerFilterService:

    @pytest.fixture(autouse=True)
    def setup_class(self, mock_logger):
        self.partner_repository_mock = AsyncMock()
        self.mock_logger = mock_logger
        self.user_service_mock = AsyncMock()
        self.partner_meta_data_service_mock = AsyncMock()
        self.filter_service = PartnerFilterService(
            partner_repository=self.partner_repository_mock,
            console_service_logger=self.mock_logger,
        )

    @pytest.mark.asyncio
    async def test_enlist_partners_dynamically_success(self):
        filter_request = PartnerFilterRequest(
            filters=[{"field": "name", "operator": "=", "value": "Acme"}],
            order_by=[{"field": "created_at", "direction": "DESC"}],
            limit=10,
            offset=0,
            dashboard_filters=None,
            is_custom_role_permission_enabled=False,
        )

        fake_partner = type(
            "Partner",
            (),
            {
                "id": UUID("11111111-1111-1111-1111-111111111111"),
                "name": "Acme",
                "company_legal_name": "Acme Corp",
                "gst_no": "GST123",
                "cin_no": "CIN456",
                "active_license": 100,
                "description": "Test Partner",
                "created_at": 17000000,
                "is_active": True,
            },
        )()

        fake_admin = type(
            "Admin",
            (),
            {"partner_id": UUID("11111111-1111-1111-1111-111111111111"), "email": "admin@acme.com", "phone_number": "9999999999"},
        )()

        fake_query = select(Partner)

        # Mock repo responses
        self.partner_repository_mock.execute_partner_filter_scalar_query.return_value = (
            1
        )
        self.partner_repository_mock.execure_partner_filter_query.side_effect = [
            [(fake_partner,)],  # First call: returns partners
            []  # Second call: returns counts (empty since no configs)
        ]

        # Mock metadata
        self.partner_meta_data_service_mock.get_partner_meta_data_by_partner_ids.return_value = {
            1: {"is_talko_free_trial__enabled": True}
        }

        # Mock admin users
        self.user_service_mock.get_admin_credentials_by_hierarchy.return_value = [
            fake_admin
        ]

        # Mock builder
        with patch(
            "src.components.partner.partner_filter_builder.PartnerFilterBuilder"
        ) as MockBuilder:
            mock_builder = MockBuilder.return_value
            mock_builder.build_query = AsyncMock(return_value=fake_query)

            response = await self.filter_service.enlist_partners_dynamically(
                filter_request,
                user_service=self.user_service_mock,
                partner_meta_data_service=self.partner_meta_data_service_mock,
            )

        assert isinstance(response, PaginatedPartnerResponse)
        assert response.total_count == 1
        assert len(response.partners_data) == 1
        assert response.partners_data[0].name == "Acme"
        assert response.partners_data[0].email == "admin@acme.com"
        assert response.partners_data[0].phone_number == "9999999999"

    @pytest.mark.asyncio
    async def test_enlist_partners_dynamically_no_admin(self):
        filter_request = PartnerFilterRequest(
            filters=[{"field": "name", "operator": "=", "value": "Acme"}],
            order_by=[{"field": "created_at", "direction": "DESC"}],
            limit=10,
            offset=0,
            dashboard_filters=None,
            is_custom_role_permission_enabled=False,
        )

        fake_partner = type(
            "Partner",
            (),
            {
                "id": UUID("22222222-2222-2222-2222-222222222222"),
                "name": "Beta",
                "company_legal_name": "Beta Corp",
                "gst_no": "GST789",
                "cin_no": "CIN101",
                "active_license": 50,
                "description": "Another Partner",
                "created_at": 17000001,
                "is_active": True,
            },
        )()

        fake_query = select(Partner)

        # Mock DB calls
        self.partner_repository_mock.execute_partner_filter_scalar_query.return_value = (
            1
        )
        self.partner_repository_mock.execure_partner_filter_query.side_effect = [
            [(fake_partner,)],  # First call: returns partners
            []  # Second call: returns counts
        ]

        # No admin users
        self.user_service_mock.get_admin_credentials_by_hierarchy.return_value = []

        # Mock partner metadata
        self.partner_meta_data_service_mock.get_partner_meta_data_by_partner_ids.return_value = {
            2: {"is_talko_free_trial__enabled": False}
        }

        # Mock builder
        with patch(
            "src.components.partner.partner_filter_builder.PartnerFilterBuilder"
        ) as MockBuilder:
            mock_builder = MockBuilder.return_value
            mock_builder.build_query = AsyncMock(return_value=fake_query)

            response = await self.filter_service.enlist_partners_dynamically(
                filter_request,
                user_service=self.user_service_mock,
                partner_meta_data_service=self.partner_meta_data_service_mock,
            )

        assert response.total_count == 1
        assert len(response.partners_data) == 1
        assert response.partners_data[0].name == "Beta"
        assert response.partners_data[0].email is None
        assert response.partners_data[0].phone_number is None

    @pytest.mark.asyncio
    async def test_enlist_partners_dynamically_partner_exception(self):
        filter_request = PartnerFilterRequest(
            filters=[],
            order_by=[],
            limit=10,
            offset=0,
            dashboard_filters=None,
            is_custom_role_permission_enabled=False,
        )

        self.partner_repository_mock.execute_partner_filter_scalar_query.side_effect = (
            PartnerException("DB error")
        )
        fake_query = select(Partner)

        with patch(
            "src.components.partner.partner_filter_builder.PartnerFilterBuilder"
        ) as MockBuilder:
            mock_builder = MockBuilder.return_value
            mock_builder.build_query = AsyncMock(return_value=fake_query)

            with pytest.raises(PartnerException):
                await self.filter_service.enlist_partners_dynamically(
                    filter_request, user_service=self.user_service_mock
                )

        self.mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_enlist_partners_dynamically_generic_exception(self):
        filter_request = PartnerFilterRequest(
            filters=[],
            order_by=[],
            limit=10,
            offset=0,
            dashboard_filters=None,
            is_custom_role_permission_enabled=False,
        )

        self.partner_repository_mock.execute_partner_filter_scalar_query.side_effect = (
            Exception("Unexpected error")
        )
        fake_query = select(Partner)

        with patch(
            "src.components.partner.partner_filter_builder.PartnerFilterBuilder"
        ) as MockBuilder:
            mock_builder = MockBuilder.return_value
            mock_builder.build_query = AsyncMock(return_value=fake_query)

            with pytest.raises(Exception):
                await self.filter_service.enlist_partners_dynamically(
                    filter_request, user_service=self.user_service_mock
                )

        self.mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_enlist_partners_dashboard_filter_last_seven_days(self):
        now = int(time.time() * 1000)

        filter_request = PartnerFilterRequest(
            filters=[],
            order_by=[],
            limit=5,
            offset=0,
            dashboard_filters=DashboardFilters.PARTNERS_LAST_SEVEN_DAYS,
            is_custom_role_permission_enabled=False,
        )

        fake_partner = type(
            "Partner",
            (),
            {
                "id": UUID("66666666-6666-6666-6666-666666666666"),
                "name": "RecentPartner",
                "company_legal_name": "Recent Corp",
                "gst_no": "GSTRECENT",
                "cin_no": "CINRECENT",
                "active_license": 10,
                "description": "Recent Partner",
                "created_at": now,
                "is_active": True,
            },
        )()

        fake_query = select(Partner)

        # Mock repository
        self.partner_repository_mock.execute_partner_filter_scalar_query.return_value = (
            1
        )
        self.partner_repository_mock.execure_partner_filter_query.side_effect = [
            [(fake_partner,)],  # First call: returns partners
            []  # Second call: returns counts
        ]

        # No admin users
        self.user_service_mock.get_admin_credentials_by_hierarchy.return_value = []

        

        # Mock metadata service (free trial flag)
        self.partner_meta_data_service_mock.get_partner_meta_data_by_partner_ids.return_value = {
            6: {"is_talko_free_trial__enabled": False}
        }

        # Mock builder
        with patch(
            "src.components.partner.partner_filter_builder.PartnerFilterBuilder"
        ) as MockBuilder:
            mock_builder = MockBuilder.return_value
            mock_builder.build_query = AsyncMock(return_value=fake_query)

            response = await self.filter_service.enlist_partners_dynamically(
                filter_request,
                user_service=self.user_service_mock,
                partner_meta_data_service=self.partner_meta_data_service_mock,
            )

        assert response.total_count == 1
        assert len(response.partners_data) == 1
        assert response.partners_data[0].id == UUID("66666666-6666-6666-6666-666666666666")

    @pytest.mark.asyncio
    async def test_enlist_partners_dashboard_filter_gt_fifty_licenses(self):
        filter_request = PartnerFilterRequest(
            filters=[],
            order_by=[],
            limit=5,
            offset=0,
            dashboard_filters=DashboardFilters.PARTNERS_GT_FIFTY_LICENSES,
            is_custom_role_permission_enabled=False,
        )

        fake_partner = type(
            "Partner",
            (),
            {
                "id": UUID("55555555-5555-5555-5555-555555555555"),
                "name": "BigPartner",
                "company_legal_name": "Big Corp",
                "gst_no": "GSTBIG",
                "cin_no": "CINBIG",
                "active_license": 51,
                "description": "Big Partner",
                "created_at": 17000004,
                "is_active": True,
            },
        )()

        fake_query = select(Partner)

        # Mock repo
        self.partner_repository_mock.execute_partner_filter_scalar_query.return_value = (
            1
        )
        self.partner_repository_mock.execure_partner_filter_query.side_effect = [
            [(fake_partner,)],  # First call: returns partners
            []  # Second call: returns counts
        ]

        # No admin users
        self.user_service_mock.get_admin_credentials_by_hierarchy.return_value = []

        # Required mocks
        self.partner_meta_data_service_mock.get_partner_meta_data_by_partner_ids.return_value = {
            5: {"is_talko_free_trial__enabled": False}
        }

        with patch(
            "src.components.partner.partner_filter_builder.PartnerFilterBuilder"
        ) as MockBuilder:
            mock_builder = MockBuilder.return_value
            mock_builder.build_query = AsyncMock(return_value=fake_query)

            response = await self.filter_service.enlist_partners_dynamically(
                filter_request,
                user_service=self.user_service_mock,
                partner_meta_data_service=self.partner_meta_data_service_mock,
            )

        assert response.total_count == 1
        assert response.partners_data[0].active_license > 50

    @pytest.mark.asyncio
    async def test_enlist_partners_dashboard_filter_talko(self):
        filter_request = PartnerFilterRequest(
            filters=[],
            order_by=[],
            limit=5,
            offset=0,
            dashboard_filters=DashboardFilters.PARTNERS_USING_TALKO,
            is_custom_role_permission_enabled=False,
        )

        fake_partner = type(
            "Partner",
            (),
            {
                "id": UUID("44444444-4444-4444-4444-444444444444"),
                "name": "TalkoPartner",
                "company_legal_name": "Talko Corp",
                "gst_no": "GSTTALKO",
                "cin_no": "CINTALKO",
                "active_license": 20,
                "description": "Talko Partner",
                "created_at": 17000003,
                "is_active": True,
            },
        )()

        fake_query = select(Partner)

        # Repo mocks
        self.partner_repository_mock.execute_partner_filter_scalar_query.return_value = (
            1
        )
        self.partner_repository_mock.execure_partner_filter_query.side_effect = [
            [(fake_partner,)],  # First call: returns partners
            []  # Second call: returns counts
        ]

        # No admin users
        self.user_service_mock.get_admin_credentials_by_hierarchy.return_value = []

        # Free trial mock
        self.partner_meta_data_service_mock.get_partner_meta_data_by_partner_ids.return_value = {
            4: {"is_talko_free_trial__enabled": False}
        }

        with patch(
            "src.components.partner.partner_filter_builder.PartnerFilterBuilder"
        ) as MockBuilder:
            mock_builder = MockBuilder.return_value
            mock_builder.build_query = AsyncMock(return_value=fake_query)

            response = await self.filter_service.enlist_partners_dynamically(
                filter_request,
                user_service=self.user_service_mock,
                partner_meta_data_service=self.partner_meta_data_service_mock,
            )

        assert response.total_count == 1
        assert response.partners_data[0].name == "TalkoPartner"

    @pytest.mark.asyncio
    async def test_enlist_partners_custom_role_permission_enabled(self):
        filter_request = PartnerFilterRequest(
            filters=[],
            order_by=[],
            limit=5,
            offset=0,
            dashboard_filters=None,
            is_custom_role_permission_enabled=True,
        )

        fake_partner = type(
            "Partner",
            (),
            {
                "id": UUID("33333333-3333-3333-3333-333333333333"),
                "name": "CustomRole",
                "company_legal_name": "CustomRole Corp",
                "gst_no": "GST999",
                "cin_no": "CIN999",
                "active_license": 10,
                "description": "Custom Role Partner",
                "created_at": 17000002,
                "is_active": True,
            },
        )()

        fake_query = select(Partner)

        # Repo mocks
        self.partner_repository_mock.execute_partner_filter_scalar_query.return_value = (
            1
        )
        self.partner_repository_mock.execure_partner_filter_query.side_effect = [
            [(fake_partner,)],  # First call: returns partners
            []  # Second call: returns counts
        ]

        # No admin users
        self.user_service_mock.get_admin_credentials_by_hierarchy.return_value = []

        # Required mocks
        self.partner_meta_data_service_mock.get_partner_meta_data_by_partner_ids.return_value = {
            3: {"is_talko_free_trial__enabled": False}
        }

        with patch(
            "src.components.partner.partner_filter_builder.PartnerFilterBuilder"
        ) as MockBuilder:
            mock_builder = MockBuilder.return_value
            mock_builder.build_query = AsyncMock(return_value=fake_query)

            response = await self.filter_service.enlist_partners_dynamically(
                filter_request,
                user_service=self.user_service_mock,
                partner_meta_data_service=self.partner_meta_data_service_mock,
            )

        assert response.total_count == 1
        assert response.partners_data[0].name == "CustomRole"

    def test_defaults(self):
        req = PartnerFilterRequest()
        assert req.is_custom_role_permission_enabled is False
        assert req.dashboard_filters is None
        assert isinstance(req.filters, list) and req.filters == []
        assert isinstance(req.order_by, list) and req.order_by == []
        assert req.limit == 100
        assert req.offset == 0


    @pytest.mark.parametrize(
        "limit, should_raise",
        [
            (1, False),
            (500, False),
            (0, True),     # below minimum
            (501, True),   # above maximum
        ],
    )
    def test_limit_bounds(self, limit, should_raise):
        if should_raise:
            with pytest.raises(ValidationError):
                PartnerFilterRequest(limit=limit)
        else:
            req = PartnerFilterRequest(limit=limit)
            assert req.limit == limit


    def test_offset_negative_raises(self):
        with pytest.raises(ValidationError):
            PartnerFilterRequest(offset=-1)


    @pytest.mark.parametrize(
        "value",
        [
            123,           # int
            "123",         # numeric string
        ],
    )
    def test_filters_id_valid(self, value):
        filters = [{"field": "id", "operator": "=", "value": value}]
        req = PartnerFilterRequest(filters=filters)
        assert req.filters[0]["value"] == value


    def test_filters_id_non_numeric_raises(self):
        filters = [{"field": "id", "operator": "=", "value": "abc"}]
        with pytest.raises(ValidationError) as excinfo:
            PartnerFilterRequest(filters=filters)
        assert "Please enter a valid numeric ID" in str(excinfo.value)


    def test_filters_id_exceeds_max_int_raises(self):
        filters = [{"field": "id", "operator": "=", "value": str(MAX_INT + 1)}]
        with pytest.raises(ValidationError) as excinfo:
            PartnerFilterRequest(filters=filters)
        assert "ID exceeds maximum limit" in str(excinfo.value)


    def test_filters_id_negative_raises(self):
        filters = [{"field": "id", "operator": "=", "value": "-1"}]
        with pytest.raises(ValidationError) as excinfo:
            PartnerFilterRequest(filters=filters)
        assert "ID cannot be negative" in str(excinfo.value)