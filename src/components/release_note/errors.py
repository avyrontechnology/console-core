from src.components.common.errors import NotFoundError


class ReleaseNoteNotFoundError(NotFoundError):
    entity_name: str = "Release Note"


class UnauthorizedReleaseNoteAccessError(Exception):
    def __init__(self):
        super().__init__("Unauthorized access to this release note")


class ReleaseNoteFileUploadError(Exception):
    def __init__(self):
        super().__init__("Failed to upload release note file")
        
class ReleaseNoteUpdateError(Exception):
    def __init__(self):
        super().__init__("Failed to update release note")