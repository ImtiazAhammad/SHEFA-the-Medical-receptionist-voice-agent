"""Write a lab run as a folder a client can open: report.html, results.json, audio/*.wav.

The page is self-contained apart from the WAV files beside it, so the folder can be
zipped and sent, or opened from `shefa serve` at /lab.
"""

from __future__ import annotations

import html
import json
import statistics
import wave
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from shefa.lab.runner import ScenarioResult, TurnRecord

RATE = 16000
GAP = b"\x00\x00" * int(RATE * 0.35)


def write_wav(path: Path, pcm: bytes) -> None:
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(pcm)


def _median(values: list[float]) -> float | None:
    return statistics.median(values) if values else None


def summarise(results: list[ScenarioResult]) -> dict[str, Any]:
    turns = [t for r in results for t in r.turns]
    checks = [c for r in results for c in [*r.checks, *(c for t in r.turns for c in t.checks)]]
    wers = [t.wer for t in turns if t.wer is not None]
    return {
        "scenarios": len(results),
        "scenarios_passed": sum(1 for r in results if r.passed),
        "checks": len(checks),
        "checks_passed": sum(1 for c in checks if c.ok),
        "turns": len(turns),
        "median_reply_ms": _median([t.llm_ms for t in turns]),
        "median_first_audio_ms": _median(
            [t.first_audio_ms for t in turns if t.first_audio_ms is not None]
        ),
        "median_stt_ms": _median([t.stt_ms for t in turns if t.stt_ms is not None]),
        "mean_wer": (sum(wers) / len(wers)) if wers else None,
    }


def _turn_json(turn: TurnRecord) -> dict[str, Any]:
    return {
        key: getattr(turn, key)
        for key in ("said", "heard", "reply", "greeting", "state", "language", "actions",
                    "wer", "llm_ms", "stt_ms", "first_audio_ms")
    } | {"checks": [c.__dict__ for c in turn.checks]}


def results_json(results: list[ScenarioResult], meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "meta": meta,
        "summary": summarise(results),
        "scenarios": [
            {
                "id": r.scenario.id,
                "title": r.scenario.title,
                "tests": r.scenario.tests,
                "passed": r.passed,
                "error": r.error,
                "checks": [c.__dict__ for c in r.checks],
                "appointments": r.appointments,
                "turns": [_turn_json(t) for t in r.turns],
            }
            for r in results
        ],
    }


def _audio(results: list[ScenarioResult], out: Path) -> dict[tuple[str, int, str], str]:
    """Write every clip plus one whole-call file per scenario; return their paths."""
    folder = out / "audio"
    folder.mkdir(parents=True, exist_ok=True)
    paths: dict[tuple[str, int, str], str] = {}
    for result in results:
        call: list[bytes] = []
        for index, turn in enumerate(result.turns):
            for role, pcm in (("greeting", turn.greeting_audio), ("patient", turn.patient_audio),
                              ("agent", turn.agent_audio)):
                if pcm:
                    name = f"{result.scenario.id}-{index:02d}-{role}.wav"
                    write_wav(folder / name, pcm)
                    paths[(result.scenario.id, index, role)] = f"audio/{name}"
                    call.extend([pcm, GAP])
        if call:
            name = f"{result.scenario.id}-call.wav"
            write_wav(folder / name, b"".join(call))
            paths[(result.scenario.id, -1, "call")] = f"audio/{name}"
    return paths


def _ms(value: float | None) -> str:
    return "—" if value is None else f"{value / 1000:.2f} s"


# The page style lives in report.css so it can be edited as CSS.
_CSS = Path(__file__).with_name("report.css").read_text(encoding="utf-8")


def _checks_html(checks: list[Any]) -> str:
    rows = "".join(
        f'<li class="{"ok" if c.ok else "bad"}">{html.escape(c.name)}'
        f'{" <span class=mute>(" + html.escape(c.detail) + ")</span>" if c.detail else ""}</li>'
        for c in checks
    )
    return f'<ul class="checks">{rows}</ul>' if rows else ""


def _bubble(role: str, text: str, audio: str | None, extra: str = "") -> str:
    who = "Patient" if role == "patient" else "SHEFA"
    player = f'<audio controls preload="none" src="{html.escape(audio)}"></audio>' if audio else ""
    cls = "msg me" if role == "patient" else "msg"
    return f'<div class="{cls}"><small>{who}</small>{html.escape(text)}{extra}{player}</div>'


def render_html(results: list[ScenarioResult], meta: dict[str, Any],
                audio: dict[tuple[str, int, str], str]) -> str:
    summary = summarise(results)
    stats = [
        (f"{summary['scenarios_passed']}/{summary['scenarios']}", "scenarios passed"),
        (f"{summary['checks_passed']}/{summary['checks']}", "checks passed"),
        (_ms(summary["median_reply_ms"]), "median time to decide a reply"),
        (_ms(summary["median_first_audio_ms"]), "median time to first sound"),
    ]
    if summary["mean_wer"] is not None:
        stats.append((f"{summary['mean_wer']:.0%}", "speech recognition word errors"))
    stat_html = "".join(f'<div class="stat"><b>{v}</b><span>{k}</span></div>' for v, k in stats)
    index = "".join(
        f'<tr><td><a href="#{html.escape(r.scenario.id)}">{html.escape(r.scenario.title)}</a></td>'
        f'<td>{html.escape(r.scenario.tests)}</td>'
        f'<td><span class="tag {"ok" if r.passed else "bad"}">'
        f'{"pass" if r.passed else "needs work"}</span></td></tr>'
        for r in results
    )
    sections = []
    for result in results:
        sid = result.scenario.id
        parts = []
        call = audio.get((sid, -1, "call"))
        if call:
            parts.append(f'<p class="mute">Whole call</p><audio controls preload="none" '
                         f'src="{html.escape(call)}"></audio>')
        for i, turn in enumerate(result.turns):
            if turn.greeting:
                parts.append(_bubble("agent", turn.greeting, audio.get((sid, i, "greeting"))))
            heard = ""
            if turn.heard != turn.said:
                heard = (f'<div class="heard">heard as: {html.escape(turn.heard)}'
                         f' · {turn.wer:.0%} word errors</div>')
            parts.append(_bubble("patient", turn.said, audio.get((sid, i, "patient")), heard))
            tags = [f"decided in {_ms(turn.llm_ms)}"]
            if turn.first_audio_ms is not None:
                tags.append(f"first sound {_ms(turn.first_audio_ms)}")
            tags += [f"action: {a}" for a in turn.actions]
            if turn.state != "active":
                tags.append(f"call {turn.state}")
            failed = [c for c in turn.checks if not c.ok]
            extra = '<div class="heard">' + " · ".join(html.escape(t) for t in tags) + "</div>"
            if failed:
                extra += _checks_html(failed)
            parts.append(_bubble("agent", turn.reply or "(no reply)",
                                 audio.get((sid, i, "agent")), extra))
        if result.error:
            parts.append(f'<p class="tag bad">error: {html.escape(result.error)}</p>')
        if result.appointments:
            rows = "".join(
                f"<tr><td>{html.escape(str(a.get('appointment_id', '')))}</td>"
                f"<td>{html.escape(str(a.get('date', '')))} "
                f"{html.escape(str(a.get('start_time', '')))}</td>"
                f"<td>Dr. {html.escape(str(a.get('doctor_en', '')))}</td>"
                f"<td>{html.escape(str(a.get('status', '')))}</td></tr>"
                for a in result.appointments
            )
            parts.append(f'<p class="mute">Clinic database after the call</p><table>{rows}</table>')
        title_bn = (f' <span class="mute">{html.escape(result.scenario.title_bn)}</span>'
                    if result.scenario.title_bn else "")
        sections.append(
            f'<section class="card" id="{html.escape(sid)}"><div class="head"><h2>'
            f'{html.escape(result.scenario.title)}</h2>{title_bn}<span class="tag '
            f'{"ok" if result.passed else "bad"}">{"pass" if result.passed else "needs work"}'
            f'</span></div><p class="tests">{html.escape(result.scenario.tests)}</p>'
            + "".join(parts) + _checks_html(result.checks) + "</section>"
        )
    setup = " · ".join(f"{html.escape(k)}: {html.escape(str(v))}" for k, v in meta.items())
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>SHEFA conversation lab</title><style>{_CSS}</style></head><body><main>"
        "<h1>SHEFA conversation lab</h1>"
        f'<p class="sub">{setup}</p><div class="grid">{stat_html}</div>'
        f'<div class="card"><table><tr><th>Scenario</th><th>What it tests</th><th></th></tr>'
        f"{index}</table></div>" + "".join(sections) + "</main></body></html>"
    )


def write_report(results: list[ScenarioResult], out: str | Path,
                 meta: dict[str, Any] | None = None) -> Path:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    meta = {"run": datetime.now().strftime("%Y-%m-%d %H:%M"), **(meta or {})}
    audio = _audio(results, out)
    (out / "results.json").write_text(
        json.dumps(results_json(results, meta), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    page = out / "report.html"
    page.write_text(render_html(results, meta, audio), encoding="utf-8")
    return page
