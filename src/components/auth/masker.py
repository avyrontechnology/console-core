"""
Sensitive-data masking helpers.
"""
from typing import Any

# Define a constant instead of duplicating this literal 4 times"
_MASKED = "******"
_PARTIAL_MASK = "****"


# Internal helpers

def _mask_email(value: str) -> str:
    """
    Partially masks an email address.
    Example: shikha.singh@gmail.com  →  sh******@gmail.com
    """
    if not isinstance(value, str) or "@" not in value:
        return value
    local, _, domain = value.partition("@")
    masked_local = (local[:2] + _MASKED) if len(local) > 2 else "***"
    return f"{masked_local}@{domain}"


def _mask_credential(value: str) -> str:
    """
    Partially masks a credential (email or phone/username).
    Email   : shikha.singh@gmail.com  →  sh******@gmail.com
    Other   : user123  →  us****23
    """
    if not isinstance(value, str):
        return value
    if "@" in value:
        return _mask_email(value)
    if len(value) > 4:
        return value[:2] + _PARTIAL_MASK + value[-2:]
    return "***"

# Internal: single-value masking helpers

def _mask_password_value(key: str, value: Any) -> Any:
    if "password" in key.lower() and isinstance(value, str) and value:
        return _MASKED
    return value


def _mask_email_payload_value(key: str, value: Any) -> Any:
    lower = key.lower()

    # Full redaction for password fields
    if "password" in lower:
        if isinstance(value, str) and value:
            return _MASKED
        return value

    # Partial masking for email fields
    if "email" in lower:
        if isinstance(value, str):
            return _mask_email(value)
        if isinstance(value, list):
            return [_mask_email(v) if isinstance(v, str) else v for v in value]

    # Partial masking for credential fields (email or username/phone)
    if "credential" in lower and isinstance(value, str):
        return _mask_credential(value)

    return value

# Public: password-only masking  (used for LOGS)

def mask_for_logs(data: Any) -> Any:
    """
    Recursively walks a dict / list and returns a copy with ONLY password
    fields masked. All other fields (email, credential, phone, etc.) are
    returned unchanged.

    Rule  →  any key containing 'password'  →  '******'

    Usage:
        safe_body = mask_for_logs(request_body_dict)
    """
    if isinstance(data, dict):
        return {k: _mask_password_value(k, mask_for_logs(v)) for k, v in data.items()}
    if isinstance(data, list):
        return [mask_for_logs(item) for item in data]
    return data


# Public: full masking for email notifications  (used for ERROR EMAILS)

def mask_for_email(data: Any) -> Any:
    """
    Recursively walks a dict / list and returns a copy with:
      - password fields  →  fully masked  ('******')
      - email fields     →  partially masked  (sh******@gmail.com)
      - credential fields→  partially masked  (us****23)

    All other fields are returned unchanged.

    Usage:
        safe_payload = mask_for_email(request_body_dict)
    """
    if isinstance(data, dict):
        return {k: _mask_email_payload_value(k, mask_for_email(v)) for k, v in data.items()}
    if isinstance(data, list):
        return [mask_for_email(item) for item in data]
    return data

# Public: helper for masking a single password string in log messages

def mask_password(password: str) -> str:
    """Mask a single password string for use in log messages."""
    if isinstance(password, str) and password:
        return _MASKED
    return password