from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from src.components.digital_assets.constants import DigitalAssetEnum
from src.components.digital_assets.repositories import DigitalAssetRepository
from src.components.digital_assets.schema import UploadDigitalAssetResponse
from src.components.digital_assets.services import DigitalAssetService
from src.components.digital_assets.storage.helper import StorageHelper


@pytest.fixture
def mock_digital_asset_repository():
    return MagicMock(spec=DigitalAssetRepository)


@pytest.fixture
def digital_asset_service(mock_digital_asset_repository):
    return DigitalAssetService(mock_digital_asset_repository)


@pytest.mark.asyncio
async def test_get_digital_asset_details_invalid_asset_type(
    digital_asset_service, mock_digital_asset_repository
):
    # Arrange
    partner_id = 1
    asset_type = "invalid_type"

    # Act & Assert
    with pytest.raises(HTTPException) as excinfo:
        await digital_asset_service.get_digital_asset_details(partner_id, asset_type)
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_get_digital_asset_details_not_found(
    digital_asset_service, mock_digital_asset_repository
):
    # Arrange
    partner_id = 1
    asset_type = DigitalAssetEnum.CONSOLE_PARTNER_GST.name
    mock_digital_asset_repository.get_digital_asset_by_partner_id = AsyncMock(
        return_value=None
    )

    # Act & Assert
    with pytest.raises(HTTPException):
        await digital_asset_service.get_digital_asset_details(partner_id, asset_type)


@pytest.mark.asyncio
async def test_create_digital_asset_success(
    digital_asset_service, mock_digital_asset_repository
):
    # Arrange
    partner_id = 1
    asset_type = DigitalAssetEnum.CONSOLE_PARTNER_GST.name
    user_id = 1
    file = MagicMock()
    file.filename = "image.jpg"
    uploaded_url = "http://example.com/image.jpg"

    # Mock the created asset with actual string values
    mock_created_asset = MagicMock()
    mock_created_asset.id = 1
    mock_created_asset.name = "image.jpg"  # Use a real string here
    mock_digital_asset_repository.create_digital_asset = AsyncMock(
        return_value=mock_created_asset
    )

    # Mock upload and presigned URL generation
    StorageHelper.upload_file = AsyncMock()
    StorageHelper.get_presigned_url = MagicMock(return_value=uploaded_url)

    # Act
    result = await digital_asset_service.create_digital_asset(
        partner_id, asset_type, file, user_id
    )

    # Assert
    assert isinstance(result, UploadDigitalAssetResponse)
    assert result.url == uploaded_url
    assert result.file_name == "image.jpg"


@pytest.mark.asyncio
async def test_create_digital_asset_invalid_type(
    digital_asset_service, mock_digital_asset_repository
):
    # Arrange
    partner_id = 1
    asset_type = "invalid_type"
    user_id = 1
    file = MagicMock()

    # Act & Assert
    with pytest.raises(HTTPException) as excinfo:
        await digital_asset_service.create_digital_asset(
            partner_id, asset_type, file, user_id
        )
    assert excinfo.value.status_code == 404


@pytest.mark.asyncio
async def test_create_digital_asset_error(
    digital_asset_service, mock_digital_asset_repository
):
    # Arrange
    partner_id = 1
    asset_type = DigitalAssetEnum.CONSOLE_PARTNER_GST.name
    user_id = 1
    file = MagicMock()
    mock_digital_asset_repository.create_digital_asset = AsyncMock(
        side_effect=Exception("DB error")
    )

    # Act & Assert
    with pytest.raises(Exception):
        await digital_asset_service.create_digital_asset(
            partner_id, asset_type, file, user_id
        )


@pytest.mark.asyncio
async def test_create_digital_asset_not_created():
    """Test raising ValueError when the digital asset is not created."""
    # Arrange
    partner_id = 1
    asset_type = DigitalAssetEnum.CONSOLE_PARTNER_GST.name
    user_id = 1
    file = MagicMock()
    file.filename = "test_image.jpg"

    # Mock repository and helper behavior
    mock_repository = MagicMock(spec=DigitalAssetRepository)
    mock_repository.create_digital_asset = AsyncMock(
        return_value=None
    )  # Simulate failure
    StorageHelper.upload_file = AsyncMock()
    StorageHelper.get_presigned_url = MagicMock(
        return_value="http://example.com/test_image.jpg"
    )

    service = DigitalAssetService(mock_repository)

    with pytest.raises(HTTPException) as exc_info:
        await service.create_digital_asset(partner_id, asset_type, file, user_id)
    assert str(exc_info.value) == "404: Digital asset with ID 1 not created"


@pytest.mark.asyncio
async def test_get_digital_assets_by_digital_asset_ids_success(
    digital_asset_service, mock_digital_asset_repository
):
    # Arrange
    digital_asset_ids = ["1", "2"]
    mock_asset1 = MagicMock()
    mock_asset1.id = "1"
    mock_asset1.name = "file1.jpg"
    mock_asset1.partner_id = 1
    mock_asset1.version = 1
    mock_asset1.asset_type = (
        DigitalAssetEnum.CONSOLE_PARTNER_GST.value
    )  # Use a valid enum value
    mock_asset1.additional_info = {}
    mock_asset1.created_by = 1
    mock_asset1.updated_by = 1

    mock_asset2 = MagicMock()
    mock_asset2.id = "2"
    mock_asset2.name = "file2.jpg"
    mock_asset2.partner_id = 2
    mock_asset2.version = 1
    mock_asset2.asset_type = 1
    mock_asset2.additional_info = {}
    mock_asset2.created_by = 2
    mock_asset2.updated_by = 2

    mock_digital_asset_repository.get_digital_assets_by_digital_asset_ids = AsyncMock(
        return_value=[mock_asset1, mock_asset2]
    )
    StorageHelper.get_presigned_url = MagicMock(
        side_effect=["http://example.com/file1.jpg", "http://example.com/file2.jpg"]
    )

    # Act
    result = await digital_asset_service.get_digital_assets_by_digital_asset_ids(
        digital_asset_ids
    )

    # Assert
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0].id == 1


@pytest.mark.asyncio
async def test_get_digital_assets_by_digital_asset_ids_asset_not_found(
    digital_asset_service, mock_digital_asset_repository
):
    # Arrange
    digital_asset_ids = ["1", "2"]
    mock_digital_asset_repository.get_digital_assets_by_digital_asset_ids = AsyncMock(
        return_value=[]
    )

    # Act
    result = await digital_asset_service.get_digital_assets_by_digital_asset_ids(
        digital_asset_ids
    )

    # Assert
    assert result == []


@pytest.mark.asyncio
async def test_get_digital_assets_by_digital_asset_ids_unexpected_error(
    digital_asset_service, mock_digital_asset_repository
):
    # Arrange
    digital_asset_ids = ["1", "2"]
    mock_digital_asset_repository.get_digital_assets_by_digital_asset_ids = AsyncMock(
        side_effect=Exception("Unexpected error")
    )

    # Act & Assert
    with pytest.raises(Exception) as excinfo:
        await digital_asset_service.get_digital_assets_by_digital_asset_ids(
            digital_asset_ids
        )
    assert "Unexpected error" in str(excinfo.value)
