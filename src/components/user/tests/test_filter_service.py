from uuid import UUID
import pytest
from sqlalchemy import select
from src.components.user.models import User
from unittest.mock import AsyncMock, patch, MagicMock
from src.components.user.schema import UserRoleFilterRequest, UserRoleCombinedResponse, PaginatedUserRoleResponse
from src.exceptions import UserException
from src.components.user.filter_service import FilterService

from pydantic import ValidationError
MAX_INT = 2147483647


@pytest.mark.asyncio
class TestFilterService:

    @pytest.fixture(autouse=True)
    def setup_class(self, mock_logger):
        self.user_repository_mock = AsyncMock()
        self.mock_logger = mock_logger
        self.filter_service = FilterService(
            user_repository=self.user_repository_mock, console_service_logger=self.mock_logger
        )

    @pytest.mark.asyncio
    async def test_get_user_data_success_with_country_and_parent(self):
        filter_request = UserRoleFilterRequest(
            filters=[{"field": "user_name", "operator": "=", "value": "John"}],
            order_by=[{"field": "created_at", "direction": "DESC"}],
            partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            limit=10,
            offset=1,
        )

        # Fake country and parent objects
        fake_country = type("Country", (), {"name": "USA"})()
        fake_parent = type("Parent", (), {"name": "ParentName"})()

        # Fake user with country and parent attributes
        fake_user = type("User", (), {
            "id": UUID("11111111-1111-1111-1111-111111111111"), "name": "John", "email": "john@example.com",
            "phone_number": "123", "is_active": True, "role_id": UUID("22222222-2222-2222-2222-222222222222"),
            "designation": "Engineer", "description": "Test User",
            "created_at": 17000000, "partner_id": UUID("11111111-1111-1111-1111-111111111111"),
            "country": fake_country, "country_id": UUID("10101010-1010-1010-1010-101010101010"),
            "parent": fake_parent, "parent_id": UUID("20202020-2020-2020-2020-202020202020"),
            "state_id": UUID("55555555-5555-5555-5555-555555555555"), "city_id": UUID("66666666-6666-6666-6666-666666666666"), "updated_at": 17000002, "updated_by": UUID("33333333-3333-3333-3333-333333333333")
        })()

        fake_role = type("Role", (), {
            "id": UUID("22222222-2222-2222-2222-222222222222"), "name": "Admin", "description": "Role description",
            "is_active": True, "created_at": 17000000
        })()

        fake_query = select(User)

        self.user_repository_mock.execute_user_filter_scalar_query.return_value = 1
        self.user_repository_mock.execure_user_filter_query.return_value = [(fake_user, fake_role)]

        with patch("src.components.user.filter_service.UserRoleFilterBuilder") as MockBuilder:
            mock_builder = MockBuilder.return_value
            mock_builder.build_query = AsyncMock(return_value=fake_query)

            response = await self.filter_service.get_user_data(filter_request)

        assert response.total_count == 1
        assert len(response.data) == 1
        assert response.data[0].name == "John"
        assert response.data[0].country_name == "USA"
        assert response.data[0].parent_name == "ParentName"

    @pytest.mark.asyncio
    async def test_get_user_data_success_without_country_and_parent(self):
        filter_request = UserRoleFilterRequest(
            filters=[{"field": "user_name", "operator": "=", "value": "Jane"}],
            order_by=[{"field": "created_at", "direction": "DESC"}],
            partner_id= UUID("11111111-1111-1111-1111-111111111111"),
            limit=10,
            offset=1,
        )

        fake_user = type("User", (), {
            "id": UUID("22222222-2222-2222-2222-222222222222"), "name": "Jane", "email": "jane@example.com",
            "phone_number": "456", "is_active": True, "role_id": UUID("33333333-3333-3333-3333-333333333333"),
            "designation": "Manager", "description": "Another User",
            "created_at": 17000001, "partner_id": UUID("11111111-1111-1111-1111-111111111111"),
            "country": None, "country_id": None,
            "parent": None, "parent_id": None,
            "state_id": None, "city_id": None, "updated_at": 17000003, "updated_by": None
        })()

        fake_role = type("Role", (), {
            "id": UUID("33333333-3333-3333-3333-333333333333"), "name": "User", "description": "Role description",
            "is_active": True, "created_at": 17000001
        })()

        fake_query = select(User)

        self.user_repository_mock.execute_user_filter_scalar_query.return_value = 1
        self.user_repository_mock.execure_user_filter_query.return_value = [(fake_user, fake_role)]

        with patch("src.components.user.filter_service.UserRoleFilterBuilder") as MockBuilder:
            mock_builder = MockBuilder.return_value
            mock_builder.build_query = AsyncMock(return_value=fake_query)

            response = await self.filter_service.get_user_data(filter_request)

        assert response.total_count == 1
        assert len(response.data) == 1
        assert response.data[0].name == "Jane"
        assert response.data[0].country_name is None
        assert response.data[0].parent_name is None

    @pytest.mark.asyncio
    async def test_get_user_data_user_exception(self):
        """Test raising UserException from repository."""
        filter_request = UserRoleFilterRequest(
            filters=[], order_by=[], partner_id= UUID("11111111-1111-1111-1111-111111111111"), limit=10, offset=1
        )

        # Make execute_user_filter_scalar_query raise a UserException
        self.user_repository_mock.execute_user_filter_scalar_query.side_effect = UserException("DB error")

        # Use real SQLAlchemy query so .subquery() works
        fake_query = select(User)

        with patch("src.components.user.filter_service.UserRoleFilterBuilder") as MockBuilder:
            mock_builder = MockBuilder.return_value
            mock_builder.build_query = AsyncMock(return_value=fake_query)

            # Assert that UserException is raised
            with pytest.raises(UserException):
                await self.filter_service.get_user_data(filter_request)

        self.mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_get_user_data_generic_exception(self):
        """Test raising generic Exception."""
        filter_request = UserRoleFilterRequest(filters=[], order_by=[], partner_id= UUID("11111111-1111-1111-1111-111111111111"), limit=10, offset=1)

        self.user_repository_mock.execute_user_filter_scalar_query.side_effect = Exception("Unexpected error")

        with patch("src.components.user.filter_service.UserRoleFilterBuilder") as MockBuilder:
            mock_builder = MockBuilder.return_value
            mock_builder.build_query.return_value = "fake_query"

            with pytest.raises(Exception):
                await self.filter_service.get_user_data(filter_request)

        self.mock_logger.error.assert_called()

    def test_defaults(self):
        req = UserRoleFilterRequest(partner_id= UUID("11111111-1111-1111-1111-111111111111"))
        assert req.partner_id== UUID("11111111-1111-1111-1111-111111111111")
        assert isinstance(req.filters, list) and req.filters == []
        assert isinstance(req.order_by, list) and req.order_by == []
        assert req.limit == 100
        assert req.offset == 0


    @pytest.mark.parametrize(
        "limit, should_raise",
        [
            (1, False),
            (500, False),
            (0, True),    # below minimum
            (501, True),  # above maximum
        ],
    )
    def test_limit_bounds(self, limit, should_raise):
        if should_raise:
            with pytest.raises(ValidationError):
                UserRoleFilterRequest(partner_id= UUID("11111111-1111-1111-1111-111111111111"), limit=limit)
        else:
            req = UserRoleFilterRequest(partner_id= UUID("11111111-1111-1111-1111-111111111111"), limit=limit)
            assert req.limit == limit


    def test_offset_negative_raises(self):
        with pytest.raises(ValidationError):
            UserRoleFilterRequest(partner_id= UUID("11111111-1111-1111-1111-111111111111"), offset=-1)


    @pytest.mark.parametrize(
        "value",
        [
            123,    # int
            "123",  # numeric string
        ],
    )
    def test_filters_id_valid(self, value):
        filters = [{"field": "id", "operator": "=", "value": value}]
        req = UserRoleFilterRequest(partner_id= UUID("11111111-1111-1111-1111-111111111111"), filters=filters)
        assert req.filters[0]["value"] == value


    def test_filters_id_non_numeric_raises(self):
        filters = [{"field": "id", "operator": "=", "value": "abc"}]
        with pytest.raises(ValidationError) as excinfo:
            UserRoleFilterRequest(partner_id= UUID("11111111-1111-1111-1111-111111111111"), filters=filters)
        assert "Please enter a valid numeric ID" in str(excinfo.value)


    def test_filters_id_exceeds_max_int_raises(self):
        filters = [{"field": "id", "operator": "=", "value": str(MAX_INT + 1)}]
        with pytest.raises(ValidationError) as excinfo:
            UserRoleFilterRequest(partner_id= UUID("11111111-1111-1111-1111-111111111111"), filters=filters)
        assert "ID exceeds maximum limit" in str(excinfo.value)


    def test_filters_id_negative_raises(self):
        filters = [{"field": "id", "operator": "=", "value": "-1"}]
        with pytest.raises(ValidationError) as excinfo:
            UserRoleFilterRequest(partner_id= UUID("11111111-1111-1111-1111-111111111111"), filters=filters)
        assert "ID cannot be negative" in str(excinfo.value)

