"""
Fernet-based encryption utility for sensitive partner database credentials.

Uses the existing SECRET_KEY from environment for key derivation.
Passwords are encrypted at rest and decrypted only when building
connection strings.
"""

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from src.core.environment import ENV

logger = logging.getLogger(__name__)


def _derive_fernet_key(secret: str) -> bytes:
    """
    Derive a 32-byte Fernet-compatible key from the application SECRET_KEY
    using SHA-256.  Fernet requires url-safe base64 of exactly 32 bytes.
    """
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_value(plaintext: str) -> str:
    """Encrypt a plaintext string and return the Fernet token as a string."""
    secret = ENV.SECRET_KEY
    if not secret:
        logger.warning(
            "SECRET_KEY is not set — storing DB password in plaintext (dev-only)"
        )
        return plaintext

    key: bytes = _derive_fernet_key(secret)
    f: Fernet= Fernet(key)
    encripted: str=  f.encrypt(plaintext.encode("utf-8")).decode("utf-8")
    return encripted


def decrypt_value(ciphertext: str) -> str:
    """Decrypt a Fernet token back to plaintext."""
    secret = ENV.SECRET_KEY
    if not secret:
        logger.warning(
            "SECRET_KEY is not set — assuming DB password is plaintext (dev-only)"
        )
        return ciphertext

    key = _derive_fernet_key(secret)
    f = Fernet(key)
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        logger.error(
            "Failed to decrypt partner DB password — "
            "SECRET_KEY may have changed or value is corrupt"
        )
        raise ValueError("Failed to decrypt partner database password")
