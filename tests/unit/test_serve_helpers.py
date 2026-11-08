"""`shefa serve` should need no preparation: it loads doctors and quiets the polling noise."""

from __future__ import annotations

import logging

from shefa import cli
from shefa.clinic import default_clinic_store


def test_a_fresh_install_gets_the_sample_clinic(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "clinic.example.yaml").write_text(
        "departments:\n  - name: Cardiology\n    doctors:\n      - name: Rahman\n"
    )
    assert default_clinic_store().doctors() == []

    cli._ensure_directory()

    assert [d["name_en"] for d in default_clinic_store().doctors()] == ["Rahman"]
    assert "Loaded 1 doctors" in capsys.readouterr().out
    cli._ensure_directory()  # a second start leaves it alone
    assert len(default_clinic_store().doctors()) == 1


def test_the_ringing_poll_is_not_logged_but_other_requests_are():
    quiet = cli._QuietPolling()

    def record(path: str) -> logging.LogRecord:
        return logging.LogRecord("uvicorn.access", 20, "", 0, f"GET {path} HTTP/1.1", None, None)

    assert not quiet.filter(record("/api/v1/calls/ringing"))
    assert quiet.filter(record("/api/v1/chat"))
