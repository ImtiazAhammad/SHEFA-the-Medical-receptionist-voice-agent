"""Encrypting what patients say, while it sits on disk.

Call transcripts, the words a caller used to ask for a person, and the phone numbers waiting for a
call-back are patient data. They are encrypted with a key that is NOT in the database, so a copy
of the database file (a backup, a stolen disk, a mistaken upload) reads as noise without it.

* The key comes from ``SHEFA_DATA_KEY`` (a Fernet key) or, if that is unset, from a key file
  (``storage.key_file``) created on first use with owner-only permissions.
* **Lose the key and the transcripts are gone.** Back the key up separately from the database.
* Rows written before this existed are plaintext and stay readable; new rows are encrypted.
* The clinic directory (patients' names and phone numbers) is not encrypted here, because it must
  be searched by phone number. Protect it with full-disk encryption (docs/security.md).
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

import structlog
from cryptography.fernet import Fernet, InvalidToken

logger = structlog.get_logger("shefa")

PREFIX = "enc1:"
UNREADABLE = "[unreadable: wrong or missing data key]"


class DataCipher:
    def __init__(self, key: bytes | str, *, enabled: bool = True) -> None:
        self._fernet = Fernet(key)
        self.enabled = enabled

    def encrypt(self, value: str | None) -> str | None:
        if value is None or not self.enabled:
            return value
        return PREFIX + self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str | None) -> str | None:
        """Plaintext rows (older data) pass through; an unreadable token never raises."""
        if value is None or not value.startswith(PREFIX):
            return value
        try:
            return self._fernet.decrypt(value[len(PREFIX) :].encode("ascii")).decode("utf-8")
        except InvalidToken:
            logger.error("data_key_cannot_decrypt_a_stored_value")
            return UNREADABLE


def load_or_create_key(key_file: str | Path) -> bytes:
    """``SHEFA_DATA_KEY`` if set, else the key file, created (mode 0600) on first use."""
    from_env = os.environ.get("SHEFA_DATA_KEY", "").strip()
    if from_env:
        return from_env.encode("ascii")
    path = Path(key_file)
    if path.exists():
        return path.read_bytes().strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(key + b"\n")
    logger.warning("data_key_created", path=str(path), note="back this file up separately")
    return key


_lock = threading.Lock()
_cipher: DataCipher | None = None


def default_cipher() -> DataCipher:
    """The process-wide cipher, built from settings on first use."""
    global _cipher
    with _lock:
        if _cipher is None:
            from shefa.config.settings import settings

            storage = settings.storage
            _cipher = DataCipher(
                load_or_create_key(storage.key_file), enabled=storage.encrypt_at_rest
            )
        return _cipher


def set_default_cipher(cipher: DataCipher | None) -> None:
    """Swap the process-wide cipher (tests, key rotation)."""
    global _cipher
    with _lock:
        _cipher = cipher
