"""What patients say is unreadable in the database file without the key."""

from __future__ import annotations

import sqlite3
import stat

import pytest
from cryptography.fernet import Fernet

from shefa.call_log import call_started, default_calls_store, log_turn
from shefa.store.crypt import PREFIX, UNREADABLE, DataCipher, load_or_create_key, set_default_cipher


def raw_rows(table: str) -> list[tuple]:
    path = default_calls_store().path
    connection = sqlite3.connect(path)
    try:
        return connection.execute(f"SELECT * FROM {table}").fetchall()  # noqa: S608
    finally:
        connection.close()


def test_a_transcript_is_noise_on_disk_and_words_through_the_store():
    call_started("CA1", "inbound")
    log_turn("CA1", "user", "my name is Karim and my number is 01711000123", note="heard")

    on_disk = str(raw_rows("call_turns"))
    assert "Karim" not in on_disk and "01711000123" not in on_disk and PREFIX in on_disk
    (turn,) = default_calls_store().turns_for("CA1")
    assert turn["text"] == "my name is Karim and my number is 01711000123"
    assert turn["note"] == "heard"


def test_call_back_numbers_and_reasons_are_encrypted_too():
    default_calls_store().add_callback("CA1", "01711000123", "bn", "asked for Dr Rahman")

    assert "01711000123" not in str(raw_rows("callbacks"))
    (row,) = default_calls_store().list_callbacks()
    assert row["phone"] == "01711000123" and row["reason"] == "asked for Dr Rahman"


def test_rows_written_before_encryption_stay_readable():
    call_started("CA2", "inbound")
    store = default_calls_store()
    with store.connection:
        store.connection.execute(
            "INSERT INTO call_turns (call_sid, idx, at, role, text)"
            " VALUES ('CA2', 0, 0, 'user', 'old plain words')"
        )
    assert store.turns_for("CA2")[0]["text"] == "old plain words"


def test_a_different_key_cannot_read_and_does_not_crash():
    call_started("CA3", "inbound")
    log_turn("CA3", "user", "secret")
    set_default_cipher(DataCipher(Fernet.generate_key()))  # a different key

    assert default_calls_store().turns_for("CA3")[0]["text"] == UNREADABLE


def test_switching_encryption_off_keeps_old_rows_readable_and_writes_new_ones_plain():
    from shefa.store.crypt import default_cipher

    call_started("CA4", "inbound")
    log_turn("CA4", "user", "while encrypted")
    key = default_cipher()._fernet  # the same key, with writing switched off
    set_default_cipher(DataCipher.__new__(DataCipher))
    off = DataCipher(Fernet.generate_key(), enabled=False)
    off._fernet = key
    set_default_cipher(off)

    log_turn("CA4", "user", "while plain")

    assert "while plain" in str(raw_rows("call_turns"))
    assert [t["text"] for t in default_calls_store().turns_for("CA4")] == [
        "while encrypted",
        "while plain",
    ]


def test_the_key_file_is_created_private_and_reused(tmp_path, monkeypatch):
    monkeypatch.delenv("SHEFA_DATA_KEY", raising=False)
    path = tmp_path / "nested" / "data.key"

    first = load_or_create_key(path)
    second = load_or_create_key(path)

    assert first == second and stat.S_IMODE(path.stat().st_mode) == 0o600


def test_the_environment_key_wins_over_the_file(tmp_path, monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setenv("SHEFA_DATA_KEY", key)
    assert load_or_create_key(tmp_path / "unused.key") == key.encode()
    assert not (tmp_path / "unused.key").exists()


@pytest.fixture(autouse=True)
def _fresh_cipher():
    set_default_cipher(None)
    yield
    set_default_cipher(None)
