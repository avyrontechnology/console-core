from uuid import UUID
from unittest.mock import AsyncMock, Mock

import pytest

from src.components.plan.errors import PlanNotFoundError
from src.components.plan.models import Plan
from src.components.plan.repositories import PlanRepository
from src.components.plan.schema import PlanBase, PlanUpdate
from src.components.plan.services import PlanService
from src.loggers.console_service_logger import ConsoleServiceLogger


@pytest.mark.asyncio
class TestPlanService:

    @pytest.fixture(autouse=True)
    def setup(self):
        # Mocks
        self.repo = AsyncMock(spec=PlanRepository)
        self.logger = AsyncMock(spec=ConsoleServiceLogger)

        # Service instance
        self.service = PlanService(plan_repository=self.repo, logger=self.logger)

        # Mock data
        self.mock_plan = Mock(spec=Plan)
        self.mock_plan.id = UUID("11111111-1111-1111-1111-111111111111")
        self.mock_plan.name = "Test Plan"

        self.plan_base_data = Mock(spec=PlanBase)
        self.plan_base_data.name = "Test Plan"

        self.plan_update_data = Mock(spec=PlanUpdate)
        self.plan_update_data.name = "Updated Plan"

    # -------------------- create_plan --------------------

    async def test_create_plan_success(self):
        """Test successful plan creation."""
        self.repo.create_plan.return_value = self.mock_plan
        user_id= UUID("11111111-1111-1111-1111-111111111111")

        result = await self.service.create_plan(self.plan_base_data, user_id)

        assert result == self.mock_plan
        self.repo.create_plan.assert_called_once_with(self.plan_base_data, user_id)
        self.logger.info.assert_any_call("Service: create_plan started name=Test Plan")
        self.logger.info.assert_any_call("Service: create_plan completed id=11111111-1111-1111-1111-111111111111")

    async def test_create_plan_exception(self):
        """Test plan creation with unexpected exception."""
        self.repo.create_plan.side_effect = Exception("Database error")
        user_id= UUID("11111111-1111-1111-1111-111111111111")

        with pytest.raises(Exception, match="Database error"):
            await self.service.create_plan(self.plan_base_data, user_id)

        self.repo.create_plan.assert_called_once_with(self.plan_base_data, user_id)
        self.logger.error.assert_called_once()
        error_call_args = self.logger.error.call_args[0][0]
        assert (
            "Service: create_plan unexpected error name=Test Plan err="
            in error_call_args
        )

    # -------------------- get_active_plans --------------------

    async def test_get_active_plans_success_no_filters(self):
        """Test getting active plans without filters."""
        mock_plans = [self.mock_plan]
        self.repo.get_active_plans.return_value = mock_plans

        result = await self.service.get_active_plans()

        assert result == mock_plans
        self.repo.get_active_plans.assert_called_once_with(
            None, None, None, None
        )  # FIXED: Added 4th parameter (duration)
        self.logger.info.assert_any_call("Service: get_active_plans started")
        self.logger.info.assert_any_call("Service: get_active_plans returning 1 plans")

    async def test_get_active_plans_success_with_filters(self):
        """Test getting active plans with filters."""
        mock_plans = [self.mock_plan]
        self.repo.get_active_plans.return_value = mock_plans

        result = await self.service.get_active_plans(
            partner_id= UUID("11111111-1111-1111-1111-111111111111"), service_name="test_service", plan_type="premium"
        )

        assert result == mock_plans
        self.repo.get_active_plans.assert_called_once_with(
            UUID("11111111-1111-1111-1111-111111111111"), "test_service", "premium", None
        )  # FIXED: Added 4th parameter (duration=None)
        self.logger.info.assert_any_call("Service: get_active_plans started")
        self.logger.info.assert_any_call("Service: get_active_plans returning 1 plans")

    async def test_get_active_plans_empty_result(self):
        """Test getting active plans with empty result."""
        self.repo.get_active_plans.return_value = []

        result = await self.service.get_active_plans()

        assert result == []
        self.logger.info.assert_any_call("Service: get_active_plans returning 0 plans")

    async def test_get_active_plans_exception(self):
        """Test get active plans with unexpected exception."""
        self.repo.get_active_plans.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await self.service.get_active_plans()

        self.logger.error.assert_called_once()
        error_call_args = self.logger.error.call_args[0][0]
        assert "Service: get_active_plans unexpected error err=" in error_call_args

    # -------------------- get_plan_by_id --------------------

    async def test_get_plan_by_id_success(self):
        """Test successful plan retrieval by ID."""
        plan_id= UUID("11111111-1111-1111-1111-111111111111")
        self.repo.get_plan_by_id.return_value = self.mock_plan

        result = await self.service.get_plan_by_id(plan_id)

        assert result == self.mock_plan
        self.repo.get_plan_by_id.assert_called_once_with(plan_id)
        self.logger.info.assert_called_with("Service: get_plan_by_id started id=11111111-1111-1111-1111-111111111111")

    async def test_get_plan_by_id_not_found(self):
        """Test plan retrieval when plan is not found."""
        plan_id= UUID("99999999-9999-9999-9999-999999999999")
        self.repo.get_plan_by_id.return_value = None

        with pytest.raises(PlanNotFoundError):
            await self.service.get_plan_by_id(plan_id)

        self.repo.get_plan_by_id.assert_called_once_with(plan_id)
        self.logger.info.assert_any_call("Service: get_plan_by_id started id=99999999-9999-9999-9999-999999999999")
        self.logger.info.assert_any_call("Service: get_plan_by_id not found id=99999999-9999-9999-9999-999999999999")

    async def test_get_plan_by_id_exception(self):
        """Test get plan by ID with unexpected exception."""
        plan_id= UUID("11111111-1111-1111-1111-111111111111")
        self.repo.get_plan_by_id.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await self.service.get_plan_by_id(plan_id)

        self.logger.error.assert_called_once()
        error_call_args = self.logger.error.call_args[0][0]
        assert "Service: get_plan_by_id unexpected error err=" in error_call_args

    # -------------------- update_plan --------------------

    async def test_update_plan_success(self):
        """Test successful plan update."""
        plan_id= UUID("11111111-1111-1111-1111-111111111111")
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        updated_plan = Mock(spec=Plan)
        updated_plan.id = plan_id
        self.repo.update_plan.return_value = updated_plan

        result = await self.service.update_plan(plan_id, self.plan_update_data, user_id)

        assert result == updated_plan
        self.repo.update_plan.assert_called_once_with(
            plan_id, self.plan_update_data, user_id
        )
        self.logger.info.assert_any_call("Service: update_plan started id=11111111-1111-1111-1111-111111111111")
        self.logger.info.assert_any_call("Service: update_plan succeeded id=11111111-1111-1111-1111-111111111111")

    async def test_update_plan_not_found(self):
        """Test plan update when plan is not found."""
        plan_id= UUID("99999999-9999-9999-9999-999999999999")
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        self.repo.update_plan.return_value = None

        with pytest.raises(PlanNotFoundError):
            await self.service.update_plan(plan_id, self.plan_update_data, user_id)

        self.repo.update_plan.assert_called_once_with(
            plan_id, self.plan_update_data, user_id
        )
        self.logger.info.assert_any_call("Service: update_plan started id=99999999-9999-9999-9999-999999999999")
        self.logger.info.assert_any_call("Service: update_plan not found id=99999999-9999-9999-9999-999999999999")

    async def test_update_plan_exception(self):
        """Test plan update with unexpected exception."""
        plan_id= UUID("11111111-1111-1111-1111-111111111111")
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        self.repo.update_plan.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await self.service.update_plan(plan_id, self.plan_update_data, user_id)

        self.logger.error.assert_called_once()
        error_call_args = self.logger.error.call_args[0][0]
        assert "Service: update_plan unexpected error id=11111111-1111-1111-1111-111111111111 err=" in error_call_args

    # -------------------- delete_plan --------------------

    async def test_delete_plan_success(self):
        """Test successful plan deletion."""
        plan_id= UUID("11111111-1111-1111-1111-111111111111")
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        self.repo.delete_plan.return_value = True

        result = await self.service.delete_plan(plan_id, user_id)

        assert result is None
        self.repo.delete_plan.assert_called_once_with(plan_id, user_id)
        self.logger.info.assert_any_call("Service: delete_plan started id=11111111-1111-1111-1111-111111111111")
        self.logger.info.assert_any_call("Service: delete_plan completed id=11111111-1111-1111-1111-111111111111")

    async def test_delete_plan_not_found(self):
        """Test plan deletion when plan is not found."""
        plan_id= UUID("99999999-9999-9999-9999-999999999999")
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        self.repo.delete_plan.return_value = False

        with pytest.raises(PlanNotFoundError):
            await self.service.delete_plan(plan_id, user_id)

        self.repo.delete_plan.assert_called_once_with(plan_id, user_id)
        self.logger.info.assert_any_call("Service: delete_plan started id=99999999-9999-9999-9999-999999999999")
        self.logger.info.assert_any_call("Service: delete_plan not found id=99999999-9999-9999-9999-999999999999")

    async def test_delete_plan_exception(self):
        """Test plan deletion with unexpected exception."""
        plan_id= UUID("11111111-1111-1111-1111-111111111111")
        user_id= UUID("11111111-1111-1111-1111-111111111111")
        self.repo.delete_plan.side_effect = Exception("Database error")

        with pytest.raises(Exception, match="Database error"):
            await self.service.delete_plan(plan_id, user_id)

        self.logger.error.assert_called_once()
        error_call_args = self.logger.error.call_args[0][0]
        assert "Service: delete_plan unexpected error id=11111111-1111-1111-1111-111111111111 err=" in error_call_args
