"""Provider credential encryption — AES-256-GCM.

Vendored from main repo, simplified — reads CREDENTIAL_ENCRYPTION_KEY directly
from env. If unset, derives a deterministic dev key from a fixed seed so that
local development doesn't require any setup. In production, set a real
64-char hex string.
"""

from __future__ import annotations

import hashlib
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _get_encryption_key() -> bytes:
    key_hex = os.environ.get("CREDENTIAL_ENCRYPTION_KEY", "")
    if key_hex:
        try:
            raw = bytes.fromhex(key_hex)
            if len(raw) >= 32:
                return raw[:32]
        except ValueError:
            pass
        return hashlib.sha256(key_hex.encode()).digest()
    # Dev fallback so test fixtures and `docker compose up` Just Work.
    return hashlib.sha256(b"orcarouter-lite-dev-key").digest()


def encrypt_credential(plaintext: str) -> bytes:
    aes = AESGCM(_get_encryption_key())
    nonce = os.urandom(12)
    return nonce + aes.encrypt(nonce, plaintext.encode("utf-8"), None)


def decrypt_credential(blob: bytes) -> str:
    aes = AESGCM(_get_encryption_key())
    nonce, ciphertext = blob[:12], blob[12:]
    return aes.decrypt(nonce, ciphertext, None).decode("utf-8")
