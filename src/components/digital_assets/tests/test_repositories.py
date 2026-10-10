from unittest.mock import AsyncMock, MagicMock

import pytest
from src.components.digital_assets.constants import DigitalAssetEnum
from src.components.digital_assets.models import DigitalAssets
from src.components.digital_assets.repositories import DigitalAssetRepository


@pytest.mark.asyncio
class TestDigitalAssetRepository:

    async def test_get_digital_asset_by_partner_id_success(self):
        """Test retrieving a digital asset by partner ID and asset type successfully."""
        mock_asset = DigitalAssets(
            id=1,
            name="asset1",
            partner_id=123,
            version=1,
            asset_type=DigitalAssetEnum.CONSOLE_PARTNER_GST.value,
            additional_info={"key": "value"},
            created_by=1,
            updated_by=1,
        )

        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_asset

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__.return_value.execute = AsyncMock(
            return_value=mock_execute
        )

        digital_asset_repo = DigitalAssetRepository(
            session_factory=mock_session_factory
        )

        result = await digital_asset_repo.get_digital_asset_by_partner_id(
            partner_id=123, asset_type=DigitalAssetEnum.CONSOLE_PARTNER_GST
        )

        # Compare specific attributes of mock_asset and result
        assert result.id == mock_asset.id
        assert result.name == mock_asset.name
        assert result.partner_id == mock_asset.partner_id
        assert result.asset_type == mock_asset.asset_type
        assert result.version == mock_asset.version
        assert result.additional_info == mock_asset.additional_info

    async def test_get_digital_asset_by_partner_id_not_found(self):
        """Test for when no asset is found."""
        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__.return_value.execute = AsyncMock(
            return_value=mock_execute
        )

        digital_asset_repo = DigitalAssetRepository(
            session_factory=mock_session_factory
        )

        result = await digital_asset_repo.get_digital_asset_by_partner_id(
            partner_id=123, asset_type=DigitalAssetEnum.CONSOLE_PARTNER_GST
        )

        assert result is None

    async def test_get_digital_asset_by_partner_id_error(self):
        """Test for error handling in get_digital_asset_by_partner_id."""
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__.return_value.execute = AsyncMock(
            side_effect=Exception("Database error")
        )

        digital_asset_repo = DigitalAssetRepository(
            session_factory=mock_session_factory
        )

        with pytest.raises(Exception):
            await digital_asset_repo.get_digital_asset_by_partner_id(
                partner_id=123, asset_type=DigitalAssetEnum.CONSOLE_PARTNER_GST
            )

    async def test_create_digital_asset_success(self):
        """Test successfully creating a new digital asset."""
        mock_asset = DigitalAssets(
            id=1,
            name="asset1",
            partner_id=123,
            version=1,
            asset_type=DigitalAssetEnum.CONSOLE_PARTNER_GST,
            additional_info={"key": "value"},
            created_by=1,
            updated_by=1,
        )

        mock_scalars = MagicMock()
        mock_scalars.first.return_value = None

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__.return_value.execute = AsyncMock(
            return_value=mock_execute
        )

        digital_asset_repo = DigitalAssetRepository(
            session_factory=mock_session_factory
        )

        result = await digital_asset_repo.create_digital_asset(
            partner_id=123,
            asset_type=DigitalAssetEnum.CONSOLE_PARTNER_GST,
            file_name="new_asset.png",
            user_id=1,
        )

        # Compare specific attributes of mock_asset and result
        assert result.name == "new_asset.png"
        assert result.partner_id == mock_asset.partner_id
        assert result.asset_type == mock_asset.asset_type
        assert result.version == 1

    async def test_create_digital_asset_with_versioning(self):
        """Test creating a digital asset with versioning logic."""
        mock_asset = DigitalAssets(
            id=1,
            name="asset1",
            partner_id=123,
            version=2,
            asset_type=DigitalAssetEnum.CONSOLE_PARTNER_GST,
            additional_info={"key": "value"},
            created_by=1,
            updated_by=1,
        )

        mock_scalars = MagicMock()
        mock_scalars.first.return_value = mock_asset

        mock_execute = MagicMock()
        mock_execute.scalars.return_value = mock_scalars

        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__.return_value.execute = AsyncMock(
            return_value=mock_execute
        )

        digital_asset_repo = DigitalAssetRepository(
            session_factory=mock_session_factory
        )

        result = await digital_asset_repo.create_digital_asset(
            partner_id=123,
            asset_type=DigitalAssetEnum.CONSOLE_PARTNER_GST,
            file_name="new_asset.png",
            user_id=1,
        )

        # Compare specific attributes of mock_asset and result
        assert result.name == "new_asset.png"
        assert result.partner_id == mock_asset.partner_id
        assert result.asset_type == mock_asset.asset_type
        assert result.version == mock_asset.version + 1  # Should increment by 1

    async def test_create_digital_asset_error(self):
        """Test for error handling in create_digital_asset."""
        mock_session_factory = MagicMock()
        mock_session_factory.return_value.__aenter__.return_value.execute = AsyncMock(
            side_effect=Exception("Database error")
        )

        digital_asset_repo = DigitalAssetRepository(
            session_factory=mock_session_factory
        )

        with pytest.raises(Exception):
            await digital_asset_repo.create_digital_asset(
                partner_id=123,
                asset_type=DigitalAssetEnum.CONSOLE_PARTNER_GST,
                file_name="new_asset.png",
                user_id=1,
            )
