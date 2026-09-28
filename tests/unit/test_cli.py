"""Tests for the `sefa` command-line entry points.

`pyproject.toml` declared `sefa = "sefa.main:app"`, which resolves to a FastAPI
application object: running `sefa bench` would have handed a string to a web
server. The console script has to dispatch on a subcommand.

T5 and T6 both verify through this CLI, so its exit codes are part of the
contract: `bench` must exit non-zero on an abort, or CI cannot gate on it.
"""

from __future__ import annotations

import importlib
import sys
from types import SimpleNamespace

import pytest

from sefa import cli


class TestArgumentParsing:
    def test_no_arguments_prints_usage_and_fails(self, capsys):
        code = cli.main([])

        assert code != 0
        assert "usage" in capsys.readouterr().out.lower()

    def test_an_unknown_command_fails(self, capsys):
        assert cli.main(["frobnicate"]) != 0
        assert "invalid choice" in capsys.readouterr().err

    def test_bench_is_a_known_command(self):
        assert cli.main(["--help"]) == 0


class TestBenchCommand:
    def test_prints_the_report(self, capsys, monkeypatch):
        monkeypatch.setattr(
            cli,
            "run_bench",
            _bench_returning("sefa bench  warm p50 0.100s  p95 0.200s\nPASS", passed=True),
        )

        code = cli.main(["bench", "--iterations", "2"])

        assert code == 0
        assert "warm p50" in capsys.readouterr().out

    def test_exits_non_zero_on_an_abort(self, capsys, monkeypatch):
        monkeypatch.setattr(
            cli,
            "run_bench",
            _bench_returning(
                "sefa bench\nABORT\n  - p50 1.500s exceeds 1.20s",
                passed=False,
            ),
        )

        code = cli.main(["bench"])

        assert code == 1
        assert "ABORT" in capsys.readouterr().out

    def test_defaults_to_enough_iterations_for_a_real_percentile(self, monkeypatch):
        """A 95th percentile over three samples is not a 95th percentile."""
        captured: list[int] = []
        monkeypatch.setattr(
            cli,
            "run_bench",
            _capturing_report(captured),
        )

        cli.main(["bench"])

        assert captured[0] >= 20

    def test_honours_an_explicit_iteration_count(self, monkeypatch):
        captured: list[int] = []
        monkeypatch.setattr(cli, "run_bench", _capturing_report(captured))

        cli.main(["bench", "--iterations", "50"])

        assert captured[0] == 50

    def test_rejects_a_nonsense_iteration_count(self, capsys):
        assert cli.main(["bench", "--iterations", "0"]) != 0
        assert "iterations" in capsys.readouterr().err.lower()

    def test_can_skip_the_vram_check(self, monkeypatch):
        captured: list[bool] = []

        def run_bench(**kwargs):
            captured.append(kwargs["vram"])
            return "sefa bench\nPASS", True

        monkeypatch.setattr(cli, "run_bench", run_bench)

        cli.main(["bench", "--no-vram"])

        assert captured[0] is False


def _bench_returning(text: str, passed: bool = True):
    def run_bench(**kwargs):
        return text, passed

    return run_bench


def _capturing_report(iterations: list[int], vram: list[bool] | None = None):
    def run_bench(**kwargs):
        iterations.append(kwargs["iterations"])
        if vram is not None:
            vram.append(kwargs["vram"])
        return "sefa bench\nPASS", True

    return run_bench


class TestDoctorCommand:
    def test_reports_a_missing_bangla_voice_as_a_blocker(self, capsys, monkeypatch):
        """T5 is blocked on external licensing; `doctor` must say so out loud
        rather than the pilot starting with an English voice and no warning."""
        monkeypatch.setattr(
            cli,
            "doctor_report",
            _doctor_returning("  BLOCKER  bn voice missing: bn_BD.nf_cycgan.onnx"),
        )

        code = cli.main(["doctor"])

        assert code == 1
        assert "BLOCKER" in capsys.readouterr().out

    def test_passes_when_nothing_is_blocked(self, capsys, monkeypatch):
        monkeypatch.setattr(cli, "doctor_report", _doctor_returning("  ok  voice loaded"))

        assert cli.main(["doctor"]) == 0


def _doctor_returning(text: str):
    def doctor_report(**kwargs):
        return text, "BLOCKER" not in text

    return doctor_report


class FakeChunk:
    def __init__(self, payload: bytes = b"pcm" * 64):
        self.sample_rate = 22050
        self.sample_width = 2
        self.sample_channels = 1
        self.audio_int16_bytes = payload


class FakeVoice:
    """Stands in for a loaded piper voice without the onnxruntime dependency."""

    def __init__(self, *args, **kwargs):
        self.closed = False

    def synthesize(self, text: str, syn_config=None):
        yield FakeChunk(f"pcm:{len(text)}".encode().ljust(192, b"\0"))


class FakeTTS:
    def __init__(self, per_call_seconds: float = 0.0):
        self.per_call_seconds = per_call_seconds
        self.texts: list[str] = []
        self.closed = False

    async def synthesize(self, text: str, language: str = "en"):
        self.texts.append(text)
        if self.per_call_seconds:
            import time as _time

            _time.sleep(self.per_call_seconds)
        return SimpleNamespace(audio_bytes=b"pcm" * 128, sample_rate=22050)

    async def close(self) -> None:
        self.closed = True


class TestRunBench:
    """`run_bench` must build the configured adapter and hand it real work.

    The argument-parsing tests monkeypatch this out, so without these the whole
    function — the async registry call included — would ship untested. That call
    is exactly the part that breaks: a registry that must be awaited.
    """

    def test_awaits_the_registry_adapter_and_renders_a_pass(self, monkeypatch):
        tts = FakeTTS()
        monkeypatch.setattr("sefa.models.registry.registry._create_tts", _returns(tts))
        monkeypatch.setattr("sefa.bench.read_vram_fraction", lambda: None)

        text, passed = cli.run_bench(iterations=3, vram=False)

        assert passed is True
        assert "PASS" in text
        assert "sefa bench" in text
        assert len(tts.texts) == 4

    def test_times_one_extra_utterance_to_separate_the_cold_start(self, monkeypatch):
        tts = FakeTTS()
        monkeypatch.setattr("sefa.models.registry.registry._create_tts", _returns(tts))
        monkeypatch.setattr("sefa.bench.read_vram_fraction", lambda: None)

        cli.run_bench(iterations=3, vram=False)

        # The first call pays the model load; it must not pollute the warm p95.
        assert len(tts.texts) == 4

    def test_cycles_through_the_bench_corpus(self, monkeypatch):
        tts = FakeTTS()
        monkeypatch.setattr("sefa.models.registry.registry._create_tts", _returns(tts))
        monkeypatch.setattr("sefa.bench.read_vram_fraction", lambda: None)

        iterations = len(cli.BENCH_TEXTS) + 2
        cli.run_bench(iterations=iterations, vram=False)

        # The first utterance pays the cold start, then the corpus repeats.
        assert tts.texts == [
            cli.BENCH_TEXTS[index % len(cli.BENCH_TEXTS)]
            for index in range(iterations + 1)
        ]

    def test_reports_a_failure_when_a_threshold_is_missed(self, monkeypatch):
        # 0.5s per call is past the 1.2s p50 budget once averaged over the corpus.
        tts = FakeTTS(per_call_seconds=0.05)
        monkeypatch.setattr("sefa.models.registry.registry._create_tts", _returns(tts))
        monkeypatch.setattr("sefa.bench.read_vram_fraction", lambda: None)

        text, passed = cli.run_bench(iterations=2, vram=False)

        assert passed is True  # 50ms is genuinely inside budget

        slow = FakeTTS(per_call_seconds=1.5)
        monkeypatch.setattr("sefa.models.registry.registry._create_tts", _returns(slow))
        text, passed = cli.run_bench(iterations=2, vram=False)

        assert passed is False
        assert "ABORT" in text

    def test_rejects_a_zero_iteration_count(self):
        assert cli.main(["bench", "--iterations", "0"]) == 2


class TestDoctorReport:
    """`doctor` is the gate on the T5 blocker, so it has to be trustworthy."""

    def _patch_voice_path(self, monkeypatch, voice: str) -> None:
        """Patch the settings object behind the `sefa.config.settings` module.

        `sefa/config/__init__.py` rebinds the name `settings` on the package to
        the AppConfig instance, so a dotted `sefa.config.settings.settings` path
        resolves to that instance. The module is still the import target used
        inside `doctor_report`, so that is what has to be patched.
        """
        module = importlib.import_module("sefa.config.settings")
        monkeypatch.setattr(
            module,
            "settings",
            SimpleNamespace(pipeline=SimpleNamespace(tts=SimpleNamespace(voice_path=voice))),
        )

    def test_reports_ok_when_the_voice_loads_and_synthesises(self, monkeypatch, tmp_path):
        voice = tmp_path / "voice.onnx"
        voice.write_bytes(b"stub")
        (tmp_path / "models" / "piper").mkdir(parents=True)
        (tmp_path / "models" / "piper" / "bn_BD.nf_cycgan.onnx").write_bytes(b"stub")
        self._patch_voice_path(monkeypatch, str(voice))
        monkeypatch.setattr(
            "sefa.models.tts.piper_tts.PiperVoice", type("V", (), {"load": FakeVoice})
        )
        monkeypatch.chdir(tmp_path)

        text, ok = cli.doctor_report()

        assert ok is True
        assert "BLOCKER" not in text
        assert "voice synthesised" in text

    def test_flags_a_missing_voice_file(self, monkeypatch, tmp_path):
        self._patch_voice_path(monkeypatch, str(tmp_path / "gone.onnx"))
        monkeypatch.setattr(
            "sefa.models.tts.piper_tts.PiperVoice", type("V", (), {"load": FakeVoice})
        )

        text, ok = cli.doctor_report()

        assert ok is False
        assert "BLOCKER  voice missing" in text

    def test_flags_the_bangla_voice_while_t5_is_open(self, monkeypatch, tmp_path):
        voice = tmp_path / "voice.onnx"
        voice.write_bytes(b"stub")
        self._patch_voice_path(monkeypatch, str(voice))
        monkeypatch.setattr(
            "sefa.models.tts.piper_tts.PiperVoice", type("V", (), {"load": FakeVoice})
        )
        monkeypatch.chdir(tmp_path)  # no Bangla model here

        text, ok = cli.doctor_report()

        assert ok is False
        assert "bn_BD.nf_cycgan.onnx" in text

    def test_passes_once_the_bangla_voice_is_present(self, monkeypatch, tmp_path):
        voice = tmp_path / "voice.onnx"
        voice.write_bytes(b"stub")
        (tmp_path / "models" / "piper").mkdir(parents=True)
        (tmp_path / "models" / "piper" / "bn_BD.nf_cycgan.onnx").write_bytes(b"stub")
        self._patch_voice_path(monkeypatch, str(voice))
        monkeypatch.setattr(
            "sefa.models.tts.piper_tts.PiperVoice", type("V", (), {"load": FakeVoice})
        )
        monkeypatch.chdir(tmp_path)

        _text, ok = cli.doctor_report()

        assert ok is True

    def test_reports_a_voice_that_fails_to_synthesise(self, monkeypatch, tmp_path):
        voice = tmp_path / "voice.onnx"
        voice.write_bytes(b"stub")
        self._patch_voice_path(monkeypatch, str(voice))

        class BrokenVoice:
            def __init__(self, *args, **kwargs):
                pass

            def synthesize(self, text, syn_config=None):
                raise RuntimeError("corrupt onnx graph")

        monkeypatch.setattr(
            "sefa.models.tts.piper_tts.PiperVoice", type("V", (), {"load": BrokenVoice})
        )

        text, ok = cli.doctor_report()

        assert ok is False
        assert "failed to synthesise" in text
        assert "corrupt onnx graph" in text


def _returns(value):
    async def create_tts():
        return value

    return create_tts


class TestTokenCommand:
    """`sefa token` is how an operator onboard a principal without touching code.

    T7 removed the fake `.env` keys, so a token has to come from somewhere safe;
    from the CLI it is printed once and stored as a PBKDF2 record, never as the
    token itself.
    """

    def test_token_is_a_known_command(self, capsys):
        assert cli.main(["token", "--help"]) == 0

    def test_minting_requires_a_name(self, capsys):
        assert cli.main(["token", "--role", "clinician"]) != 0
        assert "name" in (capsys.readouterr().err or capsys.readouterr().out).lower()

    def test_minting_requires_a_role(self, capsys):
        assert cli.main(["token", "--name", "front-desk"]) != 0

    def test_an_unknown_role_is_refused(self, capsys, monkeypatch):
        self._patch_roles(monkeypatch, {"clinician": ["calls:place"]})

        code = cli.main(["token", "--name", "front-desk", "--role", "admin"])

        assert code != 0
        assert "not a configured role" in capsys.readouterr().err

    def test_mint_prints_a_token_and_a_paste_ready_record(self, capsys, monkeypatch):
        self._patch_roles(
            monkeypatch, {"clinician": ["sessions:read", "calls:place", "chat:use"]}
        )
        monkeypatch.setattr("sefa.auth.generate_token", lambda *_: "s" * 40)

        code = cli.main(["token", "--name", "front-desk", "--role", "clinician"])

        assert code == 0
        out = capsys.readouterr().out
        assert "s" * 40 in out
        assert "front-desk" in out
        assert "clinician" in out

    def test_the_record_holds_a_hash_that_verifies(self, monkeypatch):
        """The printed token must actually work against the printed record.

        Minting a token and hashing a different one would hand the operator a
        credential that fails on the first request.
        """
        from sefa.auth import verify_token

        token, record = cli.token_mint("front-desk", "clinician")

        assert verify_token(token, record)
        assert len(token) >= 24

    def test_token_mint_hashes_the_token_not_stored_plaintext(self, monkeypatch):
        """The record on disk must never contain the token that has to stay secret."""
        minted = cli.token_mint("front-desk", "clinician")
        assert len(minted) == 2
        token, record = minted
        assert token not in record
        assert record.startswith("pbkdf2_sha256$")

    def test_minting_a_role_not_in_settings_fails(self, monkeypatch):
        self._patch_roles(monkeypatch, {})

        code = cli.main(["token", "--name", "front-desk", "--role", "admin"])

        assert code != 0

    @staticmethod
    def _patch_roles(monkeypatch, roles: dict) -> None:
        import importlib

        module = importlib.import_module("sefa.config.settings")
        monkeypatch.setattr(
            module, "settings", SimpleNamespace(auth=SimpleNamespace(roles=roles))
        )


class TestModuleEntryPoint:
    """`python -m sefa.cli` is how the bench gets run on a target box."""

    def test_dispatches_through_run_path(self, monkeypatch, capsys):
        """Execute the file the way `python -m sefa.cli` does.

        `run_path` rather than `run_module`: the module is already imported by
        this test file, and re-running it as a module makes runpy warn that
        behaviour may be unpredictable.
        """
        import runpy
        from pathlib import Path

        monkeypatch.setattr("sefa.bench.read_vram_fraction", lambda: None)
        monkeypatch.setattr("sefa.models.registry.registry._create_tts", _returns(FakeTTS()))
        monkeypatch.setattr(sys, "argv", ["sefa", "bench", "--iterations", "1", "--no-vram"])

        with pytest.raises(SystemExit) as exit_request:
            runpy.run_path(str(Path(cli.__file__)), run_name="__main__")

        assert exit_request.value.code == 0
        assert "sefa bench" in capsys.readouterr().out

    def test_a_failing_benchmark_exits_non_zero_from_the_command_line(self, monkeypatch, capsys):
        import runpy
        from pathlib import Path

        monkeypatch.setattr("sefa.bench.read_vram_fraction", lambda: 0.99)
        monkeypatch.setattr(
            "sefa.models.registry.registry._create_tts", _returns(FakeTTS())
        )
        monkeypatch.setattr(sys, "argv", ["sefa", "bench", "--iterations", "1"])

        with pytest.raises(SystemExit) as exit_request:
            runpy.run_path(str(Path(cli.__file__)), run_name="__main__")

        assert exit_request.value.code == 1
        assert "ABORT" in capsys.readouterr().out
