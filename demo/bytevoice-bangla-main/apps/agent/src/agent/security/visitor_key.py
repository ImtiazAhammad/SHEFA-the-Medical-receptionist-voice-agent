"""Decrypts a visitor's own Gemini API key, sealed by the web token route with AES-256-GCM.

The sealing key is derived from INTERNAL_API_TOKEN, which only the web server and the agent hold, so the
visitor key never appears in plain text in LiveKit dispatch metadata.
"""

import base64
import hashlib
import json
import logging

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from agent.constants import LOGGER_NAME, VISITOR_KEY_DERIVATION_LABEL

logger = logging.getLogger(LOGGER_NAME)

NONCE_LENGTH = 12


def _sealing_key(secret: str) -> bytes:
    return hashlib.sha256(f"{VISITOR_KEY_DERIVATION_LABEL}:{secret}".encode()).digest()


def seal_visitor_key(visitor_key: str, secret: str, nonce: bytes) -> str:
    sealed = nonce + AESGCM(_sealing_key(secret)).encrypt(nonce, visitor_key.encode(), None)
    return base64.urlsafe_b64encode(sealed).decode().rstrip("=")


def open_visitor_key(sealed: str, secret: str) -> str | None:
    try:
        raw = base64.urlsafe_b64decode(sealed + "=" * (-len(sealed) % 4))
        nonce, ciphertext = raw[:NONCE_LENGTH], raw[NONCE_LENGTH:]
        return AESGCM(_sealing_key(secret)).decrypt(nonce, ciphertext, None).decode()
    except (InvalidTag, ValueError):
        logger.warning("visitor API key could not be opened; using the clinic's key")
        return None


def visitor_key_from_metadata(metadata: str, secret: str) -> str | None:
    if not metadata or not secret:
        return None
    try:
        sealed = json.loads(metadata).get("sealed_api_key")
    except (json.JSONDecodeError, AttributeError):
        return None
    return open_visitor_key(sealed, secret) if isinstance(sealed, str) and sealed else None
