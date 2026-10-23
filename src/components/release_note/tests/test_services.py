from uuid import UUID
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.components.release_note.services import ReleaseNotesService
from src.components.release_note.models import ReleaseNotes
from src.components.release_note.errors import (
    ReleaseNoteNotFoundError,
    UnauthorizedReleaseNoteAccessError,
    ReleaseNoteFileUploadError,
)
from src.components.common.constants import CurrentUserMap


# ========================================
# FIXTURES
# ========================================

@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def service(mock_repo):
    return ReleaseNotesService(mock_repo)


# ========================================
# CREATE RELEASE NOTE
# ========================================

@pytest.mark.asyncio
async def test_create_release_note_success(service, mock_repo):

    release_note = MagicMock(spec=ReleaseNotes)
    release_note.id = UUID("11111111-1111-1111-1111-111111111111")
    release_note.title = "Title"
    release_note.description = "Desc"
    release_note.da_file_path = None
    release_note.created_at = 123
    release_note.updated_at = None
    release_note.version_history = [{"version": "v1"}]
    release_note.svc_name = "console"
    release_note.markup = "markup"

    mock_repo.create_release_note.return_value = release_note

    result = await service.create_release_note(
        "Title",
        "Desc",
        "markup",
        None,
        1,
        10,
        "console",
    )

    assert result.id == UUID("11111111-1111-1111-1111-111111111111")
    assert result.file_url is None
    assert result.markup == "markup"


@pytest.mark.asyncio
async def test_create_release_note_upload_failure(service, mock_repo):
    # File storage retired: any attached file is refused.
    file = MagicMock()
    file.filename = "test.pdf"

    with pytest.raises(ReleaseNoteFileUploadError):
        await service.create_release_note(
            "T",
            "D",
            "markup",
            file,
            1,
            10,
            "console",
        )


# ========================================
# GET RELEASE NOTE BY ID
# ========================================

@pytest.mark.asyncio
async def test_get_release_note_success(service, mock_repo):

    release_note = MagicMock(spec=ReleaseNotes)
    release_note.id = UUID("11111111-1111-1111-1111-111111111111")
    release_note.partner_id= UUID("10101010-1010-1010-1010-101010101010")
    release_note.da_file_path = "file.pdf"
    release_note.version_history = [{"version": "v1", "file_path": "file.pdf"}]
    release_note.title = "Title"
    release_note.description = "Desc"
    release_note.created_at = 123
    release_note.created_by= UUID("11111111-1111-1111-1111-111111111111")
    release_note.updated_by= UUID("22222222-2222-2222-2222-222222222222")
    release_note.svc_name = "console"
    release_note.markup = "markup"

    mock_repo.get_release_note_by_id.return_value = release_note

    current_user = {CurrentUserMap.ROLE_HIERARCHY_LEVEL: 1}

    result = await service.get_release_note_by_id(
        UUID("11111111-1111-1111-1111-111111111111"), UUID("10101010-1010-1010-1010-101010101010"), current_user, "console"
    )

    assert result.id == UUID("11111111-1111-1111-1111-111111111111")
    assert result.markup == "markup"


@pytest.mark.asyncio
async def test_get_release_note_not_found(service, mock_repo):

    mock_repo.get_release_note_by_id.return_value = None

    with pytest.raises(ReleaseNoteNotFoundError):
        await service.get_release_note_by_id(
            1,
            10,
            {CurrentUserMap.ROLE_HIERARCHY_LEVEL: 1},
            "console",
        )


@pytest.mark.asyncio
async def test_get_release_note_unauthorized(service, mock_repo):

    note = MagicMock(spec=ReleaseNotes)
    note.partner_id= UUID("20202020-2020-2020-2020-202020202020")
    note.svc_name = "console"
    note.markup = "markup"

    mock_repo.get_release_note_by_id.return_value = note

    with pytest.raises(UnauthorizedReleaseNoteAccessError):
        await service.get_release_note_by_id(
            1,
            10,
            {CurrentUserMap.ROLE_HIERARCHY_LEVEL: 5},
            "console",
        )


# ========================================
# GET ALL RELEASE NOTES
# ========================================

@pytest.mark.asyncio
async def test_get_all_release_notes_success(service, mock_repo):

    note = MagicMock(spec=ReleaseNotes)
    note.id = UUID("11111111-1111-1111-1111-111111111111")
    note.partner_id= UUID("10101010-1010-1010-1010-101010101010")
    note.title = "Title"
    note.description = "Desc"
    note.da_file_path = "file.pdf"
    note.created_at = 123
    note.updated_at = 456
    note.version_history = [{"version": "v2"}]
    note.markup = "markup"

    mock_repo.get_all_release_notes.return_value = [note]

    result = await service.get_all_release_notes(
        UUID("10101010-1010-1010-1010-101010101010"),
        {CurrentUserMap.ROLE_HIERARCHY_LEVEL: 1},
    )

    assert len(result) == 1
    assert result[0].version == "v2"


@pytest.mark.asyncio
async def test_get_all_release_notes_unauthorized_filtered(service, mock_repo):

    note = MagicMock(spec=ReleaseNotes)
    note.partner_id= UUID("20202020-2020-2020-2020-202020202020")

    mock_repo.get_all_release_notes.return_value = [note]

    result = await service.get_all_release_notes(
        UUID("10101010-1010-1010-1010-101010101010"),
        {CurrentUserMap.ROLE_HIERARCHY_LEVEL: 5},
    )

    assert result == []


# ========================================
# UPDATE RELEASE NOTE
# ========================================

@pytest.mark.asyncio
async def test_update_release_note_upload_failure(service, mock_repo):

    existing = MagicMock(spec=ReleaseNotes)
    existing.partner_id= UUID("10101010-1010-1010-1010-101010101010")
    existing.da_file_path = "old.pdf"
    existing.title = "Old"
    existing.description = "Old"
    existing.version_history = []
    existing.svc_name = "console"
    existing.markup = "old markup"
    existing.update_version_history = MagicMock()

    mock_repo.get_release_note_by_id.return_value = existing

    file = MagicMock()
    file.filename = "test.pdf"

    with pytest.raises(ReleaseNoteFileUploadError):
        await service.update_release_note(
            UUID("11111111-1111-1111-1111-111111111111"),
            "T",
            "D",
            "new markup",
            file,
            UUID("11111111-1111-1111-1111-111111111111"),
            UUID("10101010-1010-1010-1010-101010101010"),
            {CurrentUserMap.ROLE_HIERARCHY_LEVEL: 1},
        )


@pytest.mark.asyncio
async def test_update_release_note_not_found(service, mock_repo):

    mock_repo.get_release_note_by_id.return_value = None

    with pytest.raises(ReleaseNoteNotFoundError):
        await service.update_release_note(
            1,
            "T",
            "D",
            "markup",
            None,
            1,
            10,
            {CurrentUserMap.ROLE_HIERARCHY_LEVEL: 1},
        )


@pytest.mark.asyncio
async def test_update_release_note_unauthorized(service, mock_repo):

    note = MagicMock(spec=ReleaseNotes)
    note.partner_id= UUID("20202020-2020-2020-2020-202020202020")
    note.svc_name = "console"
    note.markup = "markup"

    mock_repo.get_release_note_by_id.return_value = note

    with pytest.raises(UnauthorizedReleaseNoteAccessError):
        await service.update_release_note(
            1,
            "T",
            "D",
            "markup",
            None,
            1,
            10,
            {CurrentUserMap.ROLE_HIERARCHY_LEVEL: 5},
        )


# ========================================
# GET HISTORY
# ========================================

@pytest.mark.asyncio
async def test_get_release_note_history_success(service, mock_repo):

    note = MagicMock(spec=ReleaseNotes)
    note.partner_id= UUID("10101010-1010-1010-1010-101010101010")
    note.version_history = [
        {"version": "v1", "file_path": "a.pdf"},
        {"version": "v2", "file_path": "b.pdf"},
    ]
    note.svc_name = "console"
    note.markup = "markup"

    mock_repo.get_release_note_by_id.return_value = note

    result = await service.get_release_note_history(
        UUID("11111111-1111-1111-1111-111111111111"),
        UUID("10101010-1010-1010-1010-101010101010"),
        {CurrentUserMap.ROLE_HIERARCHY_LEVEL: 1},
    )

    assert result[0]["version"] == "v2"


@pytest.mark.asyncio
async def test_get_release_note_history_not_found(service, mock_repo):

    mock_repo.get_release_note_by_id.return_value = None

    with pytest.raises(ReleaseNoteNotFoundError):
        await service.get_release_note_history(
            1,
            10,
            {CurrentUserMap.ROLE_HIERARCHY_LEVEL: 1},
        )


@pytest.mark.asyncio
async def test_get_release_note_history_unauthorized(service, mock_repo):

    note = MagicMock(spec=ReleaseNotes)
    note.partner_id= UUID("20202020-2020-2020-2020-202020202020")
    note.svc_name = "console"
    note.markup = "markup"

    mock_repo.get_release_note_by_id.return_value = note

    with pytest.raises(UnauthorizedReleaseNoteAccessError):
        await service.get_release_note_history(
            1,
            10,
            {CurrentUserMap.ROLE_HIERARCHY_LEVEL: 5},
        )