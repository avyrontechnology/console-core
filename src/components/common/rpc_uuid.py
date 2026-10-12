"""gRPC<->UUID boundary helpers (server side).

Proto3 carries IDs as strings; the DB layer uses UUID columns.
Parse inbound strings to UUID (INVALID_ARGUMENT on garbage) and
stringify outbound UUIDs for proto string fields.
"""
from typing import Iterable, List, Optional
from uuid import UUID

from grpc import StatusCode
from grpc_interceptor.exceptions import GrpcException


def parse_uuid(value, field_name: str = "id") -> UUID:
    """Parse one proto string ID to UUID. Raises GrpcException(INVALID_ARGUMENT)."""
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise GrpcException(
            details=f"Invalid UUID for field '{field_name}': {value!r}",
            status_code=StatusCode.INVALID_ARGUMENT,
        )


def parse_uuid_or_none(value, field_name: str = "id") -> Optional[UUID]:
    """Parse optional proto string ID; empty string / None -> None."""
    if value is None:
        return None
    if isinstance(value, str) and not value:
        return None
    return parse_uuid(value, field_name)


def parse_uuid_list(values: Iterable, field_name: str = "ids") -> List[UUID]:
    """Parse a repeated proto string ID field to a UUID list."""
    return [parse_uuid(v, field_name) for v in (values or [])]


def uuid_str(value) -> str:
    """Stringify a UUID for a proto string field (None -> '')."""
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def uuid_list_str(values: Iterable) -> str:
    """Render a UUID list for logs as [hex, hex] (list.__str__ would repr)."""
    return "[" + ", ".join(uuid_str(v) for v in (values or [])) + "]"
