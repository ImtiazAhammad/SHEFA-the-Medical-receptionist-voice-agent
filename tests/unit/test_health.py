from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import httpx
import pytest

from shefa import health
from shefa.config.settings import TelephonyProvider, settings
from shefa.telephony import asterisk

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import backup_db  # noqa: E402


async def test_healthy_when_twilio_is_selected(monkeypatch):
    monkeypatch.setattr(settings.telephony, "provider", TelephonyProvider.TWILIO)
    report = await health.health_report()
    assert report["status"] == "healthy" and report["asterisk"] == "n/a"
    assert report["database"] == "ok"


def _ari(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(
        asterisk,
        "client_factory",
        lambda: httpx.AsyncClient(base_url="http://ari.test/ari", transport=transport),
    )


async def test_degraded_when_ari_is_unreachable(monkeypatch):
    monkeypatch.setattr(settings.telephony, "provider", TelephonyProvider.ASTERISK)

    def down(request):
        raise httpx.ConnectError("refused")

    _ari(monkeypatch, down)
    report = await health.health_report()
    assert report["status"] == "degraded" and report["asterisk"] == "unreachable"


async def test_healthy_when_ari_answers(monkeypatch):
    monkeypatch.setattr(settings.telephony, "provider", TelephonyProvider.ASTERISK)
    _ari(monkeypatch, lambda request: httpx.Response(200, json={}))
    assert (await health.health_report())["asterisk"] == "ok"


async def test_degraded_when_the_database_fails(monkeypatch):
    class Broken:
        class connection:  # noqa: N801
            @staticmethod
            def execute(*args):
                raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr("shefa.clinic.default_clinic_store", lambda: Broken)
    monkeypatch.setattr(settings.telephony, "provider", TelephonyProvider.TWILIO)
    report = await health.health_report()
    assert report["status"] == "degraded" and report["database"] == "error"


def test_backup_copies_a_live_wal_database_and_prunes(tmp_path):
    db = tmp_path / "shefa.db"
    connection = sqlite3.connect(db)
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("CREATE TABLE t (x)")
    connection.execute("INSERT INTO t VALUES (42)")
    connection.commit()  # connection stays open, like a running server

    out = tmp_path / "backups"
    for stamp in ("20200101-000000", "20200102-000000", "20200103-000000"):
        out.mkdir(exist_ok=True)
        (out / f"shefa-{stamp}.db").write_bytes(b"old")
    target = backup_db.backup(db, out, keep=2)

    assert sqlite3.connect(target).execute("SELECT x FROM t").fetchone() == (42,)
    kept = sorted(p.name for p in out.glob("shefa-*.db"))
    assert len(kept) == 2 and target.name in kept
    connection.close()


def test_backup_refuses_a_missing_database(tmp_path):
    with pytest.raises(FileNotFoundError):
        backup_db.backup(tmp_path / "nope.db", tmp_path / "out", 3)


def test_backup_main_runs(tmp_path, monkeypatch, capsys):
    db = tmp_path / "shefa.db"
    sqlite3.connect(db).execute("CREATE TABLE t (x)").connection.close()
    monkeypatch.setattr(sys, "argv", ["backup", "--db", str(db), "--out", str(tmp_path / "b")])
    backup_db.main()
    assert "backed up to" in capsys.readouterr().out
