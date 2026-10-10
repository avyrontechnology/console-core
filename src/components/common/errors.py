class NotFoundError(Exception):

    entity_name: str

    def __init__(self, entity_id):
        super().__init__(f"{self.entity_name} not found, id: {entity_id}")


class ErrorMsg:
    INTERNAL_SERVER_ERROR = "Internal server error"


class ResourceConflictError(Exception):
    """Base exception for resource conflicts, e.g., duplicate names or IDs."""
    pass



class ValidationError(Exception):
    """Base exception for validation errors, e.g., Name validation missing."""
    pass
