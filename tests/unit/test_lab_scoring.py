"""`shefa lab score`: the shared scoring body, end to end, with fake models."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from shefa import cli
from shefa.config.settings import settings
from shefa.lab import scoring
from shefa.models.base import LLMResult, StreamEvent
from shefa.models.registry import registry

CLINIC = Path(__file__).resolve().parents[2] / "configs" / "clinic.example.yaml"
GOOD = {
    "warmth": 4,
    "feelings_first": 4,
    "no_repetition": 5,
    "phone_clarity": 5,
    "natural_bangla": 4,
    "tactful_limits": 4,
    "recovers_mishearing": 4,
    "note": "fine",
}


class AgentLLM:
    """The agent under test: replies the same way to everything, routes nothing."""

    def __init__(self):
        self.closed = False

    async def generate(self, messages, tools=None, **kwargs):
        return LLMResult(text="{}")

    async def generate_events(self, messages, tools=None, **kwargs):
        yield StreamEvent(text="জি, আর কিছু লাগবে?")

    async def close(self):
        self.closed = True


class TextLLM:
    def __init__(self, *texts: str):
        self.texts = list(texts)
        self.calls = 0
        self.messages = []

    async def generate(self, messages, tools=None, **kwargs):
        self.calls += 1
        self.messages.append(messages)
        text = self.texts[min(self.calls - 1, len(self.texts) - 1)]
        if isinstance(text, Exception):
            raise text
        return LLMResult(text=text)

    async def close(self):
        pass


def write_scenarios(path: Path, ids=("a", "b"), tags=None) -> Path:
    path.write_text(
        json.dumps(
            [
                {
                    "id": i,
                    "title": i,
                    "tests": "x",
                    "turns": ["হ্যালো"],
                    "tags": tags or [],
                    "caller_type": "angry" if i == "a" else "ordinary",
                }
                for i in ids
            ]
        ),
        encoding="utf-8",
    )
    return path


def make_args(tmp_path, **over):
    base = {
        "scenarios": [str(write_scenarios(tmp_path / "s.yaml"))],
        "tags": "",
        "model": None,
        "judge_model": "j",
        "caller_model": "c",
        "mishear": 0.0,
        "seed": 7,
        "speech": False,
        "out": str(tmp_path / "bench"),
        "clinic": str(CLINIC),
    }
    return SimpleNamespace(**{**base, **over})


@pytest.fixture(autouse=True)
def quiet_settings(monkeypatch):
    monkeypatch.setattr(settings.pipeline.llm, "tool_calls", False)
    monkeypatch.setattr(settings.pipeline.llm, "filler_after_s", 0)
    monkeypatch.setattr(settings.languages, "primary", "bn")
    yield
    registry.use_llm(None)


async def run(tmp_path, judge=None, agent=None, **over):
    args = make_args(tmp_path, **over)
    return await scoring.run_scorecard(
        over.get("model", "agent-m"),
        args,
        agent_llm=agent or AgentLLM(),
        caller_llm=TextLLM("[END]"),
        judge_llm=judge or TextLLM(json.dumps(GOOD)),
        today=date(2026, 11, 4),
    )


async def test_end_to_end_with_fake_models(tmp_path):
    judge = TextLLM(json.dumps(GOOD))
    card = await run(tmp_path, judge=judge)
    assert judge.calls == 2
    assert card["meta"]["model"] == "agent-m" and card["meta"]["judge_model"] == "j"
    assert card["meta"]["seed"] == 7 and card["meta"]["mishear_rate"] == 0.0
    # what makes two runs unlike is recorded, so `compare` can warn about it
    assert {"judge_model", "caller_model", "tags", "speech"} <= set(card["meta"])
    assert card["meta"]["case_count"] == 2
    assert card["judged"]["mean"] == pytest.approx(
        sum(v for v in GOOD.values() if isinstance(v, int)) / 7
    )
    assert card["judged"]["missing"] == 0
    assert set(card["scenarios"]) == {"a", "b"}


async def test_the_judge_sees_the_whole_transcript(tmp_path):
    judge = TextLLM(json.dumps(GOOD))
    await run(
        tmp_path, judge=judge, scenarios=[str(write_scenarios(tmp_path / "one.yaml", ("a",)))]
    )
    [messages] = judge.messages
    prompt = messages[-1]["content"]
    assert "Caller: হ্যালো" in prompt and "SHEFA: জি, আর কিছু লাগবে?" in prompt


async def test_a_failing_judge_call_is_unjudged_with_a_warning_not_a_crash(tmp_path, capsys):
    judge = TextLLM(RuntimeError("model server down"), json.dumps(GOOD))
    card = await run(tmp_path, judge=judge)
    assert card["judged"]["missing"] == 1
    err = capsys.readouterr().err
    assert "judge" in err and "model server down" in err and err.count("\n") == 1


async def test_the_agent_is_switched_and_restored(tmp_path):
    agent = AgentLLM()
    seen = []

    class Spy(TextLLM):
        async def generate(self, messages, tools=None, **kwargs):
            seen.append(await registry.get_llm())
            return await super().generate(messages)

    args = make_args(tmp_path)
    await scoring.run_scorecard(
        "m",
        args,
        agent_llm=agent,
        caller_llm=TextLLM("[END]"),
        judge_llm=Spy(json.dumps(GOOD)),
        today=date(2026, 11, 4),
    )
    assert seen == [agent, agent]
    assert registry._llm is None  # restored: the next get_llm builds the configured one
    assert agent.closed is False  # injected models belong to the caller


async def test_lab_audit_rows_go_to_the_bench_work_folder(tmp_path):
    await run(tmp_path)
    assert (tmp_path / "bench" / ".work" / "audit.db").exists()


async def test_human_labels_add_agreement(tmp_path):
    out = tmp_path / "bench"
    out.mkdir()
    (out / "human_labels.json").write_text(json.dumps({"a": {"warmth": 4, "feelings_first": 2}}))
    card = await run(tmp_path)
    assert card["judged"]["agreement"]["n"] == 2
    assert card["judged"]["agreement"]["within_one"] == 0.5


async def test_no_human_labels_no_agreement(tmp_path):
    assert "agreement" not in (await run(tmp_path))["judged"]


async def test_confusions_are_built_once_from_the_collector_and_saved(tmp_path, monkeypatch):
    from shefa.lab.mishear import Confusions

    built = []

    def fake_db(path):
        built.append(str(path))
        return Confusions({"ডাক্তার": ["দাক্তার"]}, 0.1)

    monkeypatch.setattr(Confusions, "from_collector_db", staticmethod(fake_db))
    await run(tmp_path, mishear=0.15)
    assert (tmp_path / "bench" / "confusions.json").exists()
    await run(tmp_path, mishear=0.15)
    assert len(built) == 1  # the second run loads the saved table


async def test_an_empty_collector_table_is_not_saved(tmp_path, monkeypatch, capsys):
    from shefa.lab.mishear import Confusions

    monkeypatch.setattr(scoring, "COLLECTOR_DB", tmp_path / "missing.db")
    monkeypatch.setattr(Confusions, "from_collector_db", staticmethod(lambda p: Confusions()))
    card = await run(tmp_path, mishear=0.15)
    assert not (tmp_path / "bench" / "confusions.json").exists()
    # The card records what was applied, not what was asked for.
    assert card["meta"]["mishear_rate"] == 0.0
    assert card["meta"]["mishear_requested"] == 0.15
    err = capsys.readouterr().err
    assert "no recognition errors found in" in err and "missing.db" in err
    assert "running without mishearing" in err


async def test_a_filled_table_records_the_rate_applied(tmp_path, monkeypatch):
    from shefa.lab.mishear import Confusions

    monkeypatch.setattr(
        Confusions, "from_collector_db", staticmethod(lambda p: Confusions({"a": ["b"]}, 0.0))
    )
    card = await run(tmp_path, mishear=0.15)
    assert card["meta"]["mishear_rate"] == 0.15 == card["meta"]["mishear_requested"]


async def test_a_bad_human_labels_file_fails_before_any_model_is_called(tmp_path):
    out = tmp_path / "bench"
    out.mkdir()
    judge, agent = TextLLM(json.dumps(GOOD)), AgentLLM()
    for text in ("{not json", "[1, 2]", '{"a": 4}', '{"a": {"warmth": "high"}}'):
        (out / "human_labels.json").write_text(text)
        with pytest.raises(ValueError, match="human_labels.json"):
            await run(tmp_path, judge=judge, agent=agent)
    assert judge.calls == 0


async def test_a_corrupt_confusions_file_fails_before_any_model_is_called(tmp_path):
    out = tmp_path / "bench"
    out.mkdir()
    judge = TextLLM(json.dumps(GOOD))
    for text in ("{not json", '{"subs": 3}', "[]", '{"subs": {}}'):
        (out / "confusions.json").write_text(text)
        with pytest.raises(ValueError, match="confusions.json"):
            await run(tmp_path, judge=judge, mishear=0.15)
    assert judge.calls == 0


async def test_caller_and_judge_are_built_on_the_side_server_the_agent_is_not(
    tmp_path, monkeypatch
):
    built = []

    def fake_ollama(model, base_url="default", temperature=None):
        built.append((model, base_url, temperature))
        return TextLLM("[END]") if temperature == 0.7 else TextLLM(json.dumps(GOOD))

    monkeypatch.setattr(scoring, "ollama_llm", fake_ollama)
    args = make_args(tmp_path, side_base_url="http://localhost:8001/v1")
    await scoring.run_scorecard("m", args, agent_llm=AgentLLM(), today=date(2026, 11, 4))
    assert ("c", "http://localhost:8001/v1", 0.7) in built
    assert ("j", "http://localhost:8001/v1", 0.0) in built


async def test_the_side_server_defaults_to_ollama(tmp_path, monkeypatch):
    built = []

    def fake_ollama(model, base_url="default", temperature=None):
        built.append(base_url)
        return TextLLM("[END]") if temperature == 0.7 else TextLLM(json.dumps(GOOD))

    monkeypatch.setattr(scoring, "ollama_llm", fake_ollama)
    await scoring.run_scorecard(
        "m", make_args(tmp_path), agent_llm=AgentLLM(), today=date(2026, 11, 4)
    )
    assert built == ["http://localhost:11434/v1"] * 2


async def test_scoring_a_think_candidate_runs_the_model_with_reasoning_on(tmp_path, monkeypatch):
    built = []

    def fake_ollama(model, base_url="default", temperature=None, *, think=False):
        built.append((model, think))
        if model == "qwen3:14b":
            return AgentLLM()
        return TextLLM("[END]") if temperature == 0.7 else TextLLM(json.dumps(GOOD))

    monkeypatch.setattr(scoring, "ollama_llm", fake_ollama)
    await scoring.run_scorecard("qwen3:14b+think", make_args(tmp_path), today=date(2026, 11, 4))
    assert ("qwen3:14b", True) in built


def test_validate_files_finds_the_same_bad_files_without_running_anything(tmp_path):
    out = tmp_path / "bench"
    out.mkdir()
    scoring.validate_files(make_args(tmp_path))
    (out / "human_labels.json").write_text("{oops")
    with pytest.raises(ValueError, match="human_labels.json"):
        scoring.validate_files(make_args(tmp_path))
    (out / "human_labels.json").unlink()
    (out / "confusions.json").write_text("{oops")
    with pytest.raises(ValueError, match="confusions.json"):
        scoring.validate_files(make_args(tmp_path, mishear=0.15))
    scoring.validate_files(make_args(tmp_path, mishear=0.15, speech=True))  # not replayed
    scoring.validate_files(make_args(tmp_path, mishear=0.0))


async def test_progress_lines_go_through_the_callback(tmp_path):
    lines = []
    args = make_args(tmp_path)
    await scoring.run_scorecard(
        "m",
        args,
        agent_llm=AgentLLM(),
        caller_llm=TextLLM("[END]"),
        judge_llm=TextLLM(json.dumps(GOOD)),
        today=date(2026, 11, 4),
        progress=lines.append,
    )
    assert [line.split()[0] for line in lines] == ["a", "b"]


async def test_progress_none_is_silent(tmp_path, capsys):
    args = make_args(tmp_path)
    await scoring.run_scorecard(
        "m",
        args,
        agent_llm=AgentLLM(),
        caller_llm=TextLLM("[END]"),
        judge_llm=TextLLM(json.dumps(GOOD)),
        today=date(2026, 11, 4),
        progress=None,
    )
    assert capsys.readouterr().out == ""


async def test_the_configured_model_the_run_caused_is_closed_and_dropped(tmp_path, monkeypatch):
    built = AgentLLM()

    async def create():
        return built

    monkeypatch.setattr(registry, "_create_llm", create)
    args = make_args(tmp_path, model=None)
    await scoring.run_scorecard(
        None,
        args,
        caller_llm=TextLLM("[END]"),
        judge_llm=TextLLM(json.dumps(GOOD)),
        today=date(2026, 11, 4),
    )
    assert built.closed is True and registry._llm is None


async def test_mishear_zero_skips_the_table(tmp_path, monkeypatch):
    from shefa.lab.mishear import Confusions

    def boom(path):
        raise AssertionError("the collector database must not be read")

    monkeypatch.setattr(Confusions, "from_collector_db", staticmethod(boom))
    await run(tmp_path, mishear=0.0)


async def test_the_configured_model_is_named_when_none_is_given(tmp_path, monkeypatch):
    registry.use_llm(AgentLLM())  # stands in for the product's configured model
    args = make_args(tmp_path, model=None)
    card = await scoring.run_scorecard(
        None,
        args,
        caller_llm=TextLLM("[END]"),
        judge_llm=TextLLM(json.dumps(GOOD)),
        today=date(2026, 11, 4),
    )
    assert card["meta"]["model"].startswith(settings.pipeline.llm.provider)


class TestScenarioSelection:
    def test_defaults_are_the_bench_folder_then_the_main_file(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "configs/lab/bench").mkdir(parents=True)
        write_scenarios(tmp_path / "configs/lab/bench/b.yaml", ("x",))
        write_scenarios(tmp_path / "configs/lab/scenarios.yaml", ("y",))
        chosen = scoring.select_scenarios(SimpleNamespace(scenarios=None, tags=""))
        assert [s.id for s in chosen] == ["x", "y"]

    def test_tags_filter_by_tag_caller_type_or_goal(self, tmp_path):
        path = write_scenarios(tmp_path / "s.yaml", ("a", "b"), tags=["kb"])
        by_tag = scoring.select_scenarios(SimpleNamespace(scenarios=[str(path)], tags="kb"))
        by_type = scoring.select_scenarios(SimpleNamespace(scenarios=[str(path)], tags="angry"))
        assert len(by_tag) == 2 and [s.id for s in by_type] == ["a"]

    def test_a_missing_file_is_a_clear_error(self, tmp_path):
        with pytest.raises(ValueError, match="nope.yaml"):
            scoring.select_scenarios(
                SimpleNamespace(scenarios=[str(tmp_path / "nope.yaml")], tags="")
            )

    def test_a_tag_that_selects_nothing_is_a_clear_error(self, tmp_path):
        path = write_scenarios(tmp_path / "s.yaml")
        with pytest.raises(ValueError, match="zzz"):
            scoring.select_scenarios(SimpleNamespace(scenarios=[str(path)], tags="zzz"))

    def test_the_same_id_in_two_files_is_an_error(self, tmp_path):
        one = write_scenarios(tmp_path / "1.yaml", ("a",))
        two = write_scenarios(tmp_path / "2.yaml", ("a",))
        with pytest.raises(ValueError, match="duplicate"):
            scoring.select_scenarios(SimpleNamespace(scenarios=[str(one), str(two)], tags=""))


class TestScoreCommand:
    def test_parses_arguments_with_the_documented_defaults(self):
        args = cli.build_parser().parse_args(
            ["lab", "score", "--model", "gemma2:9b", "--tags", "angry,kb"]
        )
        assert (args.lab_command, args.model, args.tags, args.mishear) == (
            "score",
            "gemma2:9b",
            "angry,kb",
            0.15,
        )
        assert args.seed == 7 and args.out == "data/bench" and args.speech is False
        assert args.scenarios is None and args.judge_model == args.caller_model
        assert args.caller_model == "hf.co/unsloth/gemma-3-12b-it-GGUF:Q4_K_M"
        assert args.side_base_url == "http://localhost:11434/v1"

    def test_side_base_url_can_point_at_another_server(self):
        args = cli.build_parser().parse_args(
            ["lab", "score", "--side-base-url", "http://localhost:8001/v1"]
        )
        assert args.side_base_url == "http://localhost:8001/v1"

    def test_compare_takes_two_files(self):
        args = cli.build_parser().parse_args(["lab", "compare", "a.json", "b.json"])
        assert (args.lab_command, args.a, args.b) == ("compare", "a.json", "b.json")

    @pytest.mark.parametrize("flags", [["--mishear", "1.5"], ["--mishear", "-0.1"]])
    def test_a_bad_mishear_rate_is_exit_2(self, flags, capsys):
        assert cli.main(["lab", "score", *flags]) == 2
        assert "mishear" in capsys.readouterr().err

    def test_a_missing_scenario_file_is_exit_2(self, tmp_path, capsys):
        assert cli.main(["lab", "score", "--scenarios", str(tmp_path / "no.yaml")]) == 2
        assert "no.yaml" in capsys.readouterr().err

    def test_a_tag_that_selects_nothing_is_exit_2(self, tmp_path, capsys):
        path = write_scenarios(tmp_path / "s.yaml")
        assert cli.main(["lab", "score", "--scenarios", str(path), "--tags", "zzz"]) == 2
        assert "zzz" in capsys.readouterr().err

    def test_a_run_prints_the_summary_saves_the_card_and_resets(
        self, tmp_path, monkeypatch, capsys
    ):
        path = write_scenarios(tmp_path / "s.yaml")
        made = []
        resets = []

        def fake_ollama(model, base_url="", temperature=None):
            made.append((model, temperature))
            return TextLLM("[END]") if temperature == 0.7 else TextLLM(json.dumps(GOOD))

        async def reset():
            resets.append(True)

        monkeypatch.setattr(scoring, "ollama_llm", fake_ollama)
        monkeypatch.setattr(registry, "reset", reset)
        monkeypatch.setattr(settings.pipeline.llm, "tool_calls", False)
        code = cli.main(
            [
                "lab",
                "score",
                "--scenarios",
                str(path),
                "--model",
                "gemma2:9b",
                "--mishear",
                "0",
                "--out",
                str(tmp_path / "bench"),
                "--clinic",
                str(CLINIC),
            ]
        )
        out = capsys.readouterr().out
        assert code == 0 and resets
        assert "scorecard  gemma2:9b" in out
        [saved] = (tmp_path / "bench").glob("scorecard-gemma2_9b-*.json")
        assert json.loads(saved.read_text())["meta"]["model"] == "gemma2:9b"
        assert ("gemma2:9b", None) in made
        assert {t for _, t in made} >= {0.0, 0.7}

    def test_a_bad_human_labels_file_is_exit_2_and_names_the_file(self, tmp_path, capsys):
        path = write_scenarios(tmp_path / "s.yaml")
        out = tmp_path / "bench"
        out.mkdir()
        (out / "human_labels.json").write_text("{oops")
        code = cli.main(
            [
                "lab",
                "score",
                "--scenarios",
                str(path),
                "--model",
                "m",
                "--out",
                str(out),
                "--mishear",
                "0",
            ]
        )
        assert code == 2
        assert "human_labels.json" in capsys.readouterr().err

    def test_compare_prints_the_difference(self, tmp_path, capsys):
        from shefa.lab import scorecard

        card = scorecard.build([], {}, {"model": "m"})
        a, b = tmp_path / "a.json", tmp_path / "b.json"
        a.write_text(json.dumps(card))
        b.write_text(json.dumps(card))
        assert cli.main(["lab", "compare", str(a), str(b)]) == 0
        assert "b - a" in capsys.readouterr().out

    def test_compare_with_an_unreadable_file_is_exit_2(self, tmp_path, capsys):
        assert cli.main(["lab", "compare", str(tmp_path / "x"), str(tmp_path / "y")]) == 2


def test_the_transcript_shows_what_the_caller_said_and_what_shefa_heard():
    from shefa.lab.runner import ScenarioResult, TurnRecord
    from shefa.lab.scenarios import Scenario

    result = ScenarioResult(
        Scenario(id="m", title="t", tests="t"),
        turns=[
            TurnRecord(said="রবিবার দশটায়", heard="রবিবার দশটায়", reply="ঠিক আছে?", state="active",
                       language="bn", greeting="জি, বলুন।"),
            TurnRecord(said="হ্যাঁ, রহমান", heard="হ্যাঁ, রমজান", reply="জি।", state="active",
                       language="bn"),
        ],
    )
    lines = scoring.transcript_of(result)
    assert lines[1] == ("patient", "রবিবার দশটায়")  # heard as said: shown once
    assert lines[3] == ("patient", "said: হ্যাঁ, রহমান  (SHEFA heard: হ্যাঁ, রমজান)")
