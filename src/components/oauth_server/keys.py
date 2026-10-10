"""RSA key management for OAuth token signing.

Loads one or more PEM private keys from ``OAUTH_SIGNING_KEY_PATH`` at import
time. Each key gets a stable ``kid`` derived from its filename so JWKS clients
can pick the right key. The lexicographically-newest file is "primary" — it's
the one we sign new tokens with. Every loaded key appears in JWKS, which
enables zero-downtime rotation:

  1. Drop the new key in. Restart. ``primary`` switches to it; old key still
     publishes so previously-issued tokens stay verifiable.
  2. Wait ``OAUTH_ACCESS_TOKEN_TTL_SECONDS`` + buffer.
  3. Delete the old key. Restart. JWKS shrinks to just the new key.

If no keys are present, we fail loudly at first use rather than at import —
because the OAuth router may not be mounted at all (env-gated) and we don't
want to crash console-service for non-OAuth deployments.
"""

import glob
import json
import os
import sys
import threading
from typing import Dict, List, Optional

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from src.components.oauth_server.config import OAUTH_SIGNING_KEY_PATH


def _warn(message: str) -> None:
    # Key loading happens at startup. We deliberately use stderr instead of
    # the configured ConsoleServiceLogger because this code can be imported
    # before the DI container has wired the logger; everything substantive
    # is logged again by the controller on first request.
    sys.stderr.write(f"[oauth.keys] {message}\n")


class _LoadedKey:
    """A single private key + its JWKS-shaped public projection."""

    __slots__ = ("kid", "private_key", "public_jwk")

    def __init__(self, kid: str, private_key: RSAPrivateKey):
        self.kid = kid
        self.private_key = private_key
        self.public_jwk = _to_public_jwk(kid, private_key)


def _to_public_jwk(kid: str, private_key: RSAPrivateKey) -> Dict[str, str]:
    """Serialise the public half as a JWK dict (RFC 7517)."""
    numbers = private_key.public_key().public_numbers()
    n = _b64url_uint(numbers.n)
    e = _b64url_uint(numbers.e)
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": n,
        "e": e,
    }


def _b64url_uint(value: int) -> str:
    import base64

    byte_length = (value.bit_length() + 7) // 8
    data = value.to_bytes(byte_length, "big")
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class KeyRing:
    """Thread-safe, lazily-initialised key store.

    Re-reads the keys directory on each ``ensure_loaded()`` only if the
    directory has been signalled stale via ``invalidate()``. Used at startup
    once, then never again under normal operation.
    """

    def __init__(self, key_dir: str):
        self._key_dir = key_dir
        self._keys: Dict[str, _LoadedKey] = {}
        self._primary_kid: Optional[str] = None
        self._loaded = False
        self._lock = threading.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load_from_disk()

    def invalidate(self) -> None:
        """Force a re-scan on next access. Used by the rotation runbook."""
        with self._lock:
            self._loaded = False
            self._keys = {}
            self._primary_kid = None

    @property
    def primary_kid(self) -> str:
        self.ensure_loaded()
        if not self._primary_kid:
            raise RuntimeError(
                "OAuth key ring is empty; cannot sign tokens. "
                f"Check OAUTH_SIGNING_KEY_PATH={self._key_dir!r}."
            )
        return self._primary_kid

    def primary_private_key(self) -> RSAPrivateKey:
        key = self._keys.get(self.primary_kid)
        if not key:
            raise RuntimeError(f"Primary key {self.primary_kid!r} is missing from keyring!")
        return key.private_key

    def primary_private_pem(self) -> bytes:
        """Serialize the primary key as a PKCS8 PEM. Cached by the cryptography
        library internally; cheap to call on every sign.
        """
        return self.primary_private_key().private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def get_public_jwk(self, kid: str) -> Optional[Dict[str, str]]:
        self.ensure_loaded()
        key = self._keys.get(kid)
        return key.public_jwk if key else None

    def jwks(self) -> Dict[str, List[Dict[str, str]]]:
        self.ensure_loaded()
        return {"keys": [k.public_jwk for k in self._keys.values()]}

    def jwks_json(self) -> str:
        return json.dumps(self.jwks(), separators=(",", ":"))

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load_from_disk(self) -> None:
        if not os.path.isdir(self._key_dir):
            _warn(
                f"signing-key dir {self._key_dir!r} does not exist; "
                "token issuance will fail until keys are provisioned"
            )
            self._loaded = True
            return

        pem_paths = sorted(glob.glob(os.path.join(self._key_dir, "*.pem")))
        if not pem_paths:
            _warn(
                f"no *.pem files found in {self._key_dir!r}; "
                "token issuance will fail until keys are provisioned"
            )
            self._loaded = True
            return

        keys: Dict[str, _LoadedKey] = {}
        for path in pem_paths:
            kid = os.path.splitext(os.path.basename(path))[0]
            try:
                with open(path, "rb") as f:
                    pem_bytes = f.read()
                priv = serialization.load_pem_private_key(
                    pem_bytes, password=None, backend=default_backend()
                )
                if not isinstance(priv, rsa.RSAPrivateKey):
                    _warn(f"{path!r} is not an RSA private key; skipping")
                    continue
                keys[kid] = _LoadedKey(kid, priv)
            except Exception as exc:
                _warn(f"failed to load {path!r}: {exc!r}")

        self._keys = keys
        self._primary_kid = max(keys.keys()) if keys else None
        self._loaded = True


# Module-level singleton — cheap, idempotent, safe to import early.
keyring = KeyRing(OAUTH_SIGNING_KEY_PATH)
