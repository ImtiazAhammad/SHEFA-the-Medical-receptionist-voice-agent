"""`shefa lab bakeoff`: the winner rule, the latency probe, the memory reading, the loop."""

from __future__ import annotations

import asyncio
import itertools
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from shefa import cli
from shefa.lab import bakeoff
from shefa.lab.bakeoff import (
    first_sentence_latency,
    gpu_memory_mb,
    model_available,
    pick_winner,
    run_bakeoff,
)
from shefa.models.base import StreamEvent

CARD = {
    "meta": {"model": "a", "case_count": 20},
    "hard": {"pass_rate": 0.9},
    "task": {"pass_rate": 0.8},
    "full": {"pass_rate": 0.75},
    "judged": {"mean": 4.1},
    "bangla_purity": 0.97,
}


class SlowFirstChunkLLM:
    """A model whose first text comes after a delay; counts the requests in flight."""

    def __init__(self, delay_s: float = 0.05, extra_body=None):
        self.delay_s = delay_s
        self.extra_body = extra_body
        self.in_flight = 0
        self.max_in_flight = 0
        self.completed = 0
        self.kwargs = []
        self.closed = False

    async def generate_events(self, messages, tools=None, **kwargs):
        self.kwargs.append(kwargs)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(self.delay_s)
            yield StreamEvent(text="জি")
            await asyncio.sleep(self.delay_s)
            yield StreamEvent(text=", বলুন।")  # the first sentence is complete here
            await asyncio.sleep(self.delay_s)
            yield StreamEvent(text=" আর কিছু?")
            self.completed += 1
        finally:
            self.in_flight -= 1

    async def close(self):
        self.closed = True


def args_stub(tmp_path: Path, **over) -> SimpleNamespace:
    values = {
        "out": str(tmp_path),
        "base_url": "http://localhost:11434/v1",
        "side_base_url": "http://localhost:11434/v1",
        "judge_model": "judge",
        "caller_model": "caller",
        "with_voice": False,
        "tags": "bakeoff",
    }
    values.update(over)
    return SimpleNamespace(**values)


def fake_available(names: set[str]):
    async def available(model, base="http://localhost:11434"):
        return model in names

    return available


@pytest.fixture
def probes(monkeypatch):
    """No server, no card: the probes, the model client and the unloader are faked."""
    calls = SimpleNamespace(
        unloaded=[], built=[], rounds=[], gpu=itertools.chain([8000], itertools.repeat(9000))
    )
    llm = SlowFirstChunkLLM(0)

    def build(model, base_url=None, temperature=None):
        calls.built.append((model, base_url))
        return llm

    async def latency(llm, prompts, concurrency=3, rounds=10):
        calls.rounds.append(rounds)
        calls.prompts = prompts
        return {"p50_ms": 300.0, "p95_ms": 500.0, "samples": 3 * rounds}

    async def unload(model, base="http://localhost:11434"):
        calls.unloaded.append(model)
        return True

    async def warm(llm, messages):
        calls.warmed = messages
        return 900.0

    monkeypatch.setattr(bakeoff, "ollama_llm", build)
    monkeypatch.setattr(bakeoff, "first_sentence_latency", latency)
    monkeypatch.setattr(bakeoff, "_first_sentence_ms", warm)
    monkeypatch.setattr(bakeoff, "unload_model", unload)
    monkeypatch.setattr(bakeoff, "gpu_memory_mb", lambda: next(calls.gpu))
    calls.llm = llm
    return calls


async def fake_scorer(model, args, **kwargs):
    return {**CARD, "meta": {"model": model, "case_count": 20}}


def test_pick_winner_respects_budget_then_quality():
    rows = [
        {
            "model": "fast",
            "status": "ok",
            "first_sentence_p95_ms": 400,
            "full_pass": 0.80,
            "judged_mean": 3.9,
        },
        {
            "model": "best",
            "status": "ok",
            "first_sentence_p95_ms": 700,
            "full_pass": 0.90,
            "judged_mean": 3.5,
        },
        {
            "model": "slow",
            "status": "ok",
            "first_sentence_p95_ms": 1500,
            "full_pass": 1.0,
            "judged_mean": 4.8,
        },
        {"model": "gone", "status": "unavailable"},
    ]
    assert pick_winner(rows, tts_first_ms=400) == "best"


def test_pick_winner_none_when_all_too_slow():
    row = {
        "model": "s",
        "status": "ok",
        "first_sentence_p95_ms": 2000,
        "full_pass": 1,
        "judged_mean": 5,
    }
    assert pick_winner([row], 400) is None


def test_pick_winner_ties_on_full_pass_go_to_judged_mean():
    rows = [
        {
            "model": "a",
            "status": "ok",
            "first_sentence_p95_ms": 300,
            "full_pass": 0.9,
            "judged_mean": 3.0,
        },
        {
            "model": "b",
            "status": "ok",
            "first_sentence_p95_ms": 300,
            "full_pass": 0.9,
            "judged_mean": 4.0,
        },
    ]
    assert pick_winner(rows, 400) == "b"


def test_pick_winner_budget_is_inclusive_and_error_rows_never_win():
    at_budget = {
        "model": "edge",
        "status": "ok",
        "first_sentence_p95_ms": 800,
        "full_pass": 0.5,
        "judged_mean": 2,
    }
    errored = {
        "model": "err",
        "status": "error",
        "first_sentence_p95_ms": 100,
        "full_pass": 1.0,
        "judged_mean": 5,
    }
    assert pick_winner([errored, at_budget], 400, budget_ms=1200) == "edge"
    assert pick_winner([at_budget], 401, budget_ms=1200) is None


def test_pick_winner_unmeasured_quality_loses_to_measured():
    rows = [
        {
            "model": "blank",
            "status": "ok",
            "first_sentence_p95_ms": 300,
            "full_pass": None,
            "judged_mean": None,
        },
        {
            "model": "real",
            "status": "ok",
            "first_sentence_p95_ms": 300,
            "full_pass": 0.1,
            "judged_mean": 1.0,
        },
    ]
    assert pick_winner(rows, 400) == "real"


def test_pick_winner_none_without_a_voice_time_or_rows():
    row = {
        "model": "m",
        "status": "ok",
        "first_sentence_p95_ms": 100,
        "full_pass": 1,
        "judged_mean": 5,
    }
    assert pick_winner([row], None) is None
    assert pick_winner([], 400) is None


async def test_first_sentence_latency_runs_concurrently():
    llm = SlowFirstChunkLLM(delay_s=0.05)
    out = await first_sentence_latency(
        llm, [[{"role": "user", "content": "x"}]], concurrency=3, rounds=2
    )
    assert out["p95_ms"] >= 49 and llm.max_in_flight == 3
    assert out["samples"] == 6 and llm.in_flight == 0


async def test_the_time_is_to_the_first_sentence_and_the_reply_is_then_read_to_its_end():
    llm = SlowFirstChunkLLM(delay_s=0.05)
    out = await first_sentence_latency(
        llm, [[{"role": "user", "content": "x"}]], concurrency=1, rounds=1
    )
    # not the 50 ms of the first word, nor the 150 ms the whole reply took
    assert 99 <= out["p50_ms"] < 140
    assert llm.completed == 1 and llm.in_flight == 0  # nothing left half-open


async def test_the_probe_adds_no_overrides_of_its_own():
    """The client applies its own extra fields; passing them again would send them twice."""
    llm = SlowFirstChunkLLM(delay_s=0, extra_body={"think": False})
    await first_sentence_latency(llm, [[{"role": "user", "content": "x"}]], concurrency=2, rounds=1)
    assert llm.kwargs == [{}, {}]


async def test_the_default_is_ten_rounds_of_three_for_thirty_samples():
    llm = SlowFirstChunkLLM(delay_s=0)
    out = await first_sentence_latency(llm, [[{"role": "user", "content": "x"}]])
    assert out["samples"] == 30 and llm.max_in_flight == 3


async def test_a_reply_with_no_sentence_end_is_timed_to_the_end_of_the_stream():
    class Unpunctuated(SlowFirstChunkLLM):
        async def generate_events(self, messages, tools=None, **kwargs):
            await asyncio.sleep(0.03)
            yield StreamEvent(text="জি")
            await asyncio.sleep(0.03)
            yield StreamEvent(text=" বলুন")

    out = await first_sentence_latency(Unpunctuated(), [[{"role": "user", "content": "x"}]], 1, 1)
    assert out["p50_ms"] >= 59


def test_the_probe_asks_with_the_products_own_prompt_and_the_clinics_directory(tmp_path):
    from shefa.clinic import ClinicStore
    from shefa.clinic.brief import directory_brief
    from shefa.clinic.loader import import_directory_file
    from shefa.prompts import system_prompt

    prompts = bakeoff.probe_prompts("configs/clinic.example.yaml", tmp_path)
    store = ClinicStore(tmp_path / "check.db")
    import_directory_file(store, "configs/clinic.example.yaml")
    bn = system_prompt("bn", None, directory_brief(store, "bn"))
    en = system_prompt("en", None, directory_brief(store, "en"))
    store.close()
    assert len(prompts) >= 4
    for messages in prompts:
        system, caller = messages
        assert system["role"] == "system" and caller["role"] == "user" and caller["content"]
        assert system["content"] in (bn, en)
    assert {m[0]["content"] for m in prompts} == {bn, en}
    assert "Hossain" in en


async def test_a_reply_with_no_text_is_an_error():
    class Silent(SlowFirstChunkLLM):
        async def generate_events(self, messages, tools=None, **kwargs):
            yield StreamEvent(text="")

    with pytest.raises(RuntimeError, match="no text"):
        await first_sentence_latency(Silent(), [[{"role": "user", "content": "x"}]], 1, 1)


async def test_the_probe_reaches_the_real_client_with_think_off(monkeypatch):
    """The real adapter sends its `extra_body` on the streamed request the probe makes."""
    from shefa.lab.models import NO_THINKING, ollama_llm

    sent = []

    class Chunk:
        def __init__(self, text):
            delta = SimpleNamespace(content=text, tool_calls=None)
            self.choices = [SimpleNamespace(delta=delta, finish_reason=None)]

    async def create(**kwargs):
        sent.append(kwargs)

        async def chunks():
            yield Chunk("জি")

        return chunks()

    llm = ollama_llm("m")
    monkeypatch.setattr(llm._client.chat.completions, "create", create)
    await bakeoff._first_sentence_ms(llm, [{"role": "user", "content": "x"}])
    assert sent[0]["extra_body"] == NO_THINKING and sent[0]["stream"] is True
    await llm.close()


async def test_first_sentence_latency_without_prompts_is_an_error():
    with pytest.raises(ValueError, match="prompt"):
        await first_sentence_latency(SlowFirstChunkLLM(), [], concurrency=1, rounds=1)


def test_gpu_memory_sums_cards(monkeypatch):
    def run(cmd, **kwargs):
        assert cmd[0] == "nvidia-smi"
        return subprocess.CompletedProcess(cmd, 0, stdout="1200\n800\n", stderr="")

    monkeypatch.setattr(bakeoff.subprocess, "run", run)
    assert gpu_memory_mb() == 2000


@pytest.mark.parametrize(
    "failure",
    [
        FileNotFoundError("nvidia-smi"),
        subprocess.TimeoutExpired("nvidia-smi", 5),
        subprocess.CalledProcessError(9, "nvidia-smi"),
    ],
)
def test_gpu_memory_none_when_nvidia_smi_fails(monkeypatch, failure):
    def run(cmd, **kwargs):
        raise failure

    monkeypatch.setattr(bakeoff.subprocess, "run", run)
    assert gpu_memory_mb() is None


def test_gpu_memory_none_for_unreadable_output(monkeypatch):
    monkeypatch.setattr(
        bakeoff.subprocess,
        "run",
        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, stdout="[N/A]\n", stderr=""),
    )
    assert gpu_memory_mb() is None


def _serve(monkeypatch, handler):
    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(bakeoff, "_client", lambda: httpx.AsyncClient(transport=transport))


async def test_model_available_reads_ollama_tags(monkeypatch):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(
            200, json={"models": [{"name": "gemma2:9b"}, {"name": "qwen3:latest"}]}
        )

    _serve(monkeypatch, handler)
    assert await model_available("gemma2:9b")
    assert await model_available("qwen3")  # no tag means :latest
    assert not await model_available("gemma2")
    assert not await model_available("nope:1b")
    assert seen[0] == "http://localhost:11434/api/tags"


async def test_model_available_false_when_ollama_is_down(monkeypatch):
    def handler(request):
        raise httpx.ConnectError("refused")

    _serve(monkeypatch, handler)
    assert not await model_available("gemma2:9b")


async def test_model_available_false_on_a_bad_reply(monkeypatch):
    _serve(monkeypatch, lambda request: httpx.Response(200, text="not json"))
    assert not await model_available("gemma2:9b")
    _serve(monkeypatch, lambda request: httpx.Response(500))
    assert not await model_available("gemma2:9b")


async def test_unload_model_asks_ollama_to_drop_it(monkeypatch):
    sent = []

    def handler(request):
        sent.append((str(request.url), json.loads(request.content)))
        return httpx.Response(200, json={})

    _serve(monkeypatch, handler)
    assert await bakeoff.unload_model("qwen3:14b")
    assert sent == [
        ("http://localhost:11434/api/generate", {"model": "qwen3:14b", "keep_alive": 0})
    ]


async def test_unload_failure_is_a_warning_not_an_error(monkeypatch, capsys):
    def handler(request):
        raise httpx.ConnectError("refused")

    _serve(monkeypatch, handler)
    assert not await bakeoff.unload_model("qwen3:14b")
    assert "warning" in capsys.readouterr().err


async def test_unavailable_model_is_reported_not_fatal(monkeypatch, tmp_path, probes):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a"}))
    rows = await run_bakeoff(["a", "b"], args_stub(tmp_path), scorer=fake_scorer)
    assert [r["status"] for r in rows] == ["ok", "unavailable"]
    assert rows[1]["message"] and rows[1]["hard_pass"] is None
    assert probes.built == [("a", "http://localhost:11434/v1")]  # b was never built


async def test_row_carries_latency_memory_quality_and_scorecard_path(monkeypatch, tmp_path, probes):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a"}))
    [row] = await run_bakeoff(["a"], args_stub(tmp_path), scorer=fake_scorer)
    assert row | {"scorecard": None} == {
        "model": "a",
        "status": "ok",
        "message": None,
        "first_sentence_p50_ms": 300.0,
        "first_sentence_p95_ms": 500.0,
        "first_sentence_samples": 30,
        "margin_ms": None,
        "gpu_mb": 8000,
        "hard_pass": 0.9,
        "task_pass": 0.8,
        "full_pass": 0.75,
        "n": 20,
        "judged_mean": 4.1,
        "bangla_purity": 0.97,
        "scorecard": None,
    }
    saved = Path(row["scorecard"])
    assert saved.parent == tmp_path and json.loads(saved.read_text())["meta"]["model"] == "a"


async def test_the_scorer_gets_the_warmed_candidate_and_the_chosen_scenarios(
    monkeypatch, tmp_path, probes
):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a"}))
    got = {}

    async def scorer(model, args, **kwargs):
        got.update(kwargs, model=model)
        return CARD

    await run_bakeoff(["a"], args_stub(tmp_path), scorer=scorer, scenarios=["s1"])
    assert got["agent_llm"] is probes.llm and got["scenarios"] == ["s1"] and got["model"] == "a"
    assert probes.llm.closed  # the bake-off built it, so the bake-off closes it


async def test_a_model_whose_scoring_raises_gets_an_error_row_and_the_run_continues(
    monkeypatch, tmp_path, probes
):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a", "b"}))

    async def scorer(model, args, **kwargs):
        if model == "a":
            raise RuntimeError("out of memory")
        return CARD

    rows = await run_bakeoff(["a", "b"], args_stub(tmp_path), scorer=scorer)
    assert [r["status"] for r in rows] == ["error", "ok"]
    assert "out of memory" in rows[0]["message"] and rows[0]["scorecard"] is None
    assert rows[0]["first_sentence_p95_ms"] == 500.0  # what was measured before the failure stays


async def test_a_failing_latency_probe_is_an_error_row(monkeypatch, tmp_path, probes):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a"}))

    async def broken(llm, prompts, concurrency=3, rounds=10):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(bakeoff, "first_sentence_latency", broken)
    [row] = await run_bakeoff(["a"], args_stub(tmp_path), scorer=fake_scorer)
    assert row["status"] == "error" and "ConnectError" in row["message"]
    assert probes.llm.closed


async def test_each_candidate_is_unloaded_after_its_run_even_when_it_fails(
    monkeypatch, tmp_path, probes
):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a", "b"}))

    async def scorer(model, args, **kwargs):
        if model == "a":
            raise RuntimeError("boom")
        return CARD

    await run_bakeoff(["a", "b"], args_stub(tmp_path), scorer=scorer)
    assert [m for m in probes.unloaded if m in {"a", "b"}] == ["a", "b"]


async def test_side_models_on_ollama_are_unloaded_too_but_not_elsewhere(
    monkeypatch, tmp_path, probes
):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a"}))
    await run_bakeoff(["a"], args_stub(tmp_path), scorer=fake_scorer)
    assert set(probes.unloaded) == {"a", "judge", "caller"}
    probes.unloaded.clear()
    other = args_stub(tmp_path, side_base_url="http://localhost:8001/v1")
    await run_bakeoff(["a"], other, scorer=fake_scorer)
    assert probes.unloaded == ["a"]


async def test_gpu_reading_is_none_when_there_is_no_card(monkeypatch, tmp_path, probes):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a"}))
    monkeypatch.setattr(bakeoff, "gpu_memory_mb", lambda: None)
    [row] = await run_bakeoff(["a"], args_stub(tmp_path), scorer=fake_scorer)
    assert row["status"] == "ok" and row["gpu_mb"] is None


def test_table_lists_every_row_and_the_winner():
    rows = [
        {
            "model": "a",
            "status": "ok",
            "first_sentence_p50_ms": 310.0,
            "first_sentence_p95_ms": 480.0,
            "gpu_mb": 8000,
            "hard_pass": 0.9,
            "judged_mean": 4.1,
            "bangla_purity": 0.97,
            "message": None,
        },
        {
            "model": "b",
            "status": "unavailable",
            "message": "not in Ollama",
            "first_sentence_p50_ms": None,
            "first_sentence_p95_ms": None,
            "gpu_mb": None,
            "hard_pass": None,
            "judged_mean": None,
            "bangla_purity": None,
        },
    ]
    text = bakeoff.table(rows, "a", 400.0, 1200)
    assert "a" in text and "480" in text and "8000" in text and "0.900" in text
    assert "unavailable" in text and "not in Ollama" in text
    assert "Winner: a" in text
    assert "No winner: no model finished" in bakeoff.table(rows[1:], None, 400.0, 1200)
    ok = [rows[0]]
    assert "voice's first-sentence time was not measured" in bakeoff.table(ok, None, None, 1200)
    inconclusive = bakeoff.table(ok, None, 900.0, 1200)
    assert "fits within 1200 ms" in inconclusive
    assert "No winner (inconclusive: re-run or raise --rounds)" in inconclusive


async def test_bake_picks_the_winner_with_the_voice_time_and_saves_json(
    monkeypatch, tmp_path, probes
):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a"}))

    async def tts():
        return 400.0

    result = await bakeoff.bake(["a", "b"], args_stub(tmp_path), scorer=fake_scorer, tts_timer=tts)
    assert result["winner"] == "a" and result["tts_first_ms"] == 400.0
    assert result["budget_ms"] == 1200 and result["tags"] == "bakeoff"
    saved = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
    assert Path(result["path"]).name.startswith("bakeoff-")
    assert [r["status"] for r in saved["rows"]] == ["ok", "unavailable"]
    assert saved["winner"] == "a" and saved["tts_first_ms"] == 400.0 and saved["budget_ms"] == 1200
    assert saved["rows"][0]["scorecard"]


async def test_bake_with_nothing_to_time_skips_the_voice_and_has_no_winner(
    monkeypatch, tmp_path, probes
):
    monkeypatch.setattr(bakeoff, "model_available", fake_available(set()))

    async def tts():
        raise AssertionError("no voice time is needed when no model ran")

    result = await bakeoff.bake(["x"], args_stub(tmp_path), scorer=fake_scorer, tts_timer=tts)
    assert result["winner"] is None and result["tts_first_ms"] is None


async def test_bake_without_a_voice_time_reports_no_winner(monkeypatch, tmp_path, probes, capsys):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a"}))

    async def tts():
        raise RuntimeError("no voice model")

    result = await bakeoff.bake(["a"], args_stub(tmp_path), scorer=fake_scorer, tts_timer=tts)
    assert result["winner"] is None and result["tts_first_ms"] is None
    assert "voice" in capsys.readouterr().err


async def test_with_voice_loads_recognition_and_voice_before_any_candidate(
    monkeypatch, tmp_path, probes
):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a"}))
    order = []

    async def load_voice():
        order.append("voice")

    async def scorer(model, args, **kwargs):
        order.append("score")
        return CARD

    async def tts():
        order.append("tts")
        return 300.0

    await bakeoff.bake(
        ["a"],
        args_stub(tmp_path, with_voice=True),
        scorer=scorer,
        tts_timer=tts,
        voice_loader=load_voice,
    )
    assert order == ["voice", "tts", "score"]


async def test_without_the_voice_option_the_voice_is_timed_after_the_candidates(
    monkeypatch, tmp_path, probes
):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a"}))
    order = []

    async def scorer(model, args, **kwargs):
        order.append("score")
        return CARD

    async def tts():
        order.append("tts")
        return 300.0

    await bakeoff.bake(["a"], args_stub(tmp_path), scorer=scorer, tts_timer=tts)
    assert order == ["score", "tts"]


async def test_measure_tts_first_ms_is_the_median_after_a_warm_up(monkeypatch):
    clock = iter([0.0, 0.5, 10.0, 10.3, 20.0, 20.1, 30.0, 30.2])
    synthesised = []

    class Frame:
        pass

    class Voice:
        async def synthesize_stream(self, text, language):
            synthesised.append((text, language))
            yield Frame()
            yield Frame()

    class FakeRegistry:
        async def get_tts(self):
            return Voice()

    monkeypatch.setattr("shefa.models.registry.registry", FakeRegistry())
    # the warm-up (0 to 0.5 s) is discarded; the timed runs took 300, 100 and 200 ms
    assert await bakeoff.measure_tts_first_ms(clock=lambda: next(clock)) == pytest.approx(200.0)
    assert len(synthesised) == 4 and synthesised[0][1] == "bn"


class TestBakeoffCommand:
    def _scenarios(self, tmp_path, tags=("bakeoff",)):
        path = tmp_path / "s.yaml"
        path.write_text(
            json.dumps(
                [{"id": "a", "title": "a", "tests": "x", "turns": ["হ্যালো"], "tags": list(tags)}]
            ),
            encoding="utf-8",
        )
        return path

    def test_parses_models_and_the_documented_defaults(self):
        args = cli.build_parser().parse_args(
            ["lab", "bakeoff", "gemma2:9b", "qwen3:14b", "--with-voice"]
        )
        assert (args.lab_command, args.models, args.with_voice) == (
            "bakeoff",
            ["gemma2:9b", "qwen3:14b"],
            True,
        )
        assert args.tags == "bakeoff" and args.out == "data/bench" and args.mishear == 0.15
        assert args.base_url == args.side_base_url == "http://localhost:11434/v1"
        assert args.rounds == 10

    def test_the_side_server_is_separate_from_the_candidates(self):
        args = cli.build_parser().parse_args(
            [
                "lab",
                "bakeoff",
                "m",
                "--side-base-url",
                "http://localhost:8001/v1",
                "--caller-model",
                "shefa-llm",
                "--judge-model",
                "shefa-llm",
            ]
        )
        assert args.side_base_url == "http://localhost:8001/v1" and args.base_url.endswith(
            ":11434/v1"
        )

    def test_at_least_one_model_is_required(self, capsys):
        with pytest.raises(SystemExit):
            cli.build_parser().parse_args(["lab", "bakeoff"])

    def test_no_case_with_the_default_tag_is_exit_2_and_says_how_to_choose(self, tmp_path, capsys):
        path = self._scenarios(tmp_path, tags=())
        assert cli.main(["lab", "bakeoff", "m", "--scenarios", str(path)]) == 2
        err = capsys.readouterr().err
        assert "bakeoff" in err and "--tags" in err

    def test_rounds_must_be_positive(self, capsys):
        assert cli.main(["lab", "bakeoff", "m", "--rounds", "0"]) == 2
        assert "--rounds" in capsys.readouterr().err

    def test_a_bad_mishear_rate_is_exit_2(self, tmp_path, capsys):
        assert cli.main(["lab", "bakeoff", "m", "--mishear", "2"]) == 2
        assert "mishear" in capsys.readouterr().err

    def test_a_bad_labels_file_is_exit_2_before_any_model_runs(self, tmp_path, capsys, monkeypatch):
        path = self._scenarios(tmp_path)
        out = tmp_path / "bench"
        out.mkdir()
        (out / "human_labels.json").write_text("{oops")

        async def never(*a, **k):
            raise AssertionError("no model should run")

        monkeypatch.setattr(bakeoff, "bake", never)
        code = cli.main(
            ["lab", "bakeoff", "m", "--scenarios", str(path), "--out", str(out), "--mishear", "0"]
        )
        assert code == 2 and "human_labels.json" in capsys.readouterr().err

    def test_a_run_prints_the_table_and_resets_the_registry(self, tmp_path, capsys, monkeypatch):
        from shefa.models.registry import registry

        path = self._scenarios(tmp_path)
        seen = {}
        resets = []

        async def fake_bake(models, args, **kwargs):
            seen.update(models=models, scenarios=kwargs["scenarios"])
            rows = [
                {
                    "model": "m",
                    "status": "unavailable",
                    "message": "not in Ollama",
                    "first_sentence_p50_ms": None,
                    "first_sentence_p95_ms": None,
                    "gpu_mb": None,
                    "hard_pass": None,
                    "judged_mean": None,
                    "bangla_purity": None,
                }
            ]
            return {
                "rows": rows,
                "winner": None,
                "tts_first_ms": None,
                "budget_ms": 1200,
                "path": str(tmp_path / "bakeoff-x.json"),
            }

        async def reset():
            resets.append(True)

        monkeypatch.setattr(bakeoff, "bake", fake_bake)
        monkeypatch.setattr(registry, "reset", reset)
        code = cli.main(
            [
                "lab",
                "bakeoff",
                "m",
                "--scenarios",
                str(path),
                "--out",
                str(tmp_path),
                "--mishear",
                "0",
            ]
        )
        out = capsys.readouterr().out
        assert code == 1 and resets  # no model was scored
        assert "not in Ollama" in out and "No winner" in out and "bakeoff-x.json" in out
        assert seen["models"] == ["m"] and [s.id for s in seen["scenarios"]] == ["a"]


async def test_rounds_from_the_options_reach_the_probe(monkeypatch, tmp_path, probes):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a"}))
    await run_bakeoff(["a"], args_stub(tmp_path, rounds=25), scorer=fake_scorer)
    await run_bakeoff(["a"], args_stub(tmp_path), scorer=fake_scorer)
    assert probes.rounds == [25, 10]


async def test_unloading_says_which_models(monkeypatch, tmp_path, probes, capsys):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a"}))
    await run_bakeoff(["a"], args_stub(tmp_path), scorer=fake_scorer)
    assert "unloading a, caller, judge from Ollama" in capsys.readouterr().out


async def test_bake_records_samples_and_margin_per_measured_row(monkeypatch, tmp_path, probes):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a", "b"}))
    p95 = {"a": 500.0, "b": 900.0}

    async def latency(llm, prompts, concurrency=3, rounds=10):
        return {"p50_ms": 1.0, "p95_ms": p95[probes.built[-1][0]], "samples": 30}

    monkeypatch.setattr(bakeoff, "first_sentence_latency", latency)

    async def tts():
        return 400.0

    result = await bakeoff.bake(
        ["a", "b", "c"], args_stub(tmp_path), scorer=fake_scorer, tts_timer=tts
    )
    a, b, c = result["rows"]
    assert (a["first_sentence_samples"], a["margin_ms"]) == (30, 300.0)  # 1200 - (500 + 400)
    assert b["margin_ms"] == -100.0  # over budget by 100 ms
    assert c["margin_ms"] is None and c["status"] == "unavailable"
    assert result["winner"] == "a" and result["complete"] is True and result["rounds"] == 10


class Interrupt(BaseException):
    """Stands in for Ctrl-C, which is not an Exception."""


async def test_the_json_is_written_after_each_row_and_survives_an_interrupt(
    monkeypatch, tmp_path, probes
):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a", "b"}))

    async def scorer(model, args, **kwargs):
        if model == "b":
            raise Interrupt
        return {**CARD, "meta": {"model": model, "case_count": 20}}

    async def tts():
        return 400.0

    with pytest.raises(Interrupt):
        await bakeoff.bake(
            ["a", "b"],
            args_stub(tmp_path, with_voice=True),
            scorer=scorer,
            tts_timer=tts,
            voice_loader=_noop,
        )
    [saved] = tmp_path.glob("bakeoff-*.json")
    data = json.loads(saved.read_text(encoding="utf-8"))
    assert data["complete"] is False
    assert [r["model"] for r in data["rows"]] == ["a"] and data["rows"][0]["status"] == "ok"
    assert data["winner"] == "a"  # the winner so far
    assert not list(tmp_path.glob("*.tmp"))


async def _noop():
    return None


async def test_each_row_rewrites_the_same_file_and_the_last_write_is_complete(
    monkeypatch, tmp_path, probes
):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a", "b"}))
    seen = []

    async def scorer(model, args, **kwargs):
        [saved] = tmp_path.glob("bakeoff-*.json") if model == "b" else [None]
        if saved:
            seen.append(json.loads(saved.read_text(encoding="utf-8")))
        return {**CARD, "meta": {"model": model, "case_count": 20}}

    async def tts():
        return 400.0

    result = await bakeoff.bake(["a", "b"], args_stub(tmp_path), scorer=scorer, tts_timer=tts)
    assert len(seen) == 1 and [r["model"] for r in seen[0]["rows"]] == ["a"]
    assert seen[0]["complete"] is False and seen[0]["winner"] is None  # voice not timed yet
    [final] = tmp_path.glob("bakeoff-*.json")
    data = json.loads(final.read_text(encoding="utf-8"))
    assert data["complete"] is True and len(data["rows"]) == 2 and str(final) == result["path"]
    assert [r["status"] for r in data["rows"]] == ["ok", "ok"]

    def test_a_run_where_a_model_was_scored_exits_0(self, tmp_path, monkeypatch):
        from shefa.models.registry import registry

        path = self._scenarios(tmp_path)

        async def fake_bake(models, args, **kwargs):
            row = {
                "model": "m",
                "status": "ok",
                "message": None,
                "first_sentence_p50_ms": 1.0,
                "first_sentence_p95_ms": 2.0,
                "margin_ms": 10.0,
                "gpu_mb": None,
                "hard_pass": 1.0,
                "judged_mean": 4.0,
                "bangla_purity": 1.0,
            }
            return {
                "rows": [row],
                "winner": "m",
                "tts_first_ms": 400.0,
                "budget_ms": 1200,
                "path": "x.json",
            }

        async def reset():
            return None

        monkeypatch.setattr(bakeoff, "bake", fake_bake)
        monkeypatch.setattr(registry, "reset", reset)
        argv = ["lab", "bakeoff", "m", "--scenarios", str(path), "--out", str(tmp_path)]
        assert cli.main([*argv, "--mishear", "0"]) == 0


def _ok_row(model, full, judged=4.0, hard=1.0, task=None, n=25, p95=300.0):
    return {
        "model": model,
        "status": "ok",
        "message": None,
        "first_sentence_p50_ms": p95 - 50,
        "first_sentence_p95_ms": p95,
        "margin_ms": 0.0,
        "gpu_mb": 9000,
        "hard_pass": hard,
        "task_pass": full if task is None else task,
        "full_pass": full,
        "n": n,
        "judged_mean": judged,
        "bangla_purity": 1.0,
    }


def test_pick_winner_ranks_by_full_pass_not_by_hard_pass_alone():
    safe_but_useless = _ok_row("safe", full=0.40, hard=1.0, judged=4.8)
    does_the_job = _ok_row("job", full=0.80, hard=0.85, judged=3.5)
    assert pick_winner([safe_but_useless, does_the_job], 400) == "job"


def test_table_shows_hard_task_full_and_n():
    text = bakeoff.table([_ok_row("a", full=0.6, hard=0.9, task=0.64)], "a", 400.0, 1200)
    header = text.splitlines()[0].split()
    for column in ("hard", "task", "full", "n"):
        assert column in header
    assert "0.640" in text and "0.600" in text and " 25" in text


def test_a_winner_within_one_case_of_the_runner_up_says_to_rerun_the_top_two():
    close = [_ok_row("a", full=0.92), _ok_row("b", full=0.88)]  # 23 v 22 of 25
    text = bakeoff.table(close, pick_winner(close, 400.0), 400.0, 1200)
    assert "Winner: a" in text
    assert "within one case of b: re-run the top two in full" in text
    clear = [_ok_row("a", full=0.92), _ok_row("b", full=0.80)]  # 23 v 20 of 25
    assert "within one case" not in bakeoff.table(clear, "a", 400.0, 1200)
    alone = [_ok_row("a", full=0.92)]
    assert "within one case" not in bakeoff.table(alone, "a", 400.0, 1200)


async def test_the_candidates_are_timed_on_the_products_prompt(monkeypatch, tmp_path, probes):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a"}))
    await run_bakeoff(["a"], args_stub(tmp_path), scorer=fake_scorer)
    assert probes.prompts == bakeoff.probe_prompts("configs/clinic.example.yaml", tmp_path)
    assert probes.warmed == probes.prompts[0]


async def test_the_json_says_which_server_the_latency_was_measured_on(
    monkeypatch, tmp_path, probes
):
    monkeypatch.setattr(bakeoff, "model_available", fake_available({"a"}))

    async def tts():
        return 400.0

    result = await bakeoff.bake(["a"], args_stub(tmp_path), scorer=fake_scorer, tts_timer=tts)
    saved = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
    assert saved["latency_server"] == "ollama" and result["latency_server"] == "ollama"
