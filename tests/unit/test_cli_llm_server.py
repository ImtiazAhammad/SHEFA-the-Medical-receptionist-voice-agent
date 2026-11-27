"""`shefa serve` brings the language model server up: use it if it answers, else start it.

Nothing here starts a real server: the HTTP probe, the process and the clock are fakes.
"""

from __future__ import annotations

import subprocess
import time
import urllib.request

import pytest

from shefa import cli
from shefa.config.settings import settings


class _Server:
    """Answers the probe from its `answers_from`-th call on (never when None)."""

    def __init__(self, answers_from: int | None) -> None:
        self.answers_from = answers_from
        self.probes = 0

    def __call__(self, url, timeout=None):
        self.probes += 1
        if self.answers_from is None or self.probes < self.answers_from:
            raise OSError("connection refused")
        return object()


class _Process:
    def __init__(self, exit_code: int | None = None) -> None:
        self.returncode = exit_code

    def poll(self):
        return self.returncode


@pytest.fixture
def started(monkeypatch):
    """Every Popen call, recorded; the process it returns is `started.process`."""
    calls: list[list[str]] = []

    class Record:
        process = _Process()

    def popen(command, **_kwargs):
        calls.append(command)
        return Record.process

    monkeypatch.setattr(subprocess, "Popen", popen)
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    Record.calls = calls
    return Record


def test_a_running_ollama_is_used_as_it_is(monkeypatch, started):
    monkeypatch.setattr(urllib.request, "urlopen", _Server(answers_from=1))
    cli._ensure_ollama()
    assert started.calls == []


def test_ollama_not_installed_is_said_and_not_started(monkeypatch, started, capsys):
    import shutil

    monkeypatch.setattr(urllib.request, "urlopen", _Server(answers_from=None))
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    cli._ensure_ollama()
    assert started.calls == []
    assert "Ollama is not installed" in capsys.readouterr().out


@pytest.mark.parametrize(("answers_from", "said"), [(3, ""), (None, "Ollama did not start")])
def test_ollama_is_started_and_waited_for(monkeypatch, started, capsys, answers_from, said):
    import shutil

    monkeypatch.setattr(urllib.request, "urlopen", _Server(answers_from=answers_from))
    monkeypatch.setattr(shutil, "which", lambda _name: "/usr/bin/ollama")
    cli._ensure_ollama()
    assert started.calls == [["ollama", "serve"]]
    out = capsys.readouterr().out
    assert "Starting Ollama" in out
    assert (said in out) if said else ("did not start" not in out)


@pytest.fixture
def vllm(monkeypatch, tmp_path):
    """A vLLM config whose python exists, run from a scratch folder (the log goes to data/)."""
    python = tmp_path / "python"
    python.write_text("")
    cfg = settings.llm_server.vllm.model_copy(
        update={"python": str(python), "startup_timeout_s": 30.0}
    )
    monkeypatch.setattr(settings.llm_server, "vllm", cfg)
    monkeypatch.chdir(tmp_path)
    return cfg


def test_a_running_vllm_is_used_as_it_is(monkeypatch, started, vllm):
    monkeypatch.setattr(urllib.request, "urlopen", _Server(answers_from=1))
    cli._ensure_vllm()
    assert started.calls == []


def test_vllm_not_installed_says_how_to_install_it(monkeypatch, started, vllm, capsys):
    monkeypatch.setattr(urllib.request, "urlopen", _Server(answers_from=None))
    monkeypatch.setattr(settings.llm_server, "vllm", vllm.model_copy(update={"python": "/nope"}))
    cli._ensure_vllm()
    assert started.calls == []
    assert "vLLM is not installed" in capsys.readouterr().out


def test_vllm_is_started_and_waited_for_until_ready(monkeypatch, started, vllm, capsys):
    monkeypatch.setattr(urllib.request, "urlopen", _Server(answers_from=3))
    cli._ensure_vllm()
    assert started.calls == [cli.vllm_command(vllm)]
    assert "vLLM is ready." in capsys.readouterr().out


def test_vllm_that_stops_says_why(monkeypatch, started, vllm, tmp_path, capsys):
    monkeypatch.setattr(urllib.request, "urlopen", _Server(answers_from=None))
    started.process = _Process(exit_code=1)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "vllm.log").write_text("[x] ValueError: out of memory\n")
    cli._ensure_vllm()
    out = capsys.readouterr().out
    assert "vLLM stopped (exit 1). ValueError: out of memory" in out


def test_vllm_that_never_answers_gives_up_at_the_deadline(monkeypatch, started, vllm, capsys):
    monkeypatch.setattr(urllib.request, "urlopen", _Server(answers_from=None))
    clock = iter([0.0, 1.0, 99.0])
    monkeypatch.setattr(time, "monotonic", lambda: next(clock))
    cli._ensure_vllm()
    assert "vLLM did not answer within 30s" in capsys.readouterr().out


@pytest.mark.parametrize(("engine", "expected"), [("vllm", "vllm"), ("ollama", "ollama")])
def test_the_configured_engine_is_the_one_brought_up(monkeypatch, engine, expected):
    seen: list[str] = []
    monkeypatch.setattr(settings.llm_server, "engine", engine)
    monkeypatch.setattr(cli, "_ensure_vllm", lambda: seen.append("vllm"))
    monkeypatch.setattr(cli, "_ensure_ollama", lambda: seen.append("ollama"))
    cli._ensure_llm_server()
    assert seen == [expected]


def test_serve_brings_the_model_and_the_directory_up_before_the_server(monkeypatch, capsys):
    import uvicorn

    seen: list[str] = []
    monkeypatch.delenv("SHEFA_SKIP_WARMUP", raising=False)
    monkeypatch.setattr(cli, "_ensure_llm_server", lambda: seen.append("llm"))
    monkeypatch.setattr(cli, "_ensure_directory", lambda: seen.append("directory"))
    monkeypatch.setattr(uvicorn, "run", lambda *_a, **_k: seen.append("server"))
    assert cli.main(["serve", "--port", "8123"]) == 0
    assert seen == ["llm", "directory", "server"]
    assert "http://127.0.0.1:8123/app" in capsys.readouterr().out


@pytest.mark.parametrize(("ok", "code"), [(True, 0), (False, 1)])
def test_selftest_prints_each_check_and_fails_on_any(monkeypatch, capsys, ok, code):
    from types import SimpleNamespace

    from shefa import selftest

    checks = [SimpleNamespace(ok=True, name="model", detail="answers"),
              SimpleNamespace(ok=ok, name="disk", detail="room")]  # fmt: skip
    seen: list[bool] = []
    monkeypatch.setattr(selftest, "run", lambda full: seen.append(full) or checks)
    assert cli.main(["selftest", "--quick"]) == code
    assert seen == [False]
    out = capsys.readouterr().out
    assert "ok   model" in out and ("ok   disk" if ok else "FAIL disk") in out


def test_collect_hands_over_to_the_collector_command(monkeypatch):
    from shefa.collector import cli as collector_cli

    seen: list[str] = []
    monkeypatch.setattr(collector_cli, "run", lambda args: seen.append(args.collect_command) or 0)
    assert cli.main(["collect", "init"]) == 0
    assert seen == ["init"]
