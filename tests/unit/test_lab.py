"""The conversation lab: scenarios, the runner against the real clinic store, the report."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from shefa import cli
from shefa.audio import AudioFrame
from shefa.config.settings import settings
from shefa.lab import report as lab_report
from shefa.lab.runner import (
    CheckResult,
    Lab,
    ScenarioResult,
    TurnRecord,
    _clean_patient_line,
    latin_share,
    scenario_checks,
    turn_checks,
    word_error_rate,
)
from shefa.lab.scenarios import Expect, Scenario, fill, load_scenarios, parse_scenarios, resolve_day
from shefa.models.base import Language, StreamEvent, STTResult

WEDNESDAY = date(2026, 11, 4)
SHIPPED = Path(__file__).resolve().parents[2] / "configs" / "lab" / "scenarios.yaml"
CLINIC = Path(__file__).resolve().parents[2] / "configs" / "clinic.example.yaml"


class TestScenarios:
    def test_days_resolve_to_the_next_one_after_today(self):
        assert resolve_day("Sun", WEDNESDAY) == date(2026, 11, 8)
        assert resolve_day("wed", WEDNESDAY) == date(2026, 11, 11)  # never today
        assert resolve_day("today", WEDNESDAY) == WEDNESDAY
        assert resolve_day("tomorrow", WEDNESDAY) == date(2026, 11, 5)
        with pytest.raises(ValueError, match="unknown day"):
            resolve_day("someday", WEDNESDAY)

    def test_placeholders_in_three_styles(self):
        text = fill("{iso:Sun} / {en:Sun} / {bn:Sun} / {other}", WEDNESDAY)

        assert text == "2026-11-08 / Sunday 8 November / রবিবার, ৮ নভেম্বর / {other}"

    def test_filling_reaches_setup_turns_persona_and_expected_dates(self):
        scenario = Scenario(
            id="x", title="t", tests="t", turns=["{bn:Mon}"], persona="on {en:Mon}",
            setup={"leave": [{"doctor": "Rahman", "from": "{iso:Mon}"}]},
            expect=Expect(booked_dates=["{iso:Mon}"]),
        )

        filled = scenario.filled(WEDNESDAY)

        assert filled.turns == ["সোমবার, ৯ নভেম্বর"]
        assert filled.persona == "on Monday 9 November"
        assert filled.setup["leave"][0]["from"] == "2026-11-09"
        assert filled.expect.booked_dates == ["2026-11-09"]
        assert scenario.turns == ["{bn:Mon}"]  # the original is untouched

    @pytest.mark.parametrize(
        ("raw", "message"),
        [
            ({"id": "x"}, "YAML list"),
            (["text"], "mapping"),
            ([{"id": "a", "title": "t", "tests": "t"}], "turns or a persona"),
            ([{"id": "a", "title": "t", "tests": "t", "turns": ["hi"]}] * 2, "duplicate"),
        ],
    )
    def test_bad_scenario_files_are_refused(self, raw, message):
        with pytest.raises(ValueError, match=message):
            parse_scenarios(raw)

    def test_the_shipped_scenarios_load_and_fill(self):
        scenarios = load_scenarios(SHIPPED)

        assert len(scenarios) >= 15
        assert {s.language for s in scenarios} == {"bn", "en"}
        assert any(s.persona for s in scenarios)
        for scenario in scenarios:
            filled = scenario.filled(WEDNESDAY)
            assert "{" not in " ".join(filled.turns) + filled.persona


class TestMeasures:
    def test_word_error_rate(self):
        assert word_error_rate("আমি ডাক্তার দেখাব", "আমি ডাক্তার দেখাব।") == 0.0
        assert word_error_rate("book Dr Rahman", "book doctor Rahman") == pytest.approx(1 / 3)
        assert word_error_rate("", "") == 0.0
        assert word_error_rate("", "noise") == 1.0

    def test_latin_share_ignores_ids_and_times(self):
        assert latin_share("আপনার APT-00001 নম্বর 09:30") == 0.0
        assert latin_share("hello আমি") == pytest.approx(5 / 8)  # আ ম ি = 3
        assert latin_share("123") == 0.0

    def test_simulated_patient_lines_are_cleaned(self):
        assert _clean_patient_line('Patient: "I need a doctor."') == "I need a doctor."
        assert _clean_patient_line("রোগী: আমার জ্বর") == "আমার জ্বর"
        assert _clean_patient_line("Thanks, bye [END]") is None
        assert _clean_patient_line("  ") is None


def _record(**kwargs):
    base = {"said": "আমি ডাক্তার দেখাব", "heard": "আমি ডাক্তার দেখাব", "reply": "জি, বলুন।",
            "state": "active", "language": "bn"}
    return TurnRecord(**{**base, **kwargs})


class TestTurnChecks:
    def _names(self, checks):
        return {c.name: c.ok for c in checks}

    def test_a_good_bangla_reply_passes_everything(self):
        checks = self._names(turn_checks(_record(), None))

        assert checks == {"replied": True, "no internal text": True, "brief": True,
                          "answers in the caller's language": True, "clean Bangla script": True}

    def test_problems_are_named(self):
        leak = self._names(turn_checks(_record(reply='{"tool": "book"}'), None))
        long = self._names(turn_checks(_record(reply="জি " * 50), None))
        english = self._names(turn_checks(_record(reply="Sure, tell me."), None))
        hindi = self._names(turn_checks(_record(reply="জি बताइए"), None))

        assert leak["no internal text"] is False
        assert long["brief"] is False
        assert english["answers in the caller's language"] is False
        assert hindi["clean Bangla script"] is False

    def test_an_expected_language_overrides_the_caller_script(self):
        checks = self._names(turn_checks(_record(heard="Doctor er appointment"), "bn"))

        assert checks["answers in the caller's language"] is True

    def test_an_ended_call_needs_no_language_checks_and_may_be_silent(self):
        assert self._names(turn_checks(_record(reply="", state="escalated"), None)) == {
            "replied": True
        }
        ended = self._names(turn_checks(_record(reply="Transferring.", state="escalated"), None))
        assert "answers in the caller's language" not in ended

    def test_an_empty_active_reply_fails(self):
        assert self._names(turn_checks(_record(reply=""), None)) == {"replied": False}


class TestScenarioChecks:
    def test_every_expectation(self):
        scenario = Scenario(
            id="x", title="t", tests="t", turns=["hi"],
            expect=Expect(state="active", actions_any=["book_appointment"],
                          actions_none=["cancel_appointment"], booked=1,
                          booked_dates=["2026-11-08"], never_say=["napa"],
                          final_reply_contains_any=["APT"]),
        )
        result = ScenarioResult(
            scenario,
            turns=[_record(actions=["book_appointment"], reply="Booked APT-00001")],
            appointments=[{"status": "booked", "date": "2026-11-08"},
                          {"status": "cancelled", "date": "2026-11-09"}],
        )

        checks = scenario_checks(scenario, result)

        assert [c.ok for c in checks] == [True] * 7

    def test_failures_and_an_empty_call(self):
        scenario = Scenario(
            id="x", title="t", tests="t", turns=["hi"],
            expect=Expect(state="escalated", actions_any=["book_appointment"], booked=1,
                          booked_dates=["2026-11-08"], never_say=["napa"],
                          final_reply_contains_any=["800"]),
        )

        checks = scenario_checks(scenario, ScenarioResult(scenario))

        assert not any(c.ok for c in checks[:4])
        assert checks[4].ok  # nothing said, so nothing forbidden said
        assert not checks[5].ok

    def test_passed_needs_every_check_and_no_error(self):
        result = ScenarioResult(Scenario(id="x", title="t", tests="t", turns=["hi"]))
        assert result.passed
        result.turns.append(_record(checks=[CheckResult("brief", False)]))
        assert not result.passed


class _Script:
    """The model behind the agent's router and replies, and behind the simulated patient."""

    def __init__(self, actions=(), patient_lines=()):
        self.actions = list(actions)
        self.patient_lines = list(patient_lines)
        self.patient_prompts = []

    async def generate(self, messages, tools=None, **kwargs):
        if kwargs.get("response_format"):
            action = self.actions.pop(0) if self.actions else None
            return SimpleNamespace(text=json.dumps(action) if action else "{}")
        self.patient_prompts.append(messages)
        return SimpleNamespace(text=self.patient_lines.pop(0) if self.patient_lines else "[END]")

    async def generate_events(self, messages, tools=None, **kwargs):
        yield StreamEvent(text="জি, আর কিছু লাগবে?")

    async def close(self):
        pass


class _Voice:
    async def synthesize_stream(self, text, language="en"):
        yield AudioFrame(b"\x01\x00" * 160, rate=16000)


class _Ears:
    def __init__(self, text=None):
        self.text = text

    async def transcribe(self, audio, language="auto"):
        return STTResult(text=self.text or "আমি মেডিসিনের ডাক্তার দেখাব", language=Language.BANGLA,
                         confidence=0.9)


@pytest.fixture
def lab(tmp_path, monkeypatch):
    from shefa.models.registry import registry

    monkeypatch.setattr(settings.pipeline.llm, "tool_calls", False)
    monkeypatch.setattr(settings.pipeline.llm, "filler_after_s", 0)
    monkeypatch.setattr(settings.languages, "primary", "bn")
    script = _Script()
    monkeypatch.setattr(registry, "_llm", script)

    def make(**kwargs):
        return Lab(clinic_file=CLINIC, work_dir=tmp_path / "work", today=WEDNESDAY,
                   patient_llm=script, **kwargs)

    return SimpleNamespace(make=make, script=script)


class TestRunner:
    async def test_a_scripted_booking_lands_in_its_own_clinic_database(self, lab):
        lab.script.actions = [
            None,
            {"tool": "book_appointment",
             "arguments": {"doctor_name": "Hossain", "date": "2026-11-08", "time": "10:00"}},
        ]
        scenario = Scenario(
            id="booking", title="t", tests="t", phone="01711000001",
            turns=["মেডিসিনের ডাক্তার দেখাব", "{bn:Sun} সকাল দশটায়"],
            expect=Expect(actions_any=["book_appointment"], booked=1,
                          booked_dates=["{iso:Sun}"], reply_language="bn"),
        )

        result = await lab.make().run(scenario)

        assert result.error is None
        assert result.turns[0].greeting
        assert result.turns[1].said == "রবিবার, ৮ নভেম্বর সকাল দশটায়"
        assert result.turns[1].actions == ["book_appointment"]
        assert "রেফারেন্স নম্বর ১" in result.turns[1].reply
        assert [a["start_time"] for a in result.appointments] == ["10:00"]
        assert result.passed, [c for c in result.checks if not c.ok]

    async def test_setup_puts_a_doctor_on_leave_and_books_an_existing_appointment(self, lab):
        scenario = Scenario(
            id="setup", title="t", tests="t", phone="01711000002", turns=["হ্যালো"],
            setup={"leave": [{"doctor": "Rahman", "from": "{iso:Tue}"}],
                   "appointments": [{"doctor": "Hossain", "date": "{iso:Sun}", "time": "09:00"}]},
        )
        runner = lab.make()

        result = await runner.run(scenario)

        assert [a["date"] for a in result.appointments] == ["2026-11-08"]
        from shefa.clinic import ClinicStore

        store = ClinicStore(runner.work_dir / "setup.db")
        assert store.doctor_on_leave(store.find_doctor("Rahman")["id"], "2026-11-10")
        store.close()

    async def test_a_rerun_starts_from_a_clean_database(self, lab):
        scenario = Scenario(
            id="again", title="t", tests="t", phone="01711000003", turns=["হ্যালো"],
            setup={"appointments": [{"doctor": "Hossain", "date": "{iso:Sun}", "time": "09:00"}]},
        )
        runner = lab.make()

        await runner.run(scenario)
        second = await runner.run(scenario)

        assert len(second.appointments) == 1  # the first run's booking did not survive

    async def test_an_emergency_ends_the_call(self, lab):
        scenario = Scenario(id="e", title="t", tests="t", turns=["আমার বুকে ব্যথা", "হ্যালো?"],
                            expect=Expect(state="escalated"))

        result = await lab.make().run(scenario)

        assert len(result.turns) == 1 and result.turns[0].state == "escalated"
        assert result.passed

    async def test_a_simulated_patient_talks_until_it_ends_the_call(self, lab):
        lab.script.patient_lines = ["আমার নাতির জ্বর", "শিশু ডাক্তার আছেন?", "[END]"]
        scenario = Scenario(id="p", title="t", tests="t", persona="নানি", language="bn",
                            max_turns=5)

        result = await lab.make().run(scenario)

        assert [t.said for t in result.turns] == ["আমার নাতির জ্বর", "শিশু ডাক্তার আছেন?"]
        first, second = lab.script.patient_prompts[0], lab.script.patient_prompts[1]
        assert "নানি" in first[0]["content"] and "Bangla" in first[0]["content"]
        assert first[1] == {"role": "user", "content": "(the phone is answered)"}
        assert [m["role"] for m in second[1:]] == ["user", "assistant", "user"]

    async def test_a_simulated_patient_stops_at_max_turns(self, lab):
        lab.script.patient_lines = ["one", "two", "three"]
        scenario = Scenario(id="p", title="t", tests="t", persona="x", language="en",
                            max_turns=2)

        result = await lab.make().run(scenario)

        assert len(result.turns) == 2

    async def test_a_persona_without_a_patient_model_runs_only_its_script(self, lab, tmp_path):
        runner = Lab(clinic_file=CLINIC, work_dir=tmp_path / "w", today=WEDNESDAY)
        scenario = Scenario(id="p", title="t", tests="t", persona="x", turns=["hello"])

        result = await runner.run(scenario)

        assert len(result.turns) == 1

    async def test_a_broken_model_is_recorded_not_raised(self, lab, monkeypatch):
        async def broken(*args, **kwargs):
            raise ConnectionError("server down")
            yield  # pragma: no cover - makes this an async generator

        monkeypatch.setattr(lab.script, "generate_events", broken)
        scenario = Scenario(id="b", title="t", tests="t", turns=["হ্যালো"])

        result = await lab.make().run(scenario)

        assert result.error == "ConnectionError: server down"
        assert not result.passed

    async def test_audio_mode_speaks_each_reply_and_times_the_first_sound(self, lab):
        ticks = iter(range(0, 10_000, 1))
        runner = lab.make(voice=_Voice(), clock=lambda: next(ticks) / 1000)
        scenario = Scenario(id="a", title="t", tests="t", turns=["হ্যালো। কেমন আছেন?"])

        result = await runner.run(scenario)

        turn = result.turns[0]
        assert turn.patient_audio and turn.agent_audio and turn.greeting_audio
        assert turn.first_audio_ms is not None and turn.wer is None

    async def test_speech_mode_hears_the_patient_through_a_phone_line(self, lab):
        heard = _Ears("আমি মেডিসিনের ডাক্তার দেখাবো")
        runner = lab.make(voice=_Voice(), stt=heard)
        scenario = Scenario(id="s", title="t", tests="t", turns=["আমি মেডিসিনের ডাক্তার দেখাব"])

        result = await runner.run(scenario)

        turn = result.turns[0]
        assert turn.heard == "আমি মেডিসিনের ডাক্তার দেখাবো"
        assert turn.wer == pytest.approx(0.25)
        assert turn.stt_ms is not None


class TestReport:
    def _results(self):
        scenario = Scenario(id="demo", title="Booking", title_bn="সিরিয়াল", tests="It books",
                            turns=["x"], phone="1")
        turn = _record(greeting="স্বাগতম", heard="আমি ডাক্তার দেখাবো", wer=0.25, llm_ms=900,
                       stt_ms=300, first_audio_ms=400, actions=["book_appointment"],
                       patient_audio=b"\x00\x00" * 10, agent_audio=b"\x00\x00" * 10,
                       greeting_audio=b"\x00\x00" * 10,
                       checks=[CheckResult("brief", False, "50 words")])
        passed = ScenarioResult(scenario, turns=[turn], appointments=[
            {"appointment_id": "APT-00001", "date": "2026-11-08", "start_time": "10:00",
             "doctor_en": "Hossain", "status": "booked"}])
        broken = ScenarioResult(Scenario(id="b", title="Broken <x>", tests="t", turns=["x"]),
                                turns=[_record(reply="", state="escalated")], error="Boom")
        return [passed, broken]

    def test_the_folder_has_a_page_results_and_audio(self, tmp_path):
        page = lab_report.write_report(self._results(), tmp_path / "r", {"language model": "x"})

        text = page.read_text(encoding="utf-8")
        data = json.loads((tmp_path / "r" / "results.json").read_text(encoding="utf-8"))
        audio = sorted(p.name for p in (tmp_path / "r" / "audio").iterdir())

        assert "SHEFA conversation lab" in text and "সিরিয়াল" in text
        assert "heard as: আমি ডাক্তার দেখাবো · 25% word errors" in text
        assert "Broken &lt;x&gt;" in text and "error: Boom" in text
        assert "audio/demo-call.wav" in text and "Dr. Hossain" in text
        assert "50 words" in text
        assert data["summary"]["scenarios"] == 2 and data["summary"]["mean_wer"] == 0.25
        assert data["meta"]["language model"] == "x"
        assert audio == ["demo-00-agent.wav", "demo-00-greeting.wav", "demo-00-patient.wav",
                         "demo-call.wav"]

    def test_a_text_only_run_shows_no_audio_or_speech_numbers(self, tmp_path):
        result = ScenarioResult(Scenario(id="t", title="T", tests="t", turns=["x"]),
                                turns=[_record()])

        text = lab_report.write_report([result], tmp_path / "r").read_text(encoding="utf-8")

        assert "<audio" not in text and "word errors" not in text
        assert lab_report.summarise([])["median_reply_ms"] is None


class TestLabCommand:
    def test_list(self, capsys):
        assert cli.main(["lab", "list", "--scenarios", str(SHIPPED)]) == 0
        assert "emergency-bn" in capsys.readouterr().out

    def test_usage_and_bad_input(self, capsys, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text("a: [")

        assert cli.main(["lab", "--help"]) == 0
        assert cli.main(["lab"]) == 2
        assert cli.main(["lab", "list", "--scenarios", str(bad)]) == 2
        assert cli.main(["lab", "run", "--scenarios", str(SHIPPED), "--only", "nope"]) == 2
        assert "Unknown scenario" in capsys.readouterr().err

    @pytest.mark.parametrize(("passes", "code"), [(True, 0), (False, 1)])
    def test_run_writes_the_report(self, monkeypatch, tmp_path, capsys, passes, code):
        from shefa.lab import runner as lab_runner
        from shefa.models.registry import registry

        made = {}

        class FakeLab:
            def __init__(self, **kwargs):
                made.update(kwargs)

            async def run(self, scenario):
                result = ScenarioResult(scenario, turns=[_record()])
                if not passes:
                    result.checks = [CheckResult("booked", False)]
                return result

        async def get(*args):
            return object()

        async def reset():
            made["reset"] = True

        monkeypatch.setattr(lab_runner, "Lab", FakeLab)
        monkeypatch.setattr(registry, "get_llm", get)
        monkeypatch.setattr(registry, "get_tts", get)
        monkeypatch.setattr(registry, "get_stt", get)
        monkeypatch.setattr(registry, "reset", reset)

        exit_code = cli.main(["lab", "run", "--scenarios", str(SHIPPED), "--only",
                              "emergency-bn,fee-question", "--out", str(tmp_path / "r"),
                              "--speech"])

        out = capsys.readouterr().out
        assert exit_code == code
        assert (tmp_path / "r" / "report.html").exists()
        assert made["voice"] is not None and made["stt"] is not None and made["reset"]
        assert ("2/2 scenarios passed" if passes else "NEEDS WORK  booked") in out

    def test_meta_names_the_models_used(self, monkeypatch):
        monkeypatch.setattr(settings.pipeline.stt, "per_language", {"bn": "x"})

        meta = cli.lab_meta(speech=True, audio=False)
        text_only = cli.lab_meta(speech=False, audio=False)

        assert meta["language model"].startswith("local ")
        assert "kokoro af_heart" in meta["voices"]
        assert meta["speech recognition"].endswith("(per language)")
        assert set(text_only) == {"language model"}
