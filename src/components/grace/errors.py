from uuid import UUID
"""Custom exceptions for the Grace Period feature."""


class GraceForbiddenError(Exception):
    """Raised when the requesting user's partner is not internal."""

    def __init__(
        self, message: str = "Only internal team members can grant grace periods."
    ):
        super().__init__(message)


class GraceNotEligibleError(Exception):
    """
    Raised when the partner has an active or scheduled entitlement for the
    given service — grace is only allowed when the partner is completely blank.
    """

    def __init__(
        self,
        partner_id: UUID,
        service_name: str,
        reason: str = "active or scheduled entitlement exists",
    ):
        super().__init__(
            "Grace period cannot be granted for partner_id={} service={}: {}.".format(
                partner_id, service_name, reason
            )
        )


class GraceMaxAttemptsError(Exception):
    """Raised when the partner has exhausted the maximum allowed grace attempts for a service."""

    def __init__(self, partner_id: UUID, service_name: str, max_attempts: int):
        super().__init__(
            "Partner {} has reached the maximum of {} grace attempts for service {}.".format(
                partner_id, max_attempts, service_name
            )
        )


class GraceAlreadyActiveError(Exception):
    """Raised when an ACTIVE grace record already exists for the partner + service."""

    def __init__(self, partner_id: UUID, service_name: str):
        super().__init__(
            "An active grace period already exists for partner_id={} service={}.".format(
                partner_id, service_name
            )
        )


class GraceInvalidDaysError(Exception):
    """Raised when granted_days is out of the allowed range."""

    def __init__(self, granted_days: int, max_days: int):
        super().__init__(
            "granted_days={} is invalid. Must be between 1 and {}.".format(
                granted_days, max_days
            )
        )


class GraceNoPriorOrderError(Exception):
    """
    Raised when no prior SUCCESS order exists for the partner + service.
    Without a prior order we cannot determine which services to extend.
    """

    def __init__(self, partner_id: UUID, service_name: str):
        super().__init__(
            "No prior successful order found for partner_id={} service={}. "
            "Cannot grant grace without an order history.".format(
                partner_id, service_name
            )
        )


class GraceNotFoundError(Exception):
    """Raised when a grace record is expected but not found."""

    def __init__(self, grace_id: UUID):
        super().__init__("Grace record with id={} not found.".format(grace_id))
