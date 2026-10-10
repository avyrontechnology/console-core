from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from src.components.audit_log.services import AuditService
from src.components.db_constants.enums import ConstantsTypes
from src.components.db_constants.models import (
    Constants,
    GlobalDynamicVariables,
    MediaConstants,
)
from src.components.db_constants.repositories import ConstantsRepository
from src.components.db_constants.schema import ConstantResponseSchema
from src.components.db_constants.services import ConstantsService
from src.components.digital_assets.services import DigitalAssetService
from src.components.digital_assets.storage.helper import StorageHelper
from src.exceptions import (
    ConstantNotFoundException,
    ConstantVersionException,
    ConstantVersionNotFoundException,
)
from src.loggers.console_service_logger import ConsoleServiceLogger


@pytest.fixture
def mock_constants_repository():
    return MagicMock(ConstantsRepository)


@pytest.fixture
def mock_console_service_logger():
    return MagicMock(ConsoleServiceLogger)


@pytest.fixture
def mock_audit_log_service():
    return MagicMock(AuditService)


@pytest.fixture
def mock_digital_asset_service():
    return MagicMock(DigitalAssetService)


@pytest.fixture
def constants_service(
    mock_constants_repository,
    mock_console_service_logger,
    mock_audit_log_service,
    mock_digital_asset_service,
):
    return ConstantsService(
        constants_repository=mock_constants_repository,
        console_service_logger=mock_console_service_logger,
        audit_log_service=mock_audit_log_service,
        digital_asset_service=mock_digital_asset_service,
    )


@pytest.mark.asyncio
async def test_get_constants_details(constants_service, mock_constants_repository):
    model = MagicMock()
    mock_constants_repository.fetch_constant_by_type = AsyncMock(return_value=[])

    constants = await constants_service.get_constants_details(model)
    assert constants == []
    mock_constants_repository.fetch_constant_by_type.assert_called_once_with(model)


def test_constant_response_schema():
    response_data = {
        "id": 1,
        "name": "Test Constant",
        "value": "Test Value",
        "description": "Test Description",
        "version": 1,
        "updated_by": 101,
        "updated_at": datetime.now(),
        "additional_info": {"key": "value"},
    }
    constant = ConstantResponseSchema(**response_data)
    assert constant.name == "Test Constant"
    assert constant.version == 1
    assert constant.additional_info == {"key": "value"}


@pytest.mark.asyncio
async def test_get_highest_version(constants_service):
    additional_info = {"version-1": "old_value", "version-2": "new_value"}
    current_version = 2
    highest_version = constants_service.get_highest_version(
        additional_info, current_version
    )
    assert highest_version == 2


@pytest.mark.asyncio
async def test_get_constant_by_id(constants_service, mock_constants_repository):
    model = MagicMock()
    constant_id = 1
    mock_constants_repository.get_constant_by_id = AsyncMock(
        return_value="constant_data"
    )

    constant = await constants_service.get_constant_by_id(constant_id, model)
    assert constant == "constant_data"
    mock_constants_repository.get_constant_by_id.assert_called_once_with(
        model, constant_id
    )


@pytest.mark.asyncio
async def test_get_constant_by_id_not_found(
    constants_service, mock_constants_repository
):
    model = MagicMock()
    constant_id = 1
    mock_constants_repository.get_constant_by_id = AsyncMock(return_value=None)

    constant = await constants_service.get_constant_by_id(constant_id, model)
    assert constant is None
    mock_constants_repository.get_constant_by_id.assert_called_once_with(
        model, constant_id
    )


@pytest.mark.asyncio
async def test_update_constant_with_media(
    constants_service,
    mock_constants_repository,
    mock_digital_asset_service,
    mock_audit_log_service,
):
    constant_id = 1
    model = MagicMock()
    value = "test_file"
    is_media_type = True
    asset_type = "OTHER"
    user_id = 1
    description = None

    mock_constants_repository.get_constant_by_id = AsyncMock(
        return_value=MagicMock(value=None, additional_info=None)
    )
    mock_digital_asset_service.create_digital_asset = AsyncMock(
        return_value=MagicMock(id="digital_asset_id")
    )
    mock_constants_repository.update_constant = AsyncMock(
        return_value="updated_constant"
    )

    updated_constant = await constants_service.update_constant(
        constant_id, model, value, is_media_type, asset_type, user_id, description
    )

    assert updated_constant == "updated_constant"
    mock_digital_asset_service.create_digital_asset.assert_called_once_with(
        partner_id=0,
        asset_type=asset_type,
        input_file=value,
        user_id=user_id,
    )
    mock_audit_log_service.log_action.assert_called_once()


@pytest.mark.asyncio
async def test_update_constant_without_media(
    constants_service, mock_constants_repository, mock_audit_log_service
):
    constant_id = 1
    model = MagicMock()
    value = "new_value"
    is_media_type = False
    asset_type = "OTHER"
    user_id = 1
    description = "Updated description"

    mock_constants_repository.get_constant_by_id = AsyncMock(
        return_value=MagicMock(value="old_value", version=1, additional_info={})
    )
    mock_constants_repository.update_constant = AsyncMock(
        return_value="updated_constant"
    )

    updated_constant = await constants_service.update_constant(
        constant_id, model, value, is_media_type, asset_type, user_id, description
    )

    assert updated_constant == "updated_constant"
    mock_audit_log_service.log_action.assert_called_once()


@pytest.mark.asyncio
async def test_update_constant_exception(
    constants_service, mock_constants_repository, mock_console_service_logger
):
    constant_id = 1
    model = MagicMock()
    value = "new_value"
    is_media_type = False
    asset_type = "OTHER"
    user_id = 1
    description = "Updated description"

    mock_constants_repository.get_constant_by_id = AsyncMock(
        side_effect=Exception("Update error")
    )

    with pytest.raises(Exception, match="Update error"):
        await constants_service.update_constant(
            constant_id, model, value, is_media_type, asset_type, user_id, description
        )

    mock_console_service_logger.error.assert_called_once_with(
        "Unexpected error occured while updating Constants: Update error"
    )


def test_get_highest_version_with_no_additional_info(constants_service):
    additional_info = {}
    current_version = 1

    highest_version = constants_service.get_highest_version(
        additional_info, current_version
    )
    assert highest_version == 1


@pytest.mark.asyncio
async def test_get_highest_version_with_non_versioned_data(constants_service):
    additional_info = {"key1": "value1", "key2": "value2"}
    current_version = 1
    highest_version = constants_service.get_highest_version(
        additional_info, current_version
    )
    assert highest_version == 1  # No versioned info, should return the current version


@pytest.mark.asyncio
async def test_get_constant_by_id_with_invalid_model(
    constants_service, mock_constants_repository
):
    invalid_model = "InvalidModel"
    constant_id = 1
    mock_constants_repository.get_constant_by_id = AsyncMock(return_value=None)

    constant = await constants_service.get_constant_by_id(constant_id, invalid_model)
    assert constant is None  # Should return None since the model is invalid
    mock_constants_repository.get_constant_by_id.assert_called_once_with(
        invalid_model, constant_id
    )


@pytest.mark.asyncio
async def test_get_constant_by_id_empty_response(
    constants_service, mock_constants_repository
):
    model = MagicMock()
    constant_id = 1
    mock_constants_repository.get_constant_by_id = AsyncMock(return_value=None)

    constant = await constants_service.get_constant_by_id(constant_id, model)
    assert constant is None  # Should return None when the constant is not found
    mock_constants_repository.get_constant_by_id.assert_called_once_with(
        model, constant_id
    )


@pytest.mark.asyncio
async def test_rollback_constant_not_found(
    constants_service, mock_constants_repository, mock_console_service_logger
):
    constant_id = 1
    target_version = 1
    constant_type = ConstantsTypes.CONSTANTS
    user_id = 1

    mock_constants_repository.get_constant_by_id = AsyncMock(return_value=None)

    with pytest.raises(ConstantNotFoundException):
        await constants_service.rollback_constant(
            constant_id, target_version, constant_type, user_id
        )

    mock_console_service_logger.error.assert_has_calls(
        [
            call("Constant with ID 1 not found."),
            call(
                "An error occured while rollback constant: Constant with ID 1 not found."
            ),
        ]
    )


@pytest.mark.asyncio
async def test_rollback_constant_no_previous_versions(
    constants_service, mock_constants_repository, mock_console_service_logger
):
    # Setup mock data for rollback
    constant_id = 1
    target_version = 1
    constant_type = ConstantsTypes.CONSTANTS  # Replace with an actual constant type
    user_id = 1

    constant = MagicMock(id=constant_id, version=2, additional_info=None)
    mock_constants_repository.get_constant_by_id = AsyncMock(return_value=constant)

    # Test rollback when no previous versions exist
    with pytest.raises(ConstantVersionNotFoundException):
        await constants_service.rollback_constant(
            constant_id, target_version, constant_type, user_id
        )

    mock_console_service_logger.error.assert_has_calls(
        [
            call("Constant with ID 1 has no previous versions."),
            call(
                "An error occured while rollback constant: Constant with ID 1 has no previous versions."
            ),
        ]
    )


@pytest.mark.asyncio
async def test_rollback_constant_already_at_target_version(
    constants_service, mock_constants_repository, mock_console_service_logger
):
    # Setup mock data for rollback
    constant_id = 1
    target_version = 1
    constant_type = ConstantsTypes.CONSTANTS
    user_id = 1

    constant = MagicMock(
        id=constant_id, version=1, additional_info={"version-1": "old_value"}
    )
    mock_constants_repository.get_constant_by_id = AsyncMock(return_value=constant)

    # Test rollback when already at the target version
    with pytest.raises(ConstantVersionException):
        await constants_service.rollback_constant(
            constant_id, target_version, constant_type, user_id
        )

    mock_console_service_logger.error.assert_has_calls(
        [
            call("Constant with ID 1 is already on version 1."),
            call(
                "An error occured while rollback constant: Constant with ID 1 is already on version 1."
            ),
        ]
    )


@pytest.mark.asyncio
async def test_rollback_constant_version_not_found_in_additional_info(
    constants_service, mock_constants_repository, mock_console_service_logger
):
    # Setup mock data for rollback
    constant_id = 1
    target_version = 1
    constant_type = ConstantsTypes.CONSTANTS  # Replace with an actual constant type
    user_id = 1

    constant = MagicMock(
        id=constant_id, version=2, additional_info={"version-2": "current_value"}
    )
    mock_constants_repository.get_constant_by_id = AsyncMock(return_value=constant)

    # Test rollback when target version is not found in additional_info
    with pytest.raises(ConstantVersionNotFoundException):
        await constants_service.rollback_constant(
            constant_id, target_version, constant_type, user_id
        )

    mock_console_service_logger.error.assert_has_calls(
        [
            call("Version 1 not found in additional_info for Constant ID 1."),
            call(
                "An error occured while rollback constant: Version 1 not found in additional_info."
            ),
        ]
    )


@pytest.mark.asyncio
async def test_unexpected_error_in_fetch_constants_details(
    constants_service, mock_console_service_logger, mock_constants_repository
):
    model = MagicMock()
    mock_constants_repository.fetch_constant_by_type = AsyncMock(
        side_effect=Exception("Unexpected error")
    )

    with pytest.raises(Exception, match="Unexpected error"):
        await constants_service.get_constants_details(model)

    mock_console_service_logger.error.assert_called_once_with(
        "Unexpected error occured while fetching constants details in constants service: Unexpected error"
    )


@pytest.mark.asyncio
async def test_error_in_get_highest_version(
    constants_service, mock_console_service_logger
):
    additional_info = {"version-1": "old_value", "version-2": "new_value"}
    current_version = 2

    constants_service.get_highest_version = AsyncMock(
        side_effect=Exception("Error getting highest version")
    )

    with pytest.raises(Exception, match="Error getting highest version"):
        await constants_service.get_highest_version(additional_info, current_version)


@pytest.mark.asyncio
async def test_error_in_rollback_constant(
    constants_service, mock_console_service_logger, mock_constants_repository
):
    constant_id = 1
    target_version = 1
    constant_type = ConstantsTypes.CONSTANTS
    user_id = 1

    mock_constants_repository.rollback_version = AsyncMock(
        side_effect=Exception("Version 1 not found in additional_info.")
    )

    constants_service.rollback_constant = AsyncMock(
        side_effect=ConstantVersionNotFoundException(
            "Version 1 not found in additional_info."
        )
    )

    with pytest.raises(
        ConstantVersionNotFoundException,
        match="Version 1 not found in additional_info.",
    ):
        await constants_service.rollback_constant(
            constant_id, target_version, constant_type, user_id
        )


@pytest.mark.asyncio
async def test_constant_media_processing(constants_service):
    constant = MagicMock()
    constant.media = "test_media_url"

    with patch.object(
        StorageHelper, "get_presigned_url", return_value="presigned_url"
    ) as mock_get_presigned_url:
        constant.media = StorageHelper.get_presigned_url(constant.media)

        mock_get_presigned_url.assert_called_once_with("test_media_url")

        assert constant.media == "presigned_url"


@pytest.mark.asyncio
async def test_get_highest_version_logs_and_raises_exception(
    constants_service, mock_console_service_logger
):
    additional_info = "invalid_data"

    with pytest.raises(Exception):
        constants_service.get_highest_version(additional_info, 2)

    mock_console_service_logger.error.assert_called_once()

    assert (
        "An error occured while getting highest version of constant:"
        in mock_console_service_logger.error.call_args[0][0]
    )


@pytest.mark.asyncio
async def test_rollback_version(
    constants_service, mock_constants_repository, mock_audit_log_service
):
    mock_constant = MagicMock()
    mock_constant.version = 3
    mock_constant.value = "current_value"
    mock_constant.additional_info = {
        "version-1": "old_value_1",
        "version-2": "old_value_2",
        "version-3": "current_value",
    }

    mock_updated_constant = MagicMock()
    mock_constants_repository.rollback_version = AsyncMock(
        return_value=mock_updated_constant
    )

    constants_service.get_constant_by_id = AsyncMock(return_value=mock_constant)

    constant_id = 1
    target_version = 2
    user_id = 42
    version_key = f"version-{target_version}"

    result = await constants_service.rollback_constant(
        id=constant_id,
        target_version=target_version,
        constant_type=ConstantsTypes.CONSTANTS,
        user_id=user_id,
    )

    assert mock_constant.additional_info[version_key] == "old_value_2"

    assert f"version-{mock_constant.version}" in mock_constant.additional_info

    mock_constants_repository.rollback_version.assert_called_once_with(
        id=constant_id,
        constant_model=Constants,
        value="old_value_2",
        version=target_version,
        user_id=user_id,
        additional_info=mock_constant.additional_info,
    )

    mock_audit_log_service.log_action.assert_called_once()
    audit_log_entry = mock_audit_log_service.log_action.call_args[0][0]
    assert "rolled back constant to a previous version" in audit_log_entry.details

    assert result == mock_updated_constant


@pytest.mark.asyncio
async def test_add_current_version_key_if_missing(
    constants_service, mock_constants_repository
):
    mock_constant = MagicMock()
    mock_constant.version = 3
    mock_constant.value = "current_value"
    mock_constant.additional_info = {
        "version-1": "old_value_1",
        "version-2": "old_value_2",
    }

    mock_constants_repository.rollback_version = AsyncMock(return_value=mock_constant)

    constants_service.get_constant_by_id = AsyncMock(return_value=mock_constant)

    constant_id = 1
    target_version = 2
    user_id = 42

    await constants_service.rollback_constant(
        id=constant_id,
        target_version=target_version,
        constant_type=ConstantsTypes.CONSTANTS,
        user_id=user_id,
    )

    current_version_key = f"version-{mock_constant.version}"
    assert current_version_key in mock_constant.additional_info
    assert mock_constant.additional_info[current_version_key] == "current_value"


@pytest.mark.asyncio
async def test_get_constants_details_with_media_constants(
    constants_service, mock_constants_repository
):
    # Mock constants with MediaConstants type
    mock_constant1 = MagicMock()
    mock_constant1.additional_info = {
        "thumbnail": "s3://bucket/image1.jpg",
        "metadata": {"size": "2MB"},  # Non-string should remain unchanged
    }
    mock_constant1.value = "s3://bucket/video1.mp4"

    mock_constant2 = MagicMock()
    mock_constant2.additional_info = {
        "preview": "s3://bucket/image2.jpg",
        "info": "s3://bucket/info.json",
    }
    mock_constant2.value = "s3://bucket/video2.mp4"

    mock_constants = [mock_constant1, mock_constant2]

    # Mock repository return value
    mock_constants_repository.fetch_constant_by_type = AsyncMock(
        return_value=mock_constants
    )
    constants_service.constants_repository = mock_constants_repository

    # Mock StorageHelper.get_presigned_url to return a dummy URL
    with patch(
        "src.components.digital_assets.storage.helper.StorageHelper.get_presigned_url",
        side_effect=lambda url: f"https://cdn.example.com/{url.split('/')[-1]}",
    ) as mock_presign:
        # Call the method under test
        result = await constants_service.get_constants_details(MediaConstants)

        # Ensure URLs in additional_info are updated correctly
        assert (
            result[0].additional_info["thumbnail"]
            == "https://cdn.example.com/image1.jpg"
        )
        assert result[0].additional_info["metadata"] == {
            "size": "2MB"
        }  # Non-string remains unchanged
        assert result[0].value == "https://cdn.example.com/video1.mp4"

        assert (
            result[1].additional_info["preview"] == "https://cdn.example.com/image2.jpg"
        )
        assert result[1].additional_info["info"] == "https://cdn.example.com/info.json"
        assert result[1].value == "https://cdn.example.com/video2.mp4"

        # Ensure get_presigned_url was called for each string value
        assert mock_presign.call_count == 5  # 3 additional_info + 2 value fields


@pytest.mark.asyncio
async def test_get_navbar_marquee_config_enabled_with_message(constants_service):
    # MagicMock's own `name` kwarg is reserved for the mock's repr, not an
    # attribute, so it must be set explicitly on each fake row afterwards.
    enabled_row = MagicMock(value="true")
    enabled_row.name = "NAVBAR_MARQUEE_ENABLED"
    message_row = MagicMock(value="Server maintenance at 10pm")
    message_row.name = "NAVBAR_MARQUEE_MESSAGE"

    constants_service.get_constants_details = AsyncMock(
        return_value=[enabled_row, message_row]
    )

    result = await constants_service.get_navbar_marquee_config()

    assert result.is_enabled is True
    assert result.message == "Server maintenance at 10pm"
    constants_service.get_constants_details.assert_called_once_with(
        GlobalDynamicVariables
    )


@pytest.mark.asyncio
async def test_get_navbar_marquee_config_disabled_hides_message(constants_service):
    enabled_row = MagicMock(value="false")
    enabled_row.name = "NAVBAR_MARQUEE_ENABLED"
    message_row = MagicMock(value="Should never be shown")
    message_row.name = "NAVBAR_MARQUEE_MESSAGE"

    constants_service.get_constants_details = AsyncMock(
        return_value=[enabled_row, message_row]
    )

    result = await constants_service.get_navbar_marquee_config()

    assert result.is_enabled is False
    assert result.message is None


@pytest.mark.asyncio
async def test_get_navbar_marquee_config_unconfigured_defaults_to_disabled(
    constants_service,
):
    constants_service.get_constants_details = AsyncMock(return_value=[])

    result = await constants_service.get_navbar_marquee_config()

    assert result.is_enabled is False
    assert result.message is None


@pytest.mark.asyncio
async def test_get_navbar_marquee_config_enabled_but_empty_message(constants_service):
    enabled_row = MagicMock(value="true")
    enabled_row.name = "NAVBAR_MARQUEE_ENABLED"
    message_row = MagicMock(value="")
    message_row.name = "NAVBAR_MARQUEE_MESSAGE"

    constants_service.get_constants_details = AsyncMock(
        return_value=[enabled_row, message_row]
    )

    result = await constants_service.get_navbar_marquee_config()

    assert result.is_enabled is True
    assert result.message is None


@pytest.mark.asyncio
async def test_get_navbar_marquee_config_is_case_and_whitespace_tolerant(
    constants_service,
):
    enabled_row = MagicMock(value="  TRUE  ")
    enabled_row.name = "NAVBAR_MARQUEE_ENABLED"

    constants_service.get_constants_details = AsyncMock(return_value=[enabled_row])

    result = await constants_service.get_navbar_marquee_config()

    assert result.is_enabled is True


@pytest.mark.asyncio
async def test_get_navbar_marquee_config_logs_and_raises_on_error(
    constants_service, mock_console_service_logger
):
    constants_service.get_constants_details = AsyncMock(
        side_effect=Exception("DB is down")
    )

    with pytest.raises(Exception, match="DB is down"):
        await constants_service.get_navbar_marquee_config()

    mock_console_service_logger.error.assert_called_once_with(
        "Unexpected error occured while fetching navbar marquee config: DB is down"
    )
