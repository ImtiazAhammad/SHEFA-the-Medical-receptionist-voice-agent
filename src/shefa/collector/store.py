"""The collection database (SQLite, WAL) and the audio folder.

Everything about contributors, clips, reviews and staff lives here, so the rules that matter are
in one place: a clip's transcript is only final when the right number of different reviewers
agree, a withdrawn clip leaves a tombstone so it can never come back from a backup, and a
contributor's secret and delete code are stored only as hashes.
"""
# ruff: noqa: E501, N812, TC001, TC003

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import sqlite3
import threading
import time
import unicodedata
import uuid
from pathlib import Path
from typing import Any

from shefa.auth import hash_password, verify_token
from shefa.collector import text as T
from shefa.collector.config import CollectorConfig

USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,29}$")
MIN_PASSWORD = 10
MAX_FAILURES = 5
LOCKOUT_SECONDS = 15 * 60
TEMP_PASSWORD_HOURS = 72
ROOM_JOIN_HOURS = 24
COMMON_PASSWORDS = frozenset(
    {
        "password",
        "password1",
        "12345678",
        "123456789",
        "1234567890",
        "qwertyui",
        "qwerty123",
        "bangladesh",
        "iloveyou",
        "11111111",
        "00000000",
        "abcd1234",
        "admin123",
        "shefa123",
    }
)
CLIP_ID = re.compile(r"^[a-f0-9]{32}$")
REJECT_FLAGS = frozenset({"unusable", "other_language", "personal_details", "offensive"})
STAFF_ROLES = ("admin", "adjudicator", "reviewer")
_SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS staff (
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
  active INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash TEXT PRIMARY KEY, staff_id INTEGER NOT NULL, created_at REAL NOT NULL, expires_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS voice_packs (
  staff_id INTEGER PRIMARY KEY, public_id TEXT NOT NULL UNIQUE, enabled INTEGER NOT NULL DEFAULT 0,
  consent_at REAL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS voice_lines (
  staff_id INTEGER NOT NULL, name TEXT NOT NULL, path TEXT NOT NULL, duration_s REAL NOT NULL,
  created_at REAL NOT NULL, PRIMARY KEY (staff_id, name));
CREATE TABLE IF NOT EXISTS campaigns (
  code TEXT PRIMARY KEY, name TEXT NOT NULL, from_name TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS contributors (
  id TEXT PRIMARY KEY, secret_hash TEXT NOT NULL, delete_hash TEXT NOT NULL UNIQUE,
  campaign TEXT NOT NULL DEFAULT '', from_name TEXT NOT NULL DEFAULT '', age_band TEXT NOT NULL DEFAULT '',
  gender TEXT NOT NULL DEFAULT '', division TEXT NOT NULL DEFAULT '', device TEXT NOT NULL DEFAULT '',
  nickname TEXT NOT NULL DEFAULT '', credit_ok INTEGER NOT NULL DEFAULT 0, ip_hash TEXT NOT NULL DEFAULT '',
  consent_version TEXT NOT NULL, consent_at REAL NOT NULL, created_at REAL NOT NULL, deleted_at REAL);
CREATE TABLE IF NOT EXISTS speakers (
  id TEXT PRIMARY KEY, contributor_id TEXT NOT NULL, label TEXT NOT NULL DEFAULT '',
  split TEXT NOT NULL, created_at REAL NOT NULL, delete_hash TEXT NOT NULL DEFAULT '',
  age_band TEXT NOT NULL DEFAULT '', gender TEXT NOT NULL DEFAULT '', division TEXT NOT NULL DEFAULT '',
  nickname TEXT NOT NULL DEFAULT '', credit_ok INTEGER NOT NULL DEFAULT 0, deleted_at REAL);
CREATE TABLE IF NOT EXISTS clips (
  id TEXT PRIMARY KEY, speaker_id TEXT NOT NULL, contributor_id TEXT NOT NULL,
  card_id TEXT NOT NULL DEFAULT '', step_id TEXT NOT NULL DEFAULT '', slot TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT '', question_bn TEXT NOT NULL DEFAULT '', expected_text TEXT,
  facts TEXT NOT NULL DEFAULT '{}', setting TEXT NOT NULL DEFAULT '', room TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL DEFAULT '', turn INTEGER NOT NULL DEFAULT 0, split TEXT NOT NULL,
  duration_s REAL NOT NULL, rms_db REAL, peak REAL, clip_fraction REAL, speech_ratio REAL, snr_db REAL,
  codec TEXT, bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, path TEXT NOT NULL, ua TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT 'new', draft_text TEXT, final_text TEXT, status TEXT NOT NULL DEFAULT 'pending',
  created_at REAL NOT NULL, deleted_at REAL);
CREATE INDEX IF NOT EXISTS clips_status ON clips(status, split);
CREATE INDEX IF NOT EXISTS clips_speaker ON clips(speaker_id);
CREATE TABLE IF NOT EXISTS reviews (
  id INTEGER PRIMARY KEY, clip_id TEXT NOT NULL, staff_id INTEGER NOT NULL, kind TEXT NOT NULL,
  text TEXT NOT NULL, flags TEXT NOT NULL DEFAULT '[]', seconds REAL, created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS reviews_clip ON reviews(clip_id);
CREATE TABLE IF NOT EXISTS seed_checks (
  staff_id INTEGER NOT NULL, clip_id TEXT NOT NULL, cer REAL NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS tombstones (
  clip_id TEXT PRIMARY KEY, sha256 TEXT NOT NULL, reason TEXT NOT NULL, at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS rooms (
  code TEXT PRIMARY KEY, card_id TEXT NOT NULL, caller_cid TEXT NOT NULL, desk_cid TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL DEFAULT 'open', created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY, at REAL NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL DEFAULT '');
"""


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _small_int(value: Any) -> int:
    try:
        return max(0, min(int(value or 0), 999))
    except (TypeError, ValueError):
        return 0


def _fraction(key: str) -> float:
    return int(_sha(key)[:8], 16) / 0xFFFFFFFF


class StoreError(Exception):
    """A rule was broken; the message is safe to show the caller."""

    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class LocalAudioStore:
    """Audio on the founder's own disk. Swappable: a cloud store only needs these four methods."""

    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def path_for(self, clip_id: str, ext: str) -> Path:
        return self.root / clip_id[:2] / f"{clip_id}{ext}"

    def save(self, clip_id: str, ext: str, data: bytes) -> Path:
        path = self.path_for(clip_id, ext)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        with open(tmp, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(path)  # the clip exists whole or not at all
        return path

    def read(self, path: str) -> bytes:
        return Path(path).read_bytes()

    def delete(self, path: str) -> None:
        Path(path).unlink(missing_ok=True)

    def free_mb(self) -> int:
        return int(shutil.disk_usage(self.root).free / 1_000_000)


class CollectorStore:
    def __init__(self, config: CollectorConfig):
        self.config = config
        config.data_dir.mkdir(parents=True, exist_ok=True)
        self.audio = LocalAudioStore(config.audio_dir)
        self._lock = threading.RLock()
        self._failures: dict[str, list[float]] = {}
        self._dummy_hash = hash_password(
            "not-a-real-password", iterations=config.password_iterations
        )
        self.db = sqlite3.connect(config.db_path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript(_SCHEMA)
        self._migrate()
        os.chmod(config.db_path, 0o600)

    def _migrate(self) -> None:
        """Older databases made before speakers carried their own profile and delete code."""
        staff_cols = {r["name"] for r in self.db.execute("PRAGMA table_info(staff)")}
        for column, ddl in (
            ("username", "TEXT"),
            ("password_hash", "TEXT NOT NULL DEFAULT ''"),
            ("must_change", "INTEGER NOT NULL DEFAULT 0"),
            ("temp_until", "REAL"),
        ):
            if column not in staff_cols:
                self.db.execute(f"ALTER TABLE staff ADD COLUMN {column} {ddl}")
        self.db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS staff_username ON staff(username COLLATE NOCASE) "
            "WHERE username IS NOT NULL"
        )
        have = {r["name"] for r in self.db.execute("PRAGMA table_info(speakers)")}
        for column, ddl in (
            ("delete_hash", "TEXT NOT NULL DEFAULT ''"),
            ("age_band", "TEXT NOT NULL DEFAULT ''"),
            ("gender", "TEXT NOT NULL DEFAULT ''"),
            ("division", "TEXT NOT NULL DEFAULT ''"),
            ("nickname", "TEXT NOT NULL DEFAULT ''"),
            ("credit_ok", "INTEGER NOT NULL DEFAULT 0"),
            ("deleted_at", "REAL"),
        ):
            if column not in have:
                self.db.execute(f"ALTER TABLE speakers ADD COLUMN {column} {ddl}")

    # ---- helpers -------------------------------------------------------------------------
    def _q(self, sql: str, args: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.db.execute(sql, args).fetchall()

    def _one(self, sql: str, args: tuple = ()) -> sqlite3.Row | None:
        rows = self._q(sql, args)
        return rows[0] if rows else None

    def _x(self, sql: str, args: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.db.execute(sql, args)

    def audit(self, actor: str, action: str, detail: str = "") -> None:
        self._x(
            "INSERT INTO audit(at,actor,action,detail) VALUES (?,?,?,?)",
            (time.time(), actor, action, detail[:500]),
        )

    # ---- settings ------------------------------------------------------------------------
    def get_setting(self, key: str, default: str = "") -> str:
        row = self._one("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else default

    def set_setting(self, key: str, value: str) -> None:
        self._x(
            "INSERT INTO settings(key,value) VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    # ---- staff ---------------------------------------------------------------------------
    # Accounts are a username and a password. A sign-in makes a random session token; only its
    # hash is stored, so a copy of the database signs nobody in. The long tokens of the first
    # version keep working only for a person who has not been given a password yet.
    def _check_username(self, username: str) -> str:
        username = username.strip().lower()
        if not USERNAME.match(username):
            raise StoreError(
                "bad_username", "a username is 3 to 30 letters, digits, dot, dash or underscore"
            )
        return username

    def _hash(self, password: str, username: str = "") -> str:
        password = unicodedata.normalize("NFC", password)
        if username and password.lower() == username.lower():
            raise StoreError("weak_password", "the password must not be the username")
        if password.isdigit():  # a mobile number is the first thing anyone would try
            raise StoreError("weak_password", "use some letters too, not only digits")
        if len(password) < MIN_PASSWORD or len(password) > 200:
            raise StoreError(
                "weak_password", f"a password needs at least {MIN_PASSWORD} characters"
            )
        if password.lower() in COMMON_PASSWORDS:
            raise StoreError("weak_password", "that password is too easy to guess")
        return hash_password(password, iterations=self.config.password_iterations)

    @staticmethod
    def temp_password() -> str:
        """Easy to read out or type on a phone: four groups of letters and digits."""
        alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
        return "-".join("".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3))

    def create_staff(
        self, name: str, role: str, username: str | None = None, password: str | None = None
    ) -> dict[str, Any]:
        """A new account. Without a password one is generated; it must be changed at first sign-in."""
        if role not in STAFF_ROLES:
            raise StoreError("bad_role", f"role must be one of {STAFF_ROLES}")
        if not username:  # "Rina Akter" -> "rina.akter"; a Bangla name needs a typed username
            username = re.sub(r"[^a-z0-9._-]+", ".", name.strip().lower()).strip(".")
        username = self._check_username(username)
        if self._one("SELECT 1 FROM staff WHERE username=? COLLATE NOCASE", (username,)):
            raise StoreError("taken", "that username is already used", 409)
        generated = password is None
        secret = password or self.temp_password()
        cur = self._x(
            "INSERT INTO staff(name,role,token_hash,created_at,username,password_hash,must_change) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                name.strip()[:60] or username,
                role,
                "x:" + secrets.token_hex(16),  # never matches a token: tokens are retired
                time.time(),
                username,
                self._hash(secret, username),
                1 if generated else 0,
            ),
        )
        if generated:
            self._x(
                "UPDATE staff SET temp_until=? WHERE id=?",
                (time.time() + TEMP_PASSWORD_HOURS * 3600, cur.lastrowid),
            )
        self.audit("system", "staff_created", f"{username} ({role})")
        return {
            "id": cur.lastrowid,
            "username": username,
            "password": secret if generated else None,
        }

    def set_password(
        self,
        staff_id: int,
        password: str | None = None,
        *,
        username: str | None = None,
        must_change: bool | None = None,
    ) -> str | None:
        """Set (or generate) a password; every open session of that person ends. Returns a
        generated password, shown once."""
        row = self._one("SELECT * FROM staff WHERE id=?", (staff_id,))
        if not row:
            raise StoreError("no_staff", "no such person", 404)
        generated = password is None
        secret = password or self.temp_password()
        name = row["username"]
        if (
            username or not name
        ):  # an old-token account gets a username from its name ("Old Rina" -> "old.rina")
            name = self._check_username(
                username or re.sub(r"[^a-z0-9._-]+", ".", row["name"].strip().lower()).strip(".")
            )
            clash = self._one(
                "SELECT 1 FROM staff WHERE username=? COLLATE NOCASE AND id!=?", (name, staff_id)
            )
            if clash:
                raise StoreError("taken", "that username is already used", 409)
        flag = generated if must_change is None else must_change
        self._x(
            "UPDATE staff SET username=?, password_hash=?, must_change=?, token_hash=?, temp_until=? WHERE id=?",
            (
                name,
                self._hash(secret, name),
                1 if flag else 0,
                "x:" + secrets.token_hex(16),
                time.time() + TEMP_PASSWORD_HOURS * 3600 if generated else None,
                staff_id,
            ),
        )
        self._x("DELETE FROM sessions WHERE staff_id=?", (staff_id,))
        self.audit("system", "password_set", name)
        return secret if generated else None

    def open_session(self, staff_id: int) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        self._x("DELETE FROM sessions WHERE expires_at<?", (now,))
        self._x(
            "INSERT INTO sessions(token_hash,staff_id,created_at,expires_at) VALUES (?,?,?,?)",
            (_sha(token), staff_id, now, now + self.config.session_hours * 3600),
        )
        return token

    def _locked(self, key: str) -> bool:
        now = time.time()
        recent = [t for t in self._failures.get(key, []) if now - t < LOCKOUT_SECONDS]
        self._failures[key] = recent
        return len(recent) >= MAX_FAILURES

    def sign_in(
        self, username: str, password: str, where: str = "", roles: set[str] | None = None
    ) -> dict[str, Any]:
        """A session for a correct username and password.

        Wrong tries are counted per username AND place they came from, so a stranger hammering a
        name through the tunnel locks only themselves out, not the real person on another network.
        A locked pair also refuses the right password, so guessing cannot be told from a lock.
        """
        username = username.strip().lower()[:60]
        password = unicodedata.normalize("NFC", password)
        key = f"{username}|{where}"
        if len(self._failures) > 5000:  # forget old failures rather than grow without bound
            self._failures.clear()
        bad = StoreError("bad_login", "wrong username or password", 401)
        if self._locked(key):
            raise StoreError("locked", "too many wrong tries, wait 15 minutes", 429)
        row = self._one(
            "SELECT * FROM staff WHERE username=? COLLATE NOCASE AND active=1", (username,)
        )
        ok = False
        # An account that may not sign in here (the admin, through the tunnel) is treated exactly
        # like a name that does not exist, so the public address cannot be used to test its password.
        if row is not None and roles is not None and row["role"] not in roles:
            row = None
        if (
            row is not None
            and row["must_change"]
            and row["temp_until"]
            and row["temp_until"] < time.time()
        ):
            row = None  # a one-time password that was never used has expired; the admin resets it
        if row is not None and row["password_hash"]:
            try:
                ok = verify_token(password, row["password_hash"])
            except ValueError:
                ok = False
        else:  # spend the same time on an unknown name, so names cannot be probed by timing
            verify_token(password, self._dummy_hash)
        if not ok:
            self._failures.setdefault(key, []).append(time.time())
            self.audit("staff", "sign_in_failed", username[:30])
            raise bad
        self._failures.pop(key, None)
        self.audit(row["username"], "signed_in", where)
        return {
            "token": self.open_session(row["id"]),
            "name": row["name"],
            "role": row["role"],
            "must_change": bool(row["must_change"]),
            "id": row["id"],
        }

    def change_password(self, staff: dict[str, Any], old: str, new: str) -> str:
        """The person changes their own password; other sessions end, a fresh one is returned."""
        row = self._one("SELECT * FROM staff WHERE id=?", (staff["id"],))
        try:
            ok = bool(row and row["password_hash"]) and verify_token(old, row["password_hash"])
        except ValueError:
            ok = False
        if not ok:
            raise StoreError("bad_login", "the current password is wrong", 401)
        if old == new:
            raise StoreError("weak_password", "choose a new password, not the same one")
        self.set_password(staff["id"], new, must_change=False)
        return self.open_session(staff["id"])

    def sign_out(self, token: str) -> None:
        self._x("DELETE FROM sessions WHERE token_hash=?", (_sha(token or ""),))

    def staff_for(self, token: str) -> dict[str, Any] | None:
        if not token or len(token) < 20:
            return None
        digest = _sha(token)
        row = self._one(
            "SELECT s.* FROM sessions k JOIN staff s ON s.id=k.staff_id "
            "WHERE k.token_hash=? AND k.expires_at>? AND s.active=1",
            (digest, time.time()),
        )
        if row is None:  # a first-version token, valid until its owner gets a password
            row = self._one(
                "SELECT * FROM staff WHERE token_hash=? AND active=1 AND password_hash=''",
                (digest,),
            )
        return dict(row) if row else None

    def list_staff(self) -> list[dict[str, Any]]:
        rows = self._q("SELECT * FROM staff ORDER BY id")
        return [
            {
                k: r[k]
                for k in ("id", "name", "role", "active", "created_at", "username", "must_change")
            }
            | {"has_password": bool(r["password_hash"])}
            for r in rows
        ]

    def deactivate_staff(self, staff_id: int) -> None:
        row = self._one("SELECT role, active FROM staff WHERE id=?", (staff_id,))
        if not row:
            raise StoreError("no_staff", "no such person", 404)
        if row["role"] == "admin" and row["active"]:
            others = self._one(
                "SELECT COUNT(*) n FROM staff WHERE role='admin' AND active=1 AND id!=?",
                (staff_id,),
            )
            if not others["n"]:
                raise StoreError("last_admin", "you cannot remove the last admin", 409)
        self._x("UPDATE staff SET active=0 WHERE id=?", (staff_id,))
        self._x("DELETE FROM sessions WHERE staff_id=?", (staff_id,))
        self._x("UPDATE voice_packs SET enabled=0 WHERE staff_id=?", (staff_id,))

    # ---- campaigns -----------------------------------------------------------------------
    def create_campaign(self, name: str, from_name: str = "", note: str = "") -> str:
        code = secrets.token_hex(3)
        self._x(
            "INSERT INTO campaigns(code,name,from_name,note,created_at) VALUES (?,?,?,?,?)",
            (code, name.strip()[:80], from_name.strip()[:60], note[:200], time.time()),
        )
        return code

    def campaign(self, code: str) -> dict[str, Any] | None:
        row = (
            self._one("SELECT * FROM campaigns WHERE code=? AND active=1", (code,))
            if code
            else None
        )
        return dict(row) if row else None

    def list_campaigns(self) -> list[dict[str, Any]]:
        rows = self._q(
            "SELECT c.*, (SELECT COUNT(*) FROM contributors p WHERE p.campaign=c.code AND p.deleted_at IS NULL) AS people,"
            " (SELECT COUNT(*) FROM clips k JOIN contributors p ON p.id=k.contributor_id"
            "  WHERE p.campaign=c.code AND k.deleted_at IS NULL) AS clips FROM campaigns c ORDER BY created_at DESC"
        )
        return [dict(r) for r in rows]

    # ---- contributors --------------------------------------------------------------------
    def start_contributor(
        self, *, campaign: str, from_name: str, ip: str, device: str
    ) -> dict[str, str]:
        cid = uuid.uuid4().hex
        secret = secrets.token_urlsafe(24)
        delete_code = "-".join(secrets.token_hex(2).upper() for _ in range(3))
        resolved = self.campaign(campaign)
        self._x(
            "INSERT INTO contributors(id,secret_hash,delete_hash,campaign,from_name,device,ip_hash,"
            "consent_version,consent_at,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                cid,
                _sha(secret),
                _sha(delete_code),
                resolved["code"] if resolved else "",
                (resolved or {}).get("from_name") or from_name.strip()[:40],
                device[:120],
                _sha(ip)[:16],
                self.config.consent_version,
                time.time(),
                time.time(),
            ),
        )
        speaker = self.new_speaker(cid, delete_code=delete_code)["speaker_id"]
        return {
            "contributor_id": cid,
            "secret": secret,
            "delete_code": delete_code,
            "speaker_id": speaker,
        }

    def check_contributor(self, cid: str, secret: str) -> bool:
        row = self._one(
            "SELECT secret_hash FROM contributors WHERE id=? AND deleted_at IS NULL", (cid,)
        )
        return bool(row) and hmac.compare_digest(row["secret_hash"], _sha(secret or ""))

    def set_profile(self, speaker_id: str, **fields: Any) -> None:
        """Optional details about ONE person (a shared phone has several)."""
        allowed = {"age_band", "gender", "division", "nickname", "credit_ok"}
        values = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if "credit_ok" in values:
            values["credit_ok"] = 1 if values["credit_ok"] else 0
        for key in ("age_band", "gender", "division", "nickname"):
            if key in values:
                values[key] = str(values[key]).strip()[:40]
        if not values:
            return
        sets = ",".join(f"{k}=?" for k in values)
        self._x(f"UPDATE speakers SET {sets} WHERE id=?", (*values.values(), speaker_id))

    def new_speaker(self, cid: str, label: str = "", delete_code: str = "") -> dict[str, str]:
        """A person on a phone. Each person has their own delete code, so one family member cannot
        erase another's recordings."""
        sid = uuid.uuid4().hex
        code = delete_code or "-".join(secrets.token_hex(2).upper() for _ in range(3))
        draw = _fraction(sid)
        split = (
            "test"
            if draw < self.config.test_fraction
            else "dev"
            if draw < self.config.test_fraction + self.config.dev_fraction
            else "train"
        )
        self._x(
            "INSERT INTO speakers(id,contributor_id,label,split,created_at,delete_hash) VALUES (?,?,?,?,?,?)",
            (sid, cid, label.strip()[:30], split, time.time(), _sha(code)),
        )
        return {"speaker_id": sid, "delete_code": code}

    def speaker(self, sid: str, cid: str) -> dict[str, Any] | None:
        row = self._one(
            "SELECT * FROM speakers WHERE id=? AND contributor_id=? AND deleted_at IS NULL",
            (sid, cid),
        )
        return dict(row) if row else None

    def clips_today(self, cid: str) -> int:
        row = self._one(
            "SELECT COUNT(*) n FROM clips WHERE contributor_id=? AND created_at>?",
            (cid, time.time() - 86400),
        )
        return int(row["n"])

    # ---- clips ---------------------------------------------------------------------------
    def tombstoned(self, clip_id: str, sha: str) -> bool:
        return bool(
            self._one("SELECT 1 FROM tombstones WHERE clip_id=? OR sha256=?", (clip_id, sha))
        )

    def add_clip(
        self,
        *,
        clip_id: str,
        speaker: dict[str, Any],
        cid: str,
        meta: dict[str, Any],
        quality: Any,
        data: bytes,
        ext: str,
        ua: str,
    ) -> dict[str, Any]:
        existing = self._one("SELECT id,sha256 FROM clips WHERE id=?", (clip_id,))
        sha = hashlib.sha256(data).hexdigest()
        if existing:  # the phone retried; the clip is already safe
            return {"clip_id": clip_id, "duplicate": True}
        if self.tombstoned(clip_id, sha):
            raise StoreError("withdrawn", "this recording was deleted earlier", 410)
        path = self.audio.save(clip_id, ext, data)
        try:
            self._x(
                "INSERT INTO clips(id,speaker_id,contributor_id,card_id,step_id,slot,kind,question_bn,expected_text,"
                "facts,setting,room,role,turn,split,duration_s,rms_db,peak,clip_fraction,speech_ratio,snr_db,codec,"
                "bytes,sha256,path,ua,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    clip_id,
                    speaker["id"],
                    cid,
                    meta.get("card_id", ""),
                    meta.get("step_id", ""),
                    meta.get("slot", ""),
                    meta.get("kind", ""),
                    meta.get("question_bn", ""),
                    meta.get("expected_text"),
                    json.dumps(meta.get("facts") or {}, ensure_ascii=False),
                    meta.get("setting", ""),
                    meta.get("room", ""),
                    meta.get("role", ""),
                    _small_int(meta.get("turn")),
                    speaker["split"],
                    quality.duration_s,
                    quality.rms_db,
                    quality.peak,
                    quality.clip_fraction,
                    quality.speech_ratio,
                    quality.snr_db,
                    quality.codec,
                    len(data),
                    sha,
                    str(path),
                    ua[:160],
                    time.time(),
                ),
            )
        except Exception:
            self.audio.delete(str(path))
            raise
        return {"clip_id": clip_id, "duplicate": False}

    def get_clip(self, clip_id: str) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM clips WHERE id=? AND deleted_at IS NULL", (clip_id,))
        return dict(row) if row else None

    def set_draft(self, clip_id: str, text: str) -> None:
        self._x("UPDATE clips SET draft_text=? WHERE id=?", (text, clip_id))

    def undrafted(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = self._q(
            "SELECT id,path FROM clips WHERE draft_text IS NULL AND deleted_at IS NULL "
            "AND status!='rejected' ORDER BY created_at LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in rows]

    def room_clips(self, code: str) -> list[dict[str, Any]]:
        rows = self._q(
            "SELECT id,role,turn,slot,duration_s,created_at FROM clips WHERE room=? "
            "AND deleted_at IS NULL ORDER BY turn,created_at",
            (code,),
        )
        return [dict(r) for r in rows]

    # ---- deletion ------------------------------------------------------------------------
    def delete_by_code(self, delete_code: str) -> int:
        """Remove every clip of the person who holds this code and leave tombstones.
        Returns the number of clips deleted."""
        row = self._one(
            "SELECT id, contributor_id FROM speakers WHERE delete_hash=? AND deleted_at IS NULL",
            (_sha(delete_code.strip().upper()),),
        )
        if not row:
            raise StoreError("unknown_code", "that delete code was not found", 404)
        return self._erase_speaker(row["id"], row["contributor_id"], "withdrawn by contributor")

    delete_contributor = delete_by_code  # the first name of this method; kept for callers

    def _erase_speaker(self, sid: str, cid: str, reason: str) -> int:
        clips = self._q(
            "SELECT id,sha256,path FROM clips WHERE speaker_id=? AND deleted_at IS NULL", (sid,)
        )
        now = time.time()
        for clip in clips:
            self.audio.delete(clip["path"])
            self._x(
                "INSERT OR REPLACE INTO tombstones(clip_id,sha256,reason,at) VALUES (?,?,?,?)",
                (clip["id"], clip["sha256"], reason, now),
            )
            self._x("DELETE FROM reviews WHERE clip_id=?", (clip["id"],))
            self._x(
                "UPDATE clips SET deleted_at=?, draft_text=NULL, final_text=NULL, status='withdrawn', "
                "path='', question_bn='', facts='{}' WHERE id=?",
                (now, clip["id"]),
            )
        self._x(
            "UPDATE speakers SET deleted_at=?, nickname='', age_band='', gender='', division='', credit_ok=0 "
            "WHERE id=?",
            (now, sid),
        )
        if not self._one(
            "SELECT 1 FROM speakers WHERE contributor_id=? AND deleted_at IS NULL", (cid,)
        ):
            self._x("UPDATE contributors SET deleted_at=?, device='' WHERE id=?", (now, cid))
        self.audit("contributor", "withdrawn", f"{len(clips)} clips")
        return len(clips)

    def remove_clip(self, clip_id: str, actor: str, reason: str) -> bool:
        clip = self.get_clip(clip_id)
        if not clip:
            return False
        self.audio.delete(clip["path"])
        self._x(
            "INSERT OR REPLACE INTO tombstones(clip_id,sha256,reason,at) VALUES (?,?,?,?)",
            (clip_id, clip["sha256"], reason, time.time()),
        )
        self._x(
            "UPDATE clips SET deleted_at=?, status='removed', path='', final_text=NULL WHERE id=?",
            (time.time(), clip_id),
        )
        self.audit(actor, "clip_removed", f"{clip_id}: {reason}")
        return True

    # ---- review --------------------------------------------------------------------------
    def next_for_review(
        self, staff: dict[str, Any], rng_value: float | None = None
    ) -> dict[str, Any] | None:
        sid = staff["id"]
        rolled = rng_value if rng_value is not None else secrets.randbelow(10_000) / 10_000
        done = "SELECT clip_id FROM reviews WHERE staff_id=?"
        base = "deleted_at IS NULL AND status NOT IN ('rejected','withdrawn','removed')"
        if staff["role"] in ("admin", "adjudicator"):
            row = self._one(
                f"SELECT * FROM clips WHERE {base} AND status='disputed' AND id NOT IN ({done}) "
                "ORDER BY created_at LIMIT 1",
                (sid,),
            )
            if row:
                return self._queue_item(dict(row), "adjudicate")
        if rolled < self.config.seed_fraction:
            row = self._one(
                f"SELECT * FROM clips WHERE {base} AND status IN ('agreed','adjudicated') AND id NOT IN ({done}) "
                "ORDER BY RANDOM() LIMIT 1",
                (sid,),
            )
            if row:
                return self._queue_item(dict(row), "seed")
        row = self._one(
            f"SELECT c.* FROM clips c WHERE {base} AND c.split='test' AND c.status IN ('pending','single') "
            f"AND c.id NOT IN ({done}) AND (SELECT COUNT(*) FROM reviews r WHERE r.clip_id=c.id AND r.kind IN ('blind','verify'))<2 "
            "ORDER BY c.created_at LIMIT 1",
            (sid,),
        )
        if row:
            return self._queue_item(dict(row), "blind")
        row = self._one(
            f"SELECT * FROM clips WHERE {base} AND split IN ('train','dev') AND status='pending' "
            f"AND id NOT IN ({done}) ORDER BY created_at LIMIT 1",
            (sid,),
        )
        if row:
            mode = "verify" if row["expected_text"] else "draft"
            return self._queue_item(dict(row), mode)
        return None

    def _queue_item(self, clip: dict[str, Any], mode: str) -> dict[str, Any]:
        hide_draft = (
            mode != "draft"
        )  # a draft anchors reviewers, so only the one mode that wants it sees it
        item = {
            "clip_id": clip["id"],
            "mode": mode,
            "slot": clip["slot"],
            "kind": clip["kind"],
            "question_bn": clip["question_bn"],
            "duration_s": round(clip["duration_s"], 1),
            "split": clip["split"],
            "setting": clip["setting"],
            "draft": None if hide_draft else clip["draft_text"],
            "expected": clip["expected_text"] if mode == "verify" else None,
        }
        if mode == "adjudicate":
            item["candidates"] = [
                {"text": r["text"], "flags": json.loads(r["flags"])}
                for r in self._q(
                    "SELECT text,flags FROM reviews WHERE clip_id=? AND kind IN ('blind','verify','draft')",
                    (clip["id"],),
                )
            ]
        return item

    def submit_review(
        self,
        staff: dict[str, Any],
        clip_id: str,
        text: str,
        flags: list[str],
        seconds: float | None,
    ) -> dict[str, Any]:
        clip = self.get_clip(clip_id)
        if not clip:
            raise StoreError("no_clip", "that recording is gone", 404)
        flags = [f for f in dict.fromkeys(flags) if f in REJECT_FLAGS | {"noisy", "unclear"}]
        rejecting = bool(set(flags) & REJECT_FLAGS)
        mode = self._mode_for(clip, staff)
        if (
            self._one(
                "SELECT 1 FROM reviews WHERE clip_id=? AND staff_id=? AND kind!='seed'",
                (clip_id, staff["id"]),
            )
            and mode != "seed"
        ):
            raise StoreError("already", "you already reviewed this recording", 409)
        cleaned, notes = T.clean_transcript(text or "")
        if not rejecting:
            if not cleaned:
                raise StoreError("empty", "type what was said, or flag the clip")
            if not T.has_bangla(cleaned) and not cleaned.isdigit():
                raise StoreError(
                    "no_bangla", "write the words in Bangla script, or flag it as another language"
                )
        if mode == "seed":
            truth = clip["final_text"] or ""
            self._x(
                "INSERT INTO seed_checks(staff_id,clip_id,cer,at) VALUES (?,?,?,?)",
                (staff["id"], clip_id, T.cer(truth, cleaned), time.time()),
            )
            self._x(
                "INSERT INTO reviews(clip_id,staff_id,kind,text,flags,seconds,created_at) VALUES (?,?,?,?,?,?,?)",
                (clip_id, staff["id"], "seed", cleaned, json.dumps(flags), seconds, time.time()),
            )
            return {"ok": True, "text": cleaned, "notes": notes, "status": clip["status"]}
        self._x(
            "INSERT INTO reviews(clip_id,staff_id,kind,text,flags,seconds,created_at) VALUES (?,?,?,?,?,?,?)",
            (clip_id, staff["id"], mode, cleaned, json.dumps(flags), seconds, time.time()),
        )
        status = self._resolve(
            clip_id, adjudicator=staff["role"] in ("admin", "adjudicator") and mode == "adjudicate"
        )
        return {"ok": True, "text": cleaned, "notes": notes, "status": status}

    def _mode_for(self, clip: dict[str, Any], staff: dict[str, Any]) -> str:
        if clip["status"] == "disputed" and staff["role"] in ("admin", "adjudicator"):
            return "adjudicate"
        if clip["status"] in ("agreed", "adjudicated"):
            return "seed"
        if clip["split"] == "test":
            return "blind"
        return "verify" if clip["expected_text"] else "draft"

    def _resolve(self, clip_id: str, adjudicator: bool = False) -> str:
        clip = self.get_clip(clip_id)
        reviews = [
            dict(r)
            for r in self._q(
                "SELECT * FROM reviews WHERE clip_id=? AND kind!='seed' ORDER BY id", (clip_id,)
            )
        ]
        flagged = [r for r in reviews if set(json.loads(r["flags"])) & REJECT_FLAGS]
        status, final = "pending", None
        if flagged:
            status = "rejected"
        elif adjudicator:
            final = [r for r in reviews if r["kind"] == "adjudicate"][-1]["text"]
            status = "adjudicated"
        else:
            texts = [r["text"] for r in reviews if r["kind"] != "adjudicate"]
            if clip["split"] == "test":
                if len(texts) >= 2:
                    agree = T.same_text(texts[0], texts[1])
                    status, final = ("agreed", texts[0]) if agree else ("disputed", None)
                elif texts:
                    status = "single"
            elif texts:
                if len(texts) >= 2 and not T.same_text(texts[0], texts[1]):
                    status = "disputed"
                else:
                    status, final = "single" if len(texts) == 1 else "agreed", texts[0]
        self._x("UPDATE clips SET status=?, final_text=? WHERE id=?", (status, final, clip_id))
        return status

    # ---- voice packs: a named staff member records the desk's lines in their own voice --------
    def voice_pack(self, staff_id: int) -> dict[str, Any]:
        row = self._one("SELECT * FROM voice_packs WHERE staff_id=?", (staff_id,))
        if not row:
            self._x(
                "INSERT INTO voice_packs(staff_id,public_id,created_at) VALUES (?,?,?)",
                (staff_id, secrets.token_hex(16), time.time()),
            )
            row = self._one("SELECT * FROM voice_packs WHERE staff_id=?", (staff_id,))
        return dict(row)

    def voice_consent(self, staff_id: int) -> None:
        self.voice_pack(staff_id)
        self._x("UPDATE voice_packs SET consent_at=? WHERE staff_id=?", (time.time(), staff_id))
        self.audit(str(staff_id), "voice_consent", "")

    def voice_names(self, staff_id: int) -> set[str]:
        return {
            r["name"] for r in self._q("SELECT name FROM voice_lines WHERE staff_id=?", (staff_id,))
        }

    def save_voice_line(self, staff_id: int, name: str, data: bytes, duration_s: float) -> None:
        pack = self.voice_pack(staff_id)
        if not pack["consent_at"]:
            raise StoreError("consent", "agree to the voice notice first", 403)
        folder = self.config.data_dir / "voices" / pack["public_id"]
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{name}.m4a"
        path.write_bytes(data)
        self._x(
            "INSERT INTO voice_lines(staff_id,name,path,duration_s,created_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(staff_id,name) DO UPDATE SET path=excluded.path, duration_s=excluded.duration_s, "
            "created_at=excluded.created_at",
            (staff_id, name, str(path), duration_s, time.time()),
        )

    def voice_line_path(self, staff_id: int, name: str) -> Path | None:
        row = self._one(
            "SELECT path FROM voice_lines WHERE staff_id=? AND name=?", (staff_id, name)
        )
        return Path(row["path"]) if row and Path(row["path"]).exists() else None

    def delete_voice_lines(self, staff_id: int, name: str | None = None) -> int:
        """Remove one line, or the whole pack (it also stops being played at once)."""
        rows = self._q(
            "SELECT name,path FROM voice_lines WHERE staff_id=?" + (" AND name=?" if name else ""),
            (staff_id, name) if name else (staff_id,),
        )
        for r in rows:
            Path(r["path"]).unlink(missing_ok=True)
            self._x("DELETE FROM voice_lines WHERE staff_id=? AND name=?", (staff_id, r["name"]))
        if not name:
            self._x("UPDATE voice_packs SET enabled=0 WHERE staff_id=?", (staff_id,))
        return len(rows)

    def set_pack_enabled(self, staff_id: int, enabled: bool, actor: str) -> None:
        row = self._one("SELECT consent_at FROM voice_packs WHERE staff_id=?", (staff_id,))
        if enabled and not (row and row["consent_at"]):  # do not create an empty pack on a refusal
            raise StoreError("consent", "this person has not agreed to the voice notice", 409)
        self._x(
            "UPDATE voice_packs SET enabled=? WHERE staff_id=?", (1 if enabled else 0, staff_id)
        )
        self.audit(actor, "voice_pack_enabled" if enabled else "voice_pack_disabled", str(staff_id))

    def voice_packs(self) -> list[dict[str, Any]]:
        rows = self._q(
            "SELECT p.staff_id, p.public_id, p.enabled, p.consent_at, s.name, s.active, "
            "(SELECT COUNT(*) FROM voice_lines l WHERE l.staff_id=p.staff_id) lines "
            "FROM voice_packs p JOIN staff s ON s.id=p.staff_id ORDER BY p.staff_id"
        )
        return [dict(r) for r in rows]

    def playable_packs(self) -> list[dict[str, Any]]:
        """Packs the public page may play: enabled by the admin, owner still active, consent given."""
        return [
            {
                "public_id": p["public_id"],
                "names": self.voice_names(p["staff_id"]),
                "staff_id": p["staff_id"],
            }
            for p in self.voice_packs()
            if p["enabled"] and p["active"] and p["consent_at"] and p["lines"]
        ]

    def pack_by_public_id(self, public_id: str) -> dict[str, Any] | None:
        row = self._one(
            "SELECT p.* FROM voice_packs p JOIN staff s ON s.id=p.staff_id "
            "WHERE p.public_id=? AND p.enabled=1 AND s.active=1",
            (public_id,),
        )
        return dict(row) if row else None

    def restore_clip(self, clip_id: str, actor: str) -> bool:
        """Undo a rejection (one reviewer's flag is enough to reject, so the admin can reverse it)."""
        clip = self.get_clip(clip_id)
        if not clip or clip["status"] != "rejected":
            return False
        for r in self._q("SELECT id, flags FROM reviews WHERE clip_id=?", (clip_id,)):
            if set(json.loads(r["flags"])) & REJECT_FLAGS:
                self._x("DELETE FROM reviews WHERE id=?", (r["id"],))
        self._resolve(clip_id)
        self.audit(actor, "clip_restored", clip_id)
        return True

    def reviewer_report(self) -> list[dict[str, Any]]:
        rows = self._q(
            "SELECT s.id, s.name, s.role, s.active, COUNT(r.id) reviews, "
            "(SELECT AVG(cer) FROM seed_checks k WHERE k.staff_id=s.id) seed_cer, "
            "(SELECT COUNT(*) FROM seed_checks k WHERE k.staff_id=s.id) seeds "
            "FROM staff s LEFT JOIN reviews r ON r.staff_id=s.id GROUP BY s.id ORDER BY s.id"
        )
        return [dict(r) for r in rows]

    # ---- rooms (call a friend) -----------------------------------------------------------
    def create_room(self, cid: str, card_id: str) -> str:
        code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
        self._x(
            "INSERT INTO rooms(code,card_id,caller_cid,created_at) VALUES (?,?,?,?)",
            (code, card_id, cid, time.time()),
        )
        return code

    def join_room(self, code: str, cid: str) -> dict[str, Any]:
        room = self._one("SELECT * FROM rooms WHERE code=?", (code.upper(),))
        if not room:
            raise StoreError("no_room", "no such room", 404)
        room = dict(room)
        if cid in (room["caller_cid"], room["desk_cid"]):
            return room
        if time.time() - room["created_at"] > ROOM_JOIN_HOURS * 3600:
            raise StoreError("no_room", "no such room", 404)
        if room["desk_cid"]:
            raise StoreError("room_full", "this room already has two people", 409)
        self._x("UPDATE rooms SET desk_cid=?, state='active' WHERE code=?", (cid, code.upper()))
        room["desk_cid"], room["state"] = cid, "active"
        return room

    def get_room(self, code: str) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM rooms WHERE code=?", (code.upper(),))
        return dict(row) if row else None

    # ---- numbers -------------------------------------------------------------------------
    def progress(self) -> dict[str, Any]:
        row = self._one(
            "SELECT COUNT(*) clips, COALESCE(SUM(duration_s),0) secs, COUNT(DISTINCT speaker_id) speakers "
            "FROM clips WHERE deleted_at IS NULL AND status NOT IN ('rejected','removed')"
        )
        goal = int(self.get_setting("goal_minutes", str(self.config.group_goal_minutes)))
        return {
            "clips": row["clips"],
            "minutes": round(row["secs"] / 60, 1),
            "speakers": row["speakers"],
            "goal_minutes": goal,
        }

    def thanks(self, limit: int = 60) -> list[str]:
        rows = self._q(
            "SELECT nickname FROM speakers WHERE credit_ok=1 AND nickname!='' AND deleted_at IS NULL "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [r["nickname"] for r in rows]

    def stats(self) -> dict[str, Any]:
        def group(column: str) -> dict[str, int]:
            """People by a profile field, counted as speakers (pass-the-phone makes several per phone)."""
            rows = self._q(
                f"SELECT {column} k, COUNT(*) n FROM speakers WHERE deleted_at IS NULL GROUP BY {column}"
            )
            return {(r["k"] or "unknown"): r["n"] for r in rows}

        def clip_group(column: str) -> dict[str, float]:
            rows = self._q(
                f"SELECT {column} k, ROUND(SUM(duration_s)/60.0,1) m FROM clips WHERE deleted_at IS NULL "
                f"AND status NOT IN ('rejected','removed') GROUP BY {column}"
            )
            return {(r["k"] or "unknown"): r["m"] for r in rows}

        status = {
            r["status"]: r["n"]
            for r in self._q(
                "SELECT status, COUNT(*) n FROM clips WHERE deleted_at IS NULL GROUP BY status"
            )
        }
        split = {
            r["split"]: r["n"]
            for r in self._q(
                "SELECT split, COUNT(*) n FROM clips WHERE deleted_at IS NULL AND status NOT IN ('rejected','removed') GROUP BY split"
            )
        }
        speakers = self._one(
            "SELECT COUNT(*) n FROM speakers s JOIN contributors c ON c.id=s.contributor_id "
            "WHERE c.deleted_at IS NULL AND EXISTS (SELECT 1 FROM clips k WHERE k.speaker_id=s.id "
            "AND k.deleted_at IS NULL)"
        )["n"]
        return {
            "progress": self.progress(),
            "speakers_with_clips": speakers,
            "contributors": self._one(
                "SELECT COUNT(*) n FROM contributors WHERE deleted_at IS NULL"
            )["n"],
            "status": status,
            "split": split,
            "minutes_by_slot": clip_group("slot"),
            "minutes_by_setting": clip_group("setting"),
            "by_division": group("division"),
            "by_age": group("age_band"),
            "by_gender": group("gender"),
            "disk_free_mb": self.audio.free_mb(),
            "min_free_disk_mb": self.config.min_free_disk_mb,
            "kill_switch": self.get_setting("kill_switch") == "1",
        }

    def clip_rows(
        self, status: str = "", limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        sql = (
            "SELECT id,speaker_id,card_id,kind,slot,split,duration_s,snr_db,speech_ratio,status,final_text,draft_text,"
            "created_at FROM clips WHERE deleted_at IS NULL"
        )
        args: list[Any] = []
        if status:
            sql += " AND status=?"
            args.append(status)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        return [dict(r) for r in self._q(sql, (*args, limit, offset))]

    def close(self) -> None:
        with self._lock:
            self.db.close()
