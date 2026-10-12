from src.components.audit_log.repositories import AuditLogRepository
from src.components.audit_log.schema import AuditLogSchema


class AuditService:
    """
    AuditService class provides functionality to log actions performed on resources.

    Attributes:
        __audit_log_repository (AuditLogRepository): An instance of AuditLogRepository to interact with the audit log storage.

    Methods:
        log_action(action, resource, resource_id, performed_by, resource_previous_state=None, resource_current_state=None, details=None):
            Asynchronously logs an action performed on a resource.

            Args:
                action (str): The action performed.
                resource (str): The type of resource on which the action was performed.
                resource_id (int): The ID of the resource.
                performed_by (int): The ID of the user who performed the action.
                resource_previous_state (str, optional): The previous state of the resource. Defaults to None.
                resource_current_state (str, optional): The current state of the resource. Defaults to None.
                details (str, optional): Additional details about the action. Defaults to None.
    """

    def __init__(self, audit_log_repository: AuditLogRepository) -> None:
        self.__audit_log_repository = audit_log_repository

    async def log_action(self, log_entry: AuditLogSchema):
        # resource_id column is String(36): stringify UUIDs at the boundary.
        if log_entry.resource_id is not None:
            log_entry.resource_id = str(log_entry.resource_id)
        await self.__audit_log_repository.create_audit_log(log_entry)
