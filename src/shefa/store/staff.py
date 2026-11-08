"""Staff accounts and their sign-in sessions.

Front desk, owner and doctor sign in with a username and a password. A sign-in makes a random
session token; only its hash is stored, so a copy of the database signs nobody in. A doctor's
account is tied to one doctor, which is what keeps them to their own day.
"""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from shefa.auth import hash_password, verify_token

ROLES = ("desk", "owner", "doctor")
SESSION_HOURS = 12
MAX_FAILURES = 5
LOCKOUT_SECONDS = 15 * 60

_SCHEMA = """
CREATE TABLE IF NOT EXISTS staff_users (
    id            INTEGER PRIMARY KEY,
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('desk', 'owner', 'doctor')),
    doctor_id     INTEGER,
    password_hash TEXT NOT NULL,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS staff_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL REFERENCES staff_users(id),
    expires_at REAL NOT NULL
);
"""


class StaffError(Exception):
    """Something a person running the clinic can be told."""


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class StaffStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.executescript(_SCHEMA)
        self.connection.commit()
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def close(self) -> None:
        self.connection.close()

    # -- accounts -----------------------------------------------------------------------

    def add_user(
        self,
        username: str,
        password: str,
        role: str,
        *,
        display_name: str = "",
        doctor_id: int | None = None,
    ) -> int:
        username = username.strip()
        if not username:
            raise StaffError("A username is needed.")
        if role not in ROLES:
            raise StaffError(f"Role must be one of {', '.join(ROLES)}.")
        if role == "doctor" and doctor_id is None:
            raise StaffError("A doctor account must be tied to a doctor.")
        if role != "doctor":
            doctor_id = None
        try:
            record = hash_password(password)
        except ValueError as exc:
            raise StaffError(str(exc)) from exc
        try:
            with self.connection:
                cur = self.connection.execute(
                    "INSERT INTO staff_users (username, display_name, role, doctor_id,"
                    " password_hash, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (username, display_name or username, role, doctor_id, record, time.time()),
                )
        except sqlite3.IntegrityError as exc:
            raise StaffError(f"The username {username!r} is already taken.") from exc
        return int(cur.lastrowid)

    def set_password(self, username: str, password: str) -> None:
        record = hash_password(password)
        with self.connection:
            cur = self.connection.execute(
                "UPDATE staff_users SET password_hash = ? WHERE username = ?", (record, username)
            )
            if cur.rowcount == 0:
                raise StaffError(f"No account {username!r}.")
            self.connection.execute(
                "DELETE FROM staff_sessions WHERE user_id = (SELECT id FROM staff_users"
                " WHERE username = ?)",
                (username,),
            )

    def set_active(self, username: str, active: bool) -> None:
        with self.connection:
            cur = self.connection.execute(
                "UPDATE staff_users SET active = ? WHERE username = ?", (int(active), username)
            )
            if cur.rowcount == 0:
                raise StaffError(f"No account {username!r}.")
            if not active:
                self.connection.execute(
                    "DELETE FROM staff_sessions WHERE user_id = (SELECT id FROM staff_users"
                    " WHERE username = ?)",
                    (username,),
                )

    def users(self) -> list[dict[str, Any]]:
        return [
            {k: row[k] for k in ("username", "display_name", "role", "doctor_id", "active")}
            for row in self.connection.execute("SELECT * FROM staff_users ORDER BY username")
        ]

    def has_users(self) -> bool:
        return self.connection.execute("SELECT 1 FROM staff_users LIMIT 1").fetchone() is not None

    # -- sign-in ------------------------------------------------------------------------

    def _locked(self, username: str) -> bool:
        now = time.time()
        recent = [t for t in self._failures.get(username.lower(), []) if now - t < LOCKOUT_SECONDS]
        self._failures[username.lower()] = recent
        return len(recent) >= MAX_FAILURES

    def sign_in(self, username: str, password: str) -> str | None:
        """A session token for a correct username and password, else None.

        Five wrong tries lock the username for fifteen minutes; the lock also refuses the right
        password, so guessing cannot be told from being locked out.
        """
        with self._lock:
            if self._locked(username):
                return None
            row = self.connection.execute(
                "SELECT * FROM staff_users WHERE username = ? AND active = 1", (username.strip(),)
            ).fetchone()
            ok = False
            if row is not None:
                try:
                    ok = verify_token(password, row["password_hash"])
                except ValueError:
                    ok = False
            if not ok:
                self._failures.setdefault(username.lower(), []).append(time.time())
                return None
            self._failures.pop(username.lower(), None)
        token = secrets.token_urlsafe(32)
        with self.connection:
            self.connection.execute(
                "DELETE FROM staff_sessions WHERE expires_at < ?", (time.time(),)
            )
            self.connection.execute(
                "INSERT INTO staff_sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
                (_digest(token), row["id"], time.time() + SESSION_HOURS * 3600),
            )
        return token

    def user_for_session(self, token: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT u.* FROM staff_sessions s JOIN staff_users u ON u.id = s.user_id"
            " WHERE s.token_hash = ? AND s.expires_at > ? AND u.active = 1",
            (_digest(token), time.time()),
        ).fetchone()
        return dict(row) if row else None

    def sign_out(self, token: str) -> None:
        with self.connection:
            self.connection.execute(
                "DELETE FROM staff_sessions WHERE token_hash = ?", (_digest(token),)
            )


_default: StaffStore | None = None
_default_lock = threading.Lock()


def default_staff_store() -> StaffStore:
    global _default
    with _default_lock:
        if _default is None:
            from shefa.config.settings import settings

            _default = StaffStore(settings.storage.db_path)
        return _default


def set_default_staff_store(store: StaffStore | None) -> None:
    global _default
    with _default_lock:
        _default = store
