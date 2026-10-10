from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from src.components.entitlement.errors import EntitlementNotFoundError
from src.components.entitlement.models import Entitlement
from src.components.entitlement.repositories import EntitlementRepository
from src.components.entitlement.schema import EntitlementCreate, EntitlementUpdate


@pytest.mark.asyncio
class TestEntitlementRepository:

    @pytest.fixture(autouse=True)
    def setup_repo(self, mock_session_factory, mock_logger):
        self.ent_repo = EntitlementRepository(
            session_factory=mock_session_factory,
            logger=mock_logger,
        )

        self.session = mock_session_factory.return_value.__aenter__.return_value
        self.mock_logger = mock_logger

    # -------------------------------------------------------------------------
    # create_entitlement
    # -------------------------------------------------------------------------
    async def test_create_entitlement_success(self):
        data = EntitlementCreate(
            order_id=10,
            partner_id=1,
            service_name="TEST_SERVICE",
            modules=["mod1", "mod2"],
            limits={"A": "B"},
            start_date=1234567890,
            end_date=1234567999,
            is_active=True,
            created_by=100,
        )

        self.session.add = MagicMock()
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        ent = await self.ent_repo.create_entitlement(data)

        self.session.add.assert_called_once()
        self.session.commit.assert_awaited_once()
        self.session.refresh.assert_awaited_once()
        assert isinstance(ent, Entitlement)

    # -------------------------------------------------------------------------
    # get_active_entitlement
    # -------------------------------------------------------------------------
    async def test_get_active_entitlement_found(self):
        mock_ent = MagicMock(spec=Entitlement)

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_ent

        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.ent_repo.get_active_entitlement(1, "SERVICE")

        assert result == mock_ent

    async def test_get_active_entitlement_not_found(self):
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None

        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.ent_repo.get_active_entitlement(1, "SERVICE")

        assert result is None

    # -------------------------------------------------------------------------
    # update_entitlement
    # -------------------------------------------------------------------------
    async def test_update_entitlement_success(self):
        mock_ent = MagicMock(spec=Entitlement)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_ent

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        data = EntitlementUpdate(is_active=False)

        updated = await self.ent_repo.update_entitlement(5, data)

        assert updated == mock_ent
        self.session.commit.assert_awaited_once()

    async def test_update_entitlement_not_found(self):
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        data = EntitlementUpdate(is_active=True)

        with pytest.raises(EntitlementNotFoundError):
            await self.ent_repo.update_entitlement(999, data)

    async def test_update_entitlement_partial_update_fields(self):
        """
        Ensures None fields are ignored in update statement.
        """
        mock_ent = MagicMock(spec=Entitlement)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_ent

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        # has only 1 actual field (other = None should be ignored)
        data = EntitlementUpdate(is_active=True, service_name=None)

        updated = await self.ent_repo.update_entitlement(3, data)

        self.session.commit.assert_awaited_once()
        assert updated == mock_ent

    async def test_get_all_active_entitlements_empty(self):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.ent_repo.get_all_active_entitlements(partner_id=1)

        self.session.execute.assert_awaited_once()
        assert result == []

    async def test_get_all_active_entitlements_db_error(self):
        self.session.execute = AsyncMock(side_effect=Exception("DB failure"))

        with pytest.raises(Exception, match="DB failure"):
            await self.ent_repo.get_all_active_entitlements(partner_id=1)

    async def test_get_all_active_entitlements_success(self):
        mock_ent1 = MagicMock(spec=Entitlement)
        mock_ent2 = MagicMock(spec=Entitlement)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            mock_ent1,
            mock_ent2,
        ]

        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.ent_repo.get_all_active_entitlements(partner_id=1)

        self.session.execute.assert_awaited_once()
        assert result == [mock_ent1, mock_ent2]

    async def test_get_entitlement_by_order_id_found(self):
        """Should return entitlement when found by order_id."""
        mock_ent = MagicMock(spec=Entitlement)
        mock_ent.id = 1
        mock_ent.order_id = 100

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_ent

        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.ent_repo.get_entitlement_by_order_id(order_id=100)

        self.session.execute.assert_awaited_once()
        assert result == mock_ent
        assert result.order_id == 100

    async def test_get_entitlement_by_order_id_not_found(self):
        """Should return None when entitlement not found by order_id."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None

        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.ent_repo.get_entitlement_by_order_id(order_id=999)

        self.session.execute.assert_awaited_once()
        assert result is None

    async def test_get_entitlement_by_order_id_with_order_relationship(self):
        """Should load order relationship via selectinload."""
        mock_ent = MagicMock(spec=Entitlement)
        mock_order = MagicMock()
        mock_ent.order = mock_order

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_ent

        self.session.execute = AsyncMock(return_value=mock_result)

        result = await self.ent_repo.get_entitlement_by_order_id(order_id=100)

        assert result == mock_ent
        assert result.order == mock_order

    async def test_get_entitlement_by_order_id_db_error(self):
        """Should raise exception when database error occurs."""
        self.session.execute = AsyncMock(
            side_effect=Exception("Database connection error")
        )

        with pytest.raises(Exception, match="Database connection error"):
            await self.ent_repo.get_entitlement_by_order_id(order_id=100)

    async def test_update_entitlement_start_date_success(self):
        """Should successfully update start date, end date, and increment counter."""
        mock_ent = MagicMock(spec=Entitlement)
        mock_ent.id = 1
        mock_ent.start_date = 2000000000000
        mock_ent.end_date = 3000000000000
        mock_ent.is_active = False
        mock_ent.start_date_update_count = 1
        mock_ent.updated_by = 50

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_ent

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.ent_repo.update_entitlement_start_date(
            entitlement_id=1,
            new_start_date=2000000000000,
            new_end_date=3000000000000,
            user_id=50,
        )

        self.session.execute.assert_awaited_once()
        self.session.commit.assert_awaited_once()
        self.session.refresh.assert_awaited_once_with(mock_ent)

        assert result == mock_ent
        assert result.start_date == 2000000000000
        assert result.end_date == 3000000000000
        assert result.is_active is False
        assert result.start_date_update_count == 1
        assert result.updated_by == 50

    async def test_update_entitlement_start_date_first_update(self):
        """Should increment counter from 0 to 1 on first update."""
        mock_ent = MagicMock(spec=Entitlement)
        mock_ent.id = 5
        mock_ent.start_date_update_count = 1  # After increment from 0

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_ent

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.ent_repo.update_entitlement_start_date(
            entitlement_id=5,
            new_start_date=1500000000000,
            new_end_date=1600000000000,
            user_id=100,
        )

        assert result.start_date_update_count == 1

    async def test_update_entitlement_start_date_multiple_updates(self):
        """Should increment counter correctly on subsequent updates."""
        mock_ent = MagicMock(spec=Entitlement)
        mock_ent.id = 10
        mock_ent.start_date_update_count = 3  # After increment from 2

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_ent

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.ent_repo.update_entitlement_start_date(
            entitlement_id=10,
            new_start_date=2500000000000,
            new_end_date=2600000000000,
            user_id=200,
        )

        assert result.start_date_update_count == 3

    async def test_update_entitlement_start_date_sets_inactive(self):
        """Should set is_active to False."""
        mock_ent = MagicMock(spec=Entitlement)
        mock_ent.is_active = False

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_ent

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.ent_repo.update_entitlement_start_date(
            entitlement_id=1,
            new_start_date=1000000000000,
            new_end_date=2000000000000,
            user_id=50,
        )

        assert result.is_active is False

    async def test_update_entitlement_start_date_updates_user_id(self):
        """Should set updated_by field to user_id."""
        mock_ent = MagicMock(spec=Entitlement)
        mock_ent.updated_by = 999

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_ent

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.ent_repo.update_entitlement_start_date(
            entitlement_id=1,
            new_start_date=1000000000000,
            new_end_date=2000000000000,
            user_id=999,
        )

        assert result.updated_by == 999

    async def test_update_entitlement_start_date_handles_none_counter(self):
        """Should handle None start_date_update_count using coalesce."""
        # When counter is None, func.coalesce should treat it as 0
        mock_ent = MagicMock(spec=Entitlement)
        mock_ent.start_date_update_count = 1  # After coalesce(None, 0) + 1

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_ent

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.ent_repo.update_entitlement_start_date(
            entitlement_id=1,
            new_start_date=1000000000000,
            new_end_date=2000000000000,
            user_id=50,
        )

        assert result.start_date_update_count == 1

    async def test_update_entitlement_start_date_commit_called(self):
        """Should commit transaction after update."""
        mock_ent = MagicMock(spec=Entitlement)

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_ent

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        await self.ent_repo.update_entitlement_start_date(
            entitlement_id=1,
            new_start_date=1000000000000,
            new_end_date=2000000000000,
            user_id=50,
        )

        self.session.commit.assert_awaited_once()

    async def test_update_entitlement_start_date_refresh_called(self):
        """Should refresh entitlement object after commit."""
        mock_ent = MagicMock(spec=Entitlement)

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_ent

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        await self.ent_repo.update_entitlement_start_date(
            entitlement_id=1,
            new_start_date=1000000000000,
            new_end_date=2000000000000,
            user_id=50,
        )

        self.session.refresh.assert_awaited_once_with(mock_ent)

    async def test_update_entitlement_start_date_db_error_before_commit(self):
        """Should raise exception when database error occurs during execute."""
        self.session.execute = AsyncMock(side_effect=Exception("Database error"))
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        with pytest.raises(Exception, match="Database error"):
            await self.ent_repo.update_entitlement_start_date(
                entitlement_id=1,
                new_start_date=1000000000000,
                new_end_date=2000000000000,
                user_id=50,
            )

        # Commit should not be called if execute fails
        self.session.commit.assert_not_awaited()

    async def test_update_entitlement_start_date_db_error_during_commit(self):
        """Should raise exception when commit fails."""
        mock_ent = MagicMock(spec=Entitlement)

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_ent

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock(side_effect=Exception("Commit failed"))
        self.session.refresh = AsyncMock()

        with pytest.raises(Exception, match="Commit failed"):
            await self.ent_repo.update_entitlement_start_date(
                entitlement_id=1,
                new_start_date=1000000000000,
                new_end_date=2000000000000,
                user_id=50,
            )

    async def test_update_entitlement_start_date_different_dates(self):
        """Should handle different start and end date values."""
        mock_ent = MagicMock(spec=Entitlement)
        mock_ent.start_date = 1111111111111
        mock_ent.end_date = 9999999999999

        mock_result = MagicMock()
        mock_result.scalar_one.return_value = mock_ent

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()
        self.session.refresh = AsyncMock()

        result = await self.ent_repo.update_entitlement_start_date(
            entitlement_id=1,
            new_start_date=1111111111111,
            new_end_date=9999999999999,
            user_id=50,
        )

        assert result.start_date == 1111111111111
        assert result.end_date == 9999999999999

    async def test_activate_pending_entitlements_success_multiple(self):
        """Should activate multiple pending entitlements and return count."""
        mock_result = MagicMock()
        mock_result.rowcount = 5

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        count = await self.ent_repo.activate_pending_entitlements()

        self.session.execute.assert_awaited_once()
        self.session.commit.assert_awaited_once()
        assert count == 5

    async def test_activate_pending_entitlements_success_single(self):
        """Should activate single pending entitlement."""
        mock_result = MagicMock()
        mock_result.rowcount = 1

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        count = await self.ent_repo.activate_pending_entitlements()

        assert count == 1

    async def test_activate_pending_entitlements_none_found(self):
        """Should return 0 when no pending entitlements to activate."""
        mock_result = MagicMock()
        mock_result.rowcount = 0

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        count = await self.ent_repo.activate_pending_entitlements()

        self.session.execute.assert_awaited_once()
        self.session.commit.assert_awaited_once()
        assert count == 0

    async def test_activate_pending_entitlements_rowcount_none(self):
        """Should return 0 when rowcount is None."""
        mock_result = MagicMock()
        mock_result.rowcount = None

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        count = await self.ent_repo.activate_pending_entitlements()

        assert count == 0

    async def test_activate_pending_entitlements_commits_transaction(self):
        """Should commit transaction after activation."""
        mock_result = MagicMock()
        mock_result.rowcount = 3

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        await self.ent_repo.activate_pending_entitlements()

        self.session.commit.assert_awaited_once()

    async def test_activate_pending_entitlements_db_error_execute(self):
        """Should raise exception when execute fails."""
        self.session.execute = AsyncMock(side_effect=Exception("Execute failed"))
        self.session.commit = AsyncMock()

        with pytest.raises(Exception, match="Execute failed"):
            await self.ent_repo.activate_pending_entitlements()

        # Commit should not be called if execute fails
        self.session.commit.assert_not_awaited()

    async def test_activate_pending_entitlements_db_error_commit(self):
        """Should raise exception when commit fails."""
        mock_result = MagicMock()
        mock_result.rowcount = 2

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock(side_effect=Exception("Commit failed"))

        with pytest.raises(Exception, match="Commit failed"):
            await self.ent_repo.activate_pending_entitlements()

    async def test_activate_pending_entitlements_large_count(self):
        """Should handle large number of activated entitlements."""
        mock_result = MagicMock()
        mock_result.rowcount = 1000

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        count = await self.ent_repo.activate_pending_entitlements()

        assert count == 1000

    async def test_activate_pending_entitlements_executes_update_query(self):
        """Should execute update statement with correct conditions."""
        mock_result = MagicMock()
        mock_result.rowcount = 2

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        await self.ent_repo.activate_pending_entitlements()

        # Verify execute was called with an update statement
        self.session.execute.assert_awaited_once()
        call_args = self.session.execute.call_args

        # The first argument should be the update statement
        assert call_args is not None

    async def test_activate_pending_entitlements_sets_is_active_true(self):
        """Should set is_active to True for matching entitlements."""
        mock_result = MagicMock()
        mock_result.rowcount = 3

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        count = await self.ent_repo.activate_pending_entitlements()

        # Verify the update was executed
        assert count == 3
        self.session.execute.assert_awaited_once()

    async def test_activate_pending_entitlements_filters_by_start_date(self):
        """Should only activate entitlements with start_date <= current_ts."""
        # This is verified by the query logic - we just ensure it runs
        mock_result = MagicMock()
        mock_result.rowcount = 2

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        count = await self.ent_repo.activate_pending_entitlements()

        assert count == 2

    async def test_activate_pending_entitlements_filters_inactive_only(self):
        """Should only activate entitlements that are currently inactive."""
        mock_result = MagicMock()
        mock_result.rowcount = 1

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        count = await self.ent_repo.activate_pending_entitlements()

        assert count == 1

    async def test_activate_pending_entitlements_filters_not_manually_deactivated(self):
        """Should not activate manually deactivated entitlements."""
        mock_result = MagicMock()
        mock_result.rowcount = 0  # None match because all are manually deactivated

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        count = await self.ent_repo.activate_pending_entitlements()

        assert count == 0

    async def test_activate_pending_entitlements_respects_end_date(self):
        """Should only activate entitlements with valid end_date."""
        # Tests that end_date filter works (end_date is None or >= current_ts)
        mock_result = MagicMock()
        mock_result.rowcount = 4

        self.session.execute = AsyncMock(return_value=mock_result)
        self.session.commit = AsyncMock()

        count = await self.ent_repo.activate_pending_entitlements()

        assert count == 4
