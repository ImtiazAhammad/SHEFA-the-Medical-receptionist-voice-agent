# ruff: noqa: E501
"""The owner's weekly report: what SHEFA did for the clinic, in numbers the owner can check.

This is what a buyer pays for, so every number is a count of real rows, never a guess, and the
one estimate (staff minutes saved) is labelled as one. Test traffic (the nightly self-test call,
`direction = 'test'`, and its bookings, `source = 'test'`) is never counted.

"After hours" means outside the desk's own hours, a clinic setting (`desk_hours`, default
09:00-21:00, every day): a call or booking then is one the clinic would otherwise have missed.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from shefa.clinic.store import CLINIC_TZ

DEFAULT_DESK_HOURS = "09:00-21:00"
MINUTES_PER_PHONE_BOOKING = 3  # the desk's time per booking call: an estimate, said as one


def _bounds(end: date, days: int) -> tuple[float, float, str, str]:
    start = end - timedelta(days=days - 1)
    t0 = datetime.combine(start, datetime.min.time(), CLINIC_TZ).timestamp()
    t1 = datetime.combine(end + timedelta(days=1), datetime.min.time(), CLINIC_TZ).timestamp()
    return t0, t1, start.isoformat(), end.isoformat()


def _desk_hours(clinic: Any) -> tuple[int, int]:
    raw = clinic.setting("desk_hours", DEFAULT_DESK_HOURS) or DEFAULT_DESK_HOURS
    try:
        a, b = raw.split("-")
        h1, m1 = (int(x) for x in a.strip().split(":"))
        h2, m2 = (int(x) for x in b.strip().split(":"))
        return h1 * 60 + m1, h2 * 60 + m2
    except ValueError:
        return 9 * 60, 21 * 60


def _after_hours(stamp: float, hours: tuple[int, int]) -> bool:
    local = datetime.fromtimestamp(stamp, CLINIC_TZ)
    minute = local.hour * 60 + local.minute
    return not hours[0] <= minute < hours[1]


def weekly_report(
    clinic: Any, calls: Any, *, end: date | None = None, days: int = 7
) -> dict[str, Any]:
    end = end or datetime.now(CLINIC_TZ).date()
    days = max(1, min(days, 31))
    t0, t1, first, last = _bounds(end, days)
    hours = _desk_hours(clinic)
    q = clinic.connection.execute

    call_rows = calls.connection.execute(
        "SELECT direction, disposition, started_at FROM calls WHERE started_at >= ? AND"
        " started_at < ? AND deleted_at IS NULL AND COALESCE(direction, '') != 'test'",
        (t0, t1),
    ).fetchall()
    inbound = [r for r in call_rows if r["direction"] == "inbound"]
    handed = sum(1 for r in call_rows if r["disposition"] == "handed_over")
    turned_away = sum(1 for r in call_rows if r["disposition"] == "turned_away")

    made = q(
        "SELECT source, created_at FROM appointments WHERE created_at >= ? AND created_at < ?"
        " AND source != 'test'",
        (t0, t1),
    ).fetchall()
    by_source: dict[str, int] = {}
    for r in made:
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
    shefa_made = [r for r in made if r["source"] in ("phone", "web")]
    after_hours_bookings = sum(1 for r in shefa_made if _after_hours(r["created_at"], hours))

    outcome = {
        r["status"]: r["n"]
        for r in q(
            "SELECT status, COUNT(*) AS n FROM appointments WHERE date >= ? AND date <= ?"
            " AND source != 'test' GROUP BY status",
            (first, last),
        )
    }
    seen = outcome.get("completed", 0) + outcome.get("no_show", 0)

    sms = {
        r["status"]: r["n"]
        for r in q(
            "SELECT status, COUNT(*) AS n FROM messages WHERE created_at >= ? AND created_at < ?"
            " GROUP BY status",
            (t0, t1),
        )
    }
    missed = {
        r["status"]: r["n"]
        for r in q(
            "SELECT status, COUNT(*) AS n FROM missed_calls WHERE missed_at >= ? AND missed_at < ?"
            " GROUP BY status",
            (t0, t1),
        )
    }
    callbacks = calls.connection.execute(
        "SELECT COUNT(*) AS opened, SUM(resolved_at IS NOT NULL) AS resolved FROM callbacks"
        " WHERE created_at >= ? AND created_at < ?",
        (t0, t1),
    ).fetchone()

    report = {
        "from": first,
        "to": last,
        "days": days,
        "desk_hours": f"{hours[0] // 60:02d}:{hours[0] % 60:02d}-{hours[1] // 60:02d}:{hours[1] % 60:02d}",
        "calls": {
            "answered_by_shefa": len(inbound),
            "after_hours": sum(1 for r in inbound if _after_hours(r["started_at"], hours)),
            "handed_to_a_person": handed,
            "turned_away_busy": turned_away,
            "outbound": sum(1 for r in call_rows if r["direction"] == "outbound"),
        },
        "bookings": {
            "by_shefa_phone": by_source.get("phone", 0),
            "by_web_page": by_source.get("web", 0),
            "walk_in": by_source.get("walkin", 0),
            "after_hours": after_hours_bookings,
            "total": sum(by_source.values()),
        },
        "visits": {
            "completed": outcome.get("completed", 0),
            "no_show": outcome.get("no_show", 0),
            "cancelled": outcome.get("cancelled", 0),
            "no_show_rate": round(outcome.get("no_show", 0) / seen, 3) if seen else None,
        },
        "callbacks": {
            "opened": callbacks["opened"] or 0,
            "resolved": int(callbacks["resolved"] or 0),
        },
        "missed_calls": {
            "total": sum(missed.values()),
            "booked": missed.get("booked", 0),
            "reached": missed.get("reached", 0) + missed.get("booked", 0),
        },
        "sms": {
            "sent": sms.get("sent", 0),
            "failed": sms.get("failed", 0),
            "not_sent_no_gateway": sms.get("not_configured", 0),
        },
        "estimate": {
            "staff_minutes_saved": by_source.get("phone", 0) * MINUTES_PER_PHONE_BOOKING,
            "minutes_per_booking_assumed": MINUTES_PER_PHONE_BOOKING,
        },
    }
    report["text_bn"] = text_bn(report, clinic.clinic_name("bn"))
    return report


def text_bn(r: dict[str, Any], clinic: str) -> str:
    """The report as a short Bangla message the owner can forward on WhatsApp."""
    from shefa.bangla import bn_digits

    n = bn_digits
    c, b, v, m = r["calls"], r["bookings"], r["visits"], r["missed_calls"]
    lines = [
        f"{clinic}: শেফার সাপ্তাহিক হিসাব ({n(r['from'])} থেকে {n(r['to'])})",
        f"• শেফা কল ধরেছে: {n(c['answered_by_shefa'])}টি (ডেস্ক বন্ধ থাকার সময়ে {n(c['after_hours'])}টি)",
        f"• শেফা বুকিং করেছে: ফোনে {n(b['by_shefa_phone'])}, ওয়েবে {n(b['by_web_page'])}"
        f" (ডেস্ক বন্ধ থাকার সময়ে {n(b['after_hours'])})",
        f"• মানুষের কাছে পাঠিয়েছে: {n(c['handed_to_a_person'])}টি কল",
    ]
    if m["total"]:
        lines.append(f"• মিস হওয়া কল: {n(m['total'])}, পরে বুকিং হয়েছে {n(m['booked'])}")
    if v["no_show_rate"] is not None:
        lines.append(f"• আসেননি: {n(v['no_show'])} জন ({n(round(v['no_show_rate'] * 100))}%)")
    lines.append(
        f"• আনুমানিক ডেস্কের সময় বেঁচেছে: {n(r['estimate']['staff_minutes_saved'])} মিনিট"
    )
    return "\n".join(lines)
