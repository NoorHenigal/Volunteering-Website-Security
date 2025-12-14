"""Application-level encryption service using XSalsa20-Poly1305 and SHA-256.

Algorithm notes:
- SecretBox uses XSalsa20-Poly1305 (not XChaCha20, but same security class)
- 24-byte nonces are random-safe (no counter management needed)
- Encryption is randomized (new nonce per write) for semantic security
- Email hashing is deterministic (SHA-256) to enable lookups without decryption

General notes:
- Never reuse nonces (24-byte random nonces are auto-generated per encryption)
- Email hash is deterministic for lookups; ciphertext is randomized
"""

import base64
import hashlib
import os
from functools import lru_cache

from nacl.secret import SecretBox

from app.core.config import settings

NONCE_SIZE = SecretBox.NONCE_SIZE


class EncryptionService:
    """Handles field-level encryption and email hashing.

    Key format: 32 bytes, provided as 64-character hex string via config.
    """

    def __init__(self, key: bytes) -> None:
        """Initialize with a 32-byte encryption key.

        Args:
            key: Exactly 32 bytes. Caller is responsible for decoding from hex.

        Raises:
            ValueError: If key is not exactly 32 bytes.
        """
        if len(key) != SecretBox.KEY_SIZE:
            msg = f"Encryption key must be exactly {SecretBox.KEY_SIZE} bytes, got {len(key)}"
            raise ValueError(msg)
        self._box = SecretBox(key)

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext string, returning base64-encoded ciphertext.

        The output includes the nonce prepended to the ciphertext.
        Format: base64(nonce || ciphertext || tag)
        """
        if not plaintext:
            return ""
        data = plaintext.encode("utf-8")
        encrypted = self._box.encrypt(data)
        return base64.b64encode(encrypted).decode("ascii")

    def decrypt(self, ciphertext_b64: str) -> str:
        """Decrypt base64-encoded ciphertext, returning plaintext string."""
        if not ciphertext_b64:
            return ""
        encrypted = base64.b64decode(ciphertext_b64)
        decrypted = self._box.decrypt(encrypted)
        return decrypted.decode("utf-8")

    @staticmethod
    def hash_email(email: str) -> str:
        """Create deterministic SHA-256 hash of normalized email.

        Email is normalized (lowercase & stripped) before hashing to ensure
        consistent lookups regardless of case or whitespace.
        """
        normalized = email.lower().strip()
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    @staticmethod
    def generate_key() -> bytes:
        """Generate a new random 32-byte encryption key."""
        return os.urandom(SecretBox.KEY_SIZE)


@lru_cache(maxsize=1)
def get_encryption_service() -> EncryptionService:
    """Get singleton encryption service instance.

    The encryption key is expected to be a 64-character hex string (32 bytes).
    """
    hex_key = settings.encryption_key.get_secret_value()
    try:
        key = bytes.fromhex(hex_key)
    except ValueError as e:
        msg = "ENCRYPTION_KEY must be a valid hex string (64 characters for 32 bytes)"
        raise ValueError(msg) from e
    if len(key) != SecretBox.KEY_SIZE:
        msg = (
            f"ENCRYPTION_KEY must decode to exactly {SecretBox.KEY_SIZE} bytes (got {len(key)}). Use 64 hex characters."
        )
        raise ValueError(msg)
    return EncryptionService(key)


def encrypt_field(value: str | None) -> str | None:
    """Encrypt a field value if not None/empty."""
    if not value:
        return None
    return get_encryption_service().encrypt(value)


def decrypt_field(ciphertext: str | None) -> str | None:
    """Decrypt a field value if not None/empty."""
    if not ciphertext:
        return None
    return get_encryption_service().decrypt(ciphertext)


def hash_email(email: str) -> str:
    """Hash email for lookups (convenience wrapper)."""
    return EncryptionService.hash_email(email)


__all__ = [
    "EncryptionService",
    "decrypt_field",
    "encrypt_field",
    "get_encryption_service",
    "hash_email",
]
