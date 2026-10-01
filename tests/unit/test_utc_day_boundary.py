"""Regression test: a UTC-day boundary must not depend on the local clock.

`date(ts,'unixepoch','utc')` double-applies the timezone: 'unixepoch' already
yields UTC, so the trailing 'utc' shifts the result back by the local offset.
In UTC+6 that misfiles every row between 00:00 and 06:00 UTC onto the previous
day — so `count_for_day(utc_day())` returns 0 for six hours every morning, and
the zero-log alert fires for a day that has rows.

The tests passed at 09:25 local and failed at 03:25 local purely because of
the clock, which is exactly the class of bug a same-day test run cannot catch.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from sefa.store.audit import AuditStore
from sefa.store.calls import CallsStore

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@pytest.fixture
def audit(tmp_path) -> AuditStore:
    store = AuditStore(tmp_path / "sefa.db")
    yield store
    store.close()


def _ts(hour: int) -> float:
    """Unix time for `hour`:00 UTC on a fixed day."""
    return (datetime(2026, 10, 1, hour, 30, tzinfo=UTC) - EPOCH).total_seconds()


@pytest.mark.parametrize("hour", range(24))
def test_audit_rows_land_on_their_own_utc_day_at_every_hour(audit, hour):
    """`count_for_day` must agree with UTC at 00:00, not just at midday."""
    audit.append("call_started", call_sid="CA-x", ts=_ts(hour))
    assert audit.count_for_day("2026-10-01") == 1, f"misfiled at {hour:02d}:00 UTC"


@pytest.mark.parametrize("hour", range(24))
def test_call_rows_land_on_their_own_utc_day_at_every_hour(tmp_path, hour):
    calls = CallsStore(tmp_path / "calls.db")
    calls.upsert_call({"call_sid": "CA-x", "created_at": _ts(hour)})
    assert calls.count_for_day("2026-10-01") == 1, f"misfiled at {hour:02d}:00 UTC"


def test_the_local_timezone_does_not_shift_the_day_boundary(monkeypatch, audit):
    """A UTC+6 machine and a UTC-5 machine must agree on the day."""
    row = _ts(2)  # 02:00 UTC — the hour that breaks in UTC+6
    audit.append("call_started", call_sid="CA-x", ts=row)

    for tz_offset in (6, -5, 13):
        monkeypatch.setenv("TZ", f"Etc/GMT{-tz_offset if tz_offset < 0 else tz_offset}")
        assert audit.count_for_day("2026-10-01") == 1, f"broken at UTC{tz_offset:+d}"
