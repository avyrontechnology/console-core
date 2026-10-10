from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from src.components.db_constants.initializer import (
    ConstantsCreator,
    ConstantsInitializer,
    LazyConstantLoader,
)
from src.components.db_constants.models import (
    Constants,
    GlobalConstants,
    GlobalMediaConstants,
    MediaConstants,
)


# Mock StorageHelper for LazyConstantLoader tests
@pytest_asyncio.fixture
def mock_storage_helper():
    with patch("src.components.db_constants.initializer.StorageHelper") as mock:
        yield mock


@pytest_asyncio.fixture
async def mock_session():
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    return session


@pytest_asyncio.fixture
async def mock_session_factory(mock_session):
    async def factory():
        return mock_session

    return factory


# Test cases for _print_report
def test_print_report_both_created_and_existing(capsys):
    # Setup
    created_constants = [
        "Created KEY1 in Constants.",
        "Created KEY2 in MediaConstants.",
    ]
    existing_constants = [
        "Already exists KEY3 in Constants.",
        "Already exists KEY4 in GlobalConstants.",
    ]

    # Execute
    ConstantsCreator._print_report(created_constants, existing_constants)

    # Assert
    captured = capsys.readouterr()
    assert "Constants Creation Report" in captured.out
    assert "Created Constants:" in captured.out
    assert "- Created KEY1 in Constants." in captured.out
    assert "- Created KEY2 in MediaConstants." in captured.out
    assert "Already Existing Constants:" in captured.out
    assert "- Already exists KEY3 in Constants." in captured.out
    assert "- Already exists KEY4 in GlobalConstants." in captured.out
    assert "-------------------" in captured.out


def test_print_report_only_created(capsys):
    # Setup
    created_constants = ["Created KEY1 in Constants."]
    existing_constants = []

    # Execute
    ConstantsCreator._print_report(created_constants, existing_constants)

    # Assert
    captured = capsys.readouterr()
    assert "Constants Creation Report" in captured.out
    assert "Created Constants:" in captured.out
    assert "- Created KEY1 in Constants." in captured.out
    assert "No constants were created." not in captured.out
    assert "All constants were already present." in captured.out
    assert "Already Existing Constants:" not in captured.out  # Corrected assertion


def test_print_report_only_existing(capsys):
    # Setup
    created_constants = []
    existing_constants = ["Already exists KEY1 in Constants."]

    # Execute
    ConstantsCreator._print_report(created_constants, existing_constants)

    # Assert
    captured = capsys.readouterr()
    assert "Constants Creation Report" in captured.out
    assert "No constants were created." in captured.out
    assert "Already Existing Constants:" in captured.out
    assert "- Already exists KEY1 in Constants." in captured.out


def test_print_report_empty(capsys):
    # Setup
    created_constants = []
    existing_constants = []

    # Execute
    ConstantsCreator._print_report(created_constants, existing_constants)

    # Assert
    captured = capsys.readouterr()
    assert "Constants Creation Report" in captured.out
    assert "No constants were created." in captured.out
    assert "All constants were already present." in captured.out


@pytest.mark.asyncio
async def test_initialize_constants(mock_session_factory):
    # Setup
    with patch.object(
        ConstantsInitializer, "_load_constants", new=AsyncMock()
    ) as mock_load:
        # Execute
        await ConstantsInitializer.initialize_constants(mock_session_factory)

        # Assert
        assert mock_load.call_count == 4
        assert mock_load.call_args_list[0][0][1] == Constants
        assert mock_load.call_args_list[1][0][1] == MediaConstants
        assert mock_load.call_args_list[2][0][1] == GlobalConstants
        assert mock_load.call_args_list[3][0][1] == GlobalMediaConstants


@pytest.mark.asyncio
async def test_constant_exists_true(mock_session):
    # Setup
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = MagicMock()
    mock_session.execute.return_value = mock_result

    # Execute
    result = await ConstantsCreator._constant_exists(
        mock_session, "TEST_KEY", Constants
    )

    # Assert
    assert result is True
    assert mock_session.execute.called


@pytest.mark.asyncio
async def test_constant_exists_false(mock_session):
    # Setup
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_session.execute.return_value = mock_result

    # Execute
    result = await ConstantsCreator._constant_exists(
        mock_session, "TEST_KEY", Constants
    )

    # Assert
    assert result is False
    assert mock_session.execute.called


@pytest.mark.asyncio
async def test_create_new_constant_non_media(mock_session):
    # Setup
    created_constants = []

    # Execute
    await ConstantsCreator._create_new_constant(
        mock_session, "TEST_KEY", Constants, created_constants
    )

    # Assert
    assert len(created_constants) == 1
    assert created_constants[0] == "Created TEST_KEY in Constants."
    assert mock_session.add.called
    assert mock_session.commit.called
    assert mock_session.add.call_args[0][0].value == ""


@pytest.mark.asyncio
async def test_create_new_constant_media(mock_session):
    # Setup
    created_constants = []

    # Execute
    await ConstantsCreator._create_new_constant(
        mock_session, "TEST_KEY", MediaConstants, created_constants
    )

    # Assert
    assert len(created_constants) == 1
    assert created_constants[0] == "Created TEST_KEY in MediaConstants."
    assert mock_session.add.called
    assert mock_session.commit.called
    assert mock_session.add.call_args[0][0].value is None


@pytest.mark.asyncio
async def test_lazy_constant_loader_dict_only():
    # Setup
    test_dict = {"TEST_KEY": "test_value"}
    loader = LazyConstantLoader("TEST_KEY", dict=test_dict, default="default")

    # Execute
    result = loader.__repr__()

    # Assert
    assert result == "test_value"


@pytest.mark.asyncio
async def test_lazy_constant_loader_dict_default():
    # Setup
    test_dict = {}
    loader = LazyConstantLoader("TEST_KEY", dict=test_dict, default="default")

    # Execute
    result = loader.__repr__()

    # Assert
    assert result == "default"


@pytest.mark.asyncio
async def test_lazy_constant_loader_model(mock_storage_helper):
    # Setup
    mock_storage_helper.get_presigned_url.return_value = "presigned_url"
    loader = LazyConstantLoader("TEST_KEY", model=Constants, default="default")

    # Execute
    result = loader.__repr__()

    # Assert
    assert result == "presigned_url"
    assert mock_storage_helper.get_presigned_url.called_with("TEST_KEY")


@pytest.mark.asyncio
async def test_lazy_constant_loader_model_none(mock_storage_helper):
    # Setup
    mock_storage_helper.get_presigned_url.return_value = None
    loader = LazyConstantLoader("TEST_KEY", model=Constants, default="default")

    # Execute
    result = loader.__repr__()

    # Assert
    assert result == "default"


@pytest.mark.asyncio
async def test_process_constants(mock_session_factory, mock_session):
    # Setup
    created_constants = []
    existing_constants = []
    key_names = ["KEY1", "KEY2"]

    with patch.object(
        ConstantsCreator, "_constant_exists", new=AsyncMock()
    ) as mock_exists:
        with patch.object(
            ConstantsCreator, "_create_new_constant", new=AsyncMock()
        ) as mock_create:
            mock_exists.side_effect = [True, False]
            mock_create.side_effect = lambda session, key, model, lst: lst.append(
                f"Created {key} in {model.__name__}."
            )

            # Execute
            await ConstantsCreator._process_constants(
                mock_session,
                key_names,
                Constants,
                created_constants,
                existing_constants,
            )

            # Assert
            assert len(existing_constants) == 1
            assert len(created_constants) == 1
            assert existing_constants[0] == 'Already exists "KEY1" in "Constants".'
            assert created_constants[0] == "Created KEY2 in Constants."
            assert mock_create.call_args_list[0][0][1] == "KEY2"
            assert mock_create.call_args_list[0][0][2] == Constants
            assert mock_create.call_args_list[0][0][3] == created_constants
