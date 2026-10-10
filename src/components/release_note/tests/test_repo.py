import pytest
from unittest.mock import AsyncMock, MagicMock

from src.components.release_note.repositories import ReleaseNotesRepository
from src.components.release_note.models import ReleaseNotes


# ===============================
# SESSION FIXTURES
# ===============================

@pytest.fixture
def mock_session():
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_session_factory(mock_session):
    factory = MagicMock()

    context_manager = AsyncMock()
    context_manager.__aenter__.return_value = mock_session
    context_manager.__aexit__.return_value = None

    factory.return_value = context_manager
    return factory


@pytest.fixture
def repository(mock_session_factory):
    return ReleaseNotesRepository(mock_session_factory)


# ===============================
# CREATE RELEASE NOTE
# ===============================

@pytest.mark.asyncio
async def test_create_release_note_success(repository, mock_session):

    result = await repository.create_release_note(
        title="Test Release",
        description="Test Desc",
        markup="Test Markup",   
        da_file_path="file.pdf",
        partner_id=10,
        user_id=1,
        svc_name="TEST_SERVICE",
    )

    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()
    mock_session.refresh.assert_called_once()

    assert result is not None
    assert isinstance(result, ReleaseNotes)
    assert result.markup == "Test Markup"


@pytest.mark.asyncio
async def test_create_release_note_exception(repository, mock_session):

    mock_session.commit.side_effect = Exception("DB Error")

    with pytest.raises(Exception):
        await repository.create_release_note(
            title="Test",
            description="Desc",
            da_file_path="file.pdf",
            partner_id=1,
            user_id=1,
            svc_name="TEST_SERVICE",
        )


# ===============================
# GET RELEASE NOTE BY ID
# ===============================

@pytest.mark.asyncio
async def test_get_release_note_by_id_success(repository, mock_session):

    release_note = MagicMock(spec=ReleaseNotes)

    scalars_mock = MagicMock()
    scalars_mock.first.return_value = release_note

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    mock_session.execute.return_value = result_mock

    result = await repository.get_release_note_by_id(1, "TEST_SERVICE")

    assert result == release_note
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_get_release_note_by_id_not_found(repository, mock_session):

    scalars_mock = MagicMock()
    scalars_mock.first.return_value = None

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    mock_session.execute.return_value = result_mock

    result = await repository.get_release_note_by_id(1, "TEST_SERVICE")

    assert result is None


@pytest.mark.asyncio
async def test_get_release_note_by_id_exception(repository, mock_session):

    mock_session.execute.side_effect = Exception("DB Error")

    with pytest.raises(Exception):
        await repository.get_release_note_by_id(1, "TEST_SERVICE")


# ===============================
# GET ALL RELEASE NOTES
# ===============================

@pytest.mark.asyncio
async def test_get_all_release_notes_success(repository, mock_session):

    release_notes = [
        MagicMock(spec=ReleaseNotes),
        MagicMock(spec=ReleaseNotes),
    ]

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = release_notes

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    mock_session.execute.return_value = result_mock

    result = await repository.get_all_release_notes(partner_id=10)

    assert result == release_notes


@pytest.mark.asyncio
async def test_get_all_release_notes_empty(repository, mock_session):

    scalars_mock = MagicMock()
    scalars_mock.all.return_value = []

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    mock_session.execute.return_value = result_mock

    result = await repository.get_all_release_notes(partner_id=10)

    assert result == []


# ===============================
# UPDATE RELEASE NOTE
# ===============================

@pytest.mark.asyncio
async def test_update_release_note_success(repository, mock_session):

    release_note = MagicMock(spec=ReleaseNotes)
    release_note.id = 1
    release_note.title = "Old Title"
    release_note.description = "Old Desc"
    release_note.markup = "Old Markup"
    release_note.da_file_path = "old.pdf"
    release_note.version_history = ["v1"]
    release_note.updated_by = None

    scalars_mock = MagicMock()
    scalars_mock.first.return_value = release_note

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    mock_session.execute.return_value = result_mock

    updated_history = ["v1", "v2"]

    result = await repository.update_release_note(
        release_note_id=1,
        title="Updated Title",
        description="Updated Desc",
        markup="Updated Markup",  
        da_file_path="new.pdf",
        user_id=2,
        version_history=updated_history,
    )

    assert result.title == "Updated Title"
    assert result.description == "Updated Desc"
    assert result.markup == "Updated Markup"
    assert result.da_file_path == "new.pdf"
    assert result.version_history == updated_history
    assert result.updated_by == 2

    mock_session.commit.assert_called_once()
    mock_session.refresh.assert_called_once()


@pytest.mark.asyncio
async def test_update_release_note_not_found(repository, mock_session):

    scalars_mock = MagicMock()
    scalars_mock.first.return_value = None

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    mock_session.execute.return_value = result_mock

    result = await repository.update_release_note(
        release_note_id=1,
        title="Title",
        description="Desc",
        markup="Markup",   
        da_file_path="file.pdf",
        user_id=1,
        version_history=[],
    )

    assert result is None


@pytest.mark.asyncio
async def test_update_release_note_exception(repository, mock_session):

    mock_session.execute.side_effect = Exception("DB Error")

    with pytest.raises(Exception):
        await repository.update_release_note(
            release_note_id=1,
            title="T",
            description="D",
            markup="Markup",   
            da_file_path="f.pdf",
            user_id=1,
            version_history=[],
        )


# ===============================
# GET RELEASE NOTE HISTORY
# ===============================

@pytest.mark.asyncio
async def test_get_release_note_history_success(repository, mock_session):

    release_note = MagicMock(spec=ReleaseNotes)
    release_note.version_history = [{"v": 1}, {"v": 2}]

    scalars_mock = MagicMock()
    scalars_mock.first.return_value = release_note

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    mock_session.execute.return_value = result_mock

    result = await repository.get_release_note_history(1)

    assert result == [{"v": 1}, {"v": 2}]


@pytest.mark.asyncio
async def test_get_release_note_history_empty(repository, mock_session):

    release_note = MagicMock(spec=ReleaseNotes)
    release_note.version_history = None

    scalars_mock = MagicMock()
    scalars_mock.first.return_value = release_note

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    mock_session.execute.return_value = result_mock

    result = await repository.get_release_note_history(1)

    assert result == []


@pytest.mark.asyncio
async def test_get_release_note_history_not_found(repository, mock_session):

    scalars_mock = MagicMock()
    scalars_mock.first.return_value = None

    result_mock = MagicMock()
    result_mock.scalars.return_value = scalars_mock

    mock_session.execute.return_value = result_mock

    result = await repository.get_release_note_history(1)

    assert result is None