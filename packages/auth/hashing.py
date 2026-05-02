"""API key generation, hashing, password utilities.

Vendored from main repo, simplified — no Settings dependency, pepper read
directly from env. Lite is single-tenant so the brute-force surface is
the operator's own machine.
"""

import hashlib
import hmac
import os
import secrets


def _get_api_key_pepper() -> bytes | None:
    pepper = os.environ.get("API_KEY_PEPPER", "")
    if not pepper or len(pepper) < 32:
        return None
    return pepper.encode("utf-8")


def generate_api_key() -> tuple[str, str, str]:
    """Generate (full_key, key_hash, key_prefix). Plaintext shown to user once."""
    random_part = secrets.token_hex(16)
    full_key = f"sk-orca-{random_part}"
    key_hash = hash_api_key(full_key)
    key_prefix = f"sk-orca-....{random_part[-4:]}"
    return full_key, key_hash, key_prefix


def hash_api_key(raw_key: str) -> str:
    """HMAC-SHA256 with pepper if configured, else plain SHA-256."""
    pepper = _get_api_key_pepper()
    if pepper is None:
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    return hmac.new(pepper, raw_key.encode("utf-8"), hashlib.sha256).hexdigest()


def api_key_lookup_hashes(raw_key: str) -> tuple[str, str]:
    """Return (legacy_sha256, peppered) for dual-lookup during pepper rollout."""
    legacy = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    peppered = hash_api_key(raw_key)
    return legacy, peppered
