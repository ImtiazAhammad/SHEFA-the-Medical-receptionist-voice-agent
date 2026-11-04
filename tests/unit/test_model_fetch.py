"""`shefa fetch-models`: get a fresh checkout to the point where it can speak.

No network, GPU or Ollama: every downloader, HTTP getter and process runner is injected.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from shefa import cli, model_fetch
from shefa.model_fetch import Check


def _fake_download(name: str, directory: Path) -> None:
    (directory / f"{name}.onnx").write_bytes(b"onnx")
    (directory / f"{name}.onnx.json").write_text("{}")


class TestCheckLine:
    def test_lines_line_up_with_the_doctor_report(self):
        assert Check(True, "voice present").line() == "  ok       voice present"
        assert Check(False, "voice missing").line() == "  BLOCKER  voice missing"


class TestFetchVoice:
    def test_downloads_both_files_into_place(self, tmp_path):
        voice = tmp_path / "piper" / "bn_BD-google-medium.onnx"
        names = []

        def download(name, directory):
            names.append(name)
            _fake_download(name, directory)

        check = model_fetch.fetch_voice(str(voice), download)

        assert check.ok and "downloaded" in check.detail
        assert names == ["bn_BD-google-medium"]
        assert voice.read_bytes() == b"onnx"
        assert (voice.parent / "bn_BD-google-medium.onnx.json").exists()
        assert sorted(p.name for p in voice.parent.iterdir()) == [
            "bn_BD-google-medium.onnx",
            "bn_BD-google-medium.onnx.json",
        ]  # the temporary directory is gone

    def test_a_present_voice_is_not_downloaded_again(self, tmp_path):
        voice = tmp_path / "v.onnx"
        voice.write_bytes(b"x")
        (tmp_path / "v.onnx.json").write_text("{}")

        def download(name, directory):  # pragma: no cover - must not run
            raise AssertionError("downloaded twice")

        assert model_fetch.fetch_voice(str(voice), download).detail.startswith("voice present")

    def test_an_empty_file_counts_as_missing(self, tmp_path):
        voice = tmp_path / "v.onnx"
        voice.write_bytes(b"")
        (tmp_path / "v.onnx.json").write_text("{}")

        assert model_fetch.fetch_voice(str(voice), _fake_download).detail.startswith(
            "voice downloaded"
        )

    def test_a_failed_download_leaves_nothing_half_written(self, tmp_path):
        voice = tmp_path / "piper" / "v.onnx"

        def download(name, directory):
            (directory / f"{name}.onnx").write_bytes(b"trunc")
            raise OSError("connection reset")

        check = model_fetch.fetch_voice(str(voice), download)

        assert not check.ok
        assert "connection reset" in check.detail
        assert list(voice.parent.iterdir()) == []

    def test_the_default_downloader_is_piper_s_own(self, tmp_path, monkeypatch):
        import piper.download_voices

        calls = []
        monkeypatch.setattr(
            piper.download_voices,
            "download_voice",
            lambda name, directory: (calls.append(name), _fake_download(name, directory)),
        )

        assert model_fetch.fetch_voice(str(tmp_path / "bn_BD-x-medium.onnx")).ok
        assert calls == ["bn_BD-x-medium"]


class TestSpeech:
    def test_runtime_check_names_the_extra_to_install(self):
        missing = model_fetch.speech_runtime_check(lambda name: None)
        present = model_fetch.speech_runtime_check(lambda name: object())

        assert not missing.ok and "--extra local-stt-gpu" in missing.detail
        assert present.ok

    def test_a_built_model_is_left_alone(self, tmp_path):
        (tmp_path / "model.bin").write_bytes(b"x")

        check = model_fetch.fetch_speech_model(str(tmp_path), run=None, find_spec=None)

        assert check.ok and "present" in check.detail

    def test_missing_conversion_packages_are_named(self, tmp_path):
        check = model_fetch.fetch_speech_model(
            str(tmp_path / "ct2"),
            find_spec=lambda name: None if name in {"torch", "transformers"} else object(),
        )

        assert not check.ok
        assert "torch, transformers" in check.detail
        assert "uv pip install" in check.detail

    def test_runs_the_conversion_script(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "fetch_stt_model.py").write_text("")
        target = tmp_path / "models" / "ct2"
        commands = []

        def run(command, check):
            commands.append(command)
            target.mkdir(parents=True)
            (target / "model.bin").write_bytes(b"x")
            return SimpleNamespace(returncode=0)

        check = model_fetch.fetch_speech_model(str(target), run, lambda name: object())

        assert check.ok and "built" in check.detail
        assert commands[0][1:] == ["scripts/fetch_stt_model.py", "--target", str(target)]

    def test_a_failed_conversion_is_a_blocker(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "fetch_stt_model.py").write_text("")

        check = model_fetch.fetch_speech_model(
            "models/ct2", lambda command, check: SimpleNamespace(returncode=2), lambda n: object()
        )

        assert not check.ok and "exit 2" in check.detail

    def test_outside_the_repo_the_script_is_reported_missing(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        check = model_fetch.fetch_speech_model("models/ct2", None, lambda name: object())

        assert not check.ok and "not found" in check.detail


class TestLanguageModel:
    def test_a_cloud_provider_needs_its_key(self):
        missing = model_fetch.llm_status("openai", "", "gpt-4o", env={})
        present = model_fetch.llm_status("anthropic", "", "claude", env={"ANTHROPIC_API_KEY": "k"})

        assert not missing.ok and "OPENAI_API_KEY" in missing.detail
        assert present.ok

    def test_a_local_server_that_lists_the_model_passes(self):
        urls = []

        def get_json(url):
            urls.append(url)
            return {"data": [{"id": "gemma2:9b"}, "junk"]}

        check = model_fetch.llm_status(
            "local", "http://h:11434/v1/", "gemma2:9b", get_json=get_json
        )

        assert check.ok
        assert urls == ["http://h:11434/v1/models"]

    def test_a_missing_model_can_be_pulled(self):
        check = model_fetch.llm_status(
            "local", "http://h/v1", "gemma2:9b", get_json=lambda url: {"data": []}
        )

        assert not check.ok and check.pullable
        assert "ollama pull gemma2:9b" in check.detail

    def test_no_server_says_how_to_start_one(self):
        def get_json(url):
            raise ConnectionError("refused")

        check = model_fetch.llm_status("local", "http://h/v1", "m", get_json=get_json)

        assert not check.ok and not check.pullable
        assert "ollama serve" in check.detail

    def test_the_default_getter_reads_json(self, monkeypatch):
        import httpx

        def get(url, timeout):
            return httpx.Response(200, json={"data": []}, request=httpx.Request("GET", url))

        monkeypatch.setattr(httpx, "get", get)

        assert model_fetch._http_get_json("http://h/v1/models") == {"data": []}

    def test_the_check_reads_the_loaded_config(self):
        from shefa.config.settings import settings

        seen = {}

        def get_json(url):
            seen["url"] = url
            return {"data": [{"id": "gemma2:9b"}]}

        assert model_fetch.llm_check_for(settings, get_json=get_json).ok
        assert seen["url"] == "http://localhost:11434/v1/models"

    def test_a_config_without_an_llm_section_is_skipped(self):
        assert model_fetch.llm_check_for(SimpleNamespace()) is None

    def test_an_unresolvable_provider_is_a_blocker(self):
        def resolve(provider):
            raise ValueError("no adapter")

        config = SimpleNamespace(
            pipeline=SimpleNamespace(llm=SimpleNamespace(provider="x")),
            models=SimpleNamespace(resolve_llm_adapter=resolve),
        )

        check = model_fetch.llm_check_for(config)

        assert not check.ok and "no adapter" in check.detail

    def test_pull_needs_ollama_installed(self):
        check = model_fetch.pull_llm("m", which=lambda name: None)

        assert not check.ok and "https://ollama.com" in check.detail

    @pytest.mark.parametrize(("code", "ok"), [(0, True), (1, False)])
    def test_pull_runs_ollama(self, code, ok):
        commands = []

        def run(command, check):
            commands.append(command)
            return SimpleNamespace(returncode=code)

        assert model_fetch.pull_llm("m", lambda name: "/bin/ollama", run).ok is ok
        assert commands == [["ollama", "pull", "m"]]


def _config(stt="whisper_local", tts="piper", model_size="models/stt/ct2"):
    adapter = SimpleNamespace(model="gemma2:9b")
    return SimpleNamespace(
        pipeline=SimpleNamespace(
            tts=SimpleNamespace(provider=tts, voice_path="models/piper/v.onnx"),
            stt=SimpleNamespace(provider=stt),
            llm=SimpleNamespace(provider="local"),
        ),
        models=SimpleNamespace(
            adapters={"stt_whisper_local": SimpleNamespace(model_size=model_size)},
            resolve_llm_adapter=lambda provider: ("llm_local", adapter),
        ),
    )


class TestFetchAll:
    def _run(self, config, **overrides):
        calls = []

        def step(name, result=True):
            def run(*args):
                calls.append(name)
                return Check(result, name)

            return run

        kwargs = {
            "voice_fn": step("voice"),
            "runtime_fn": step("runtime"),
            "speech_fn": step("speech"),
            "llm_fn": step("llm"),
            "pull_fn": step("pull"),
            **overrides,
        }
        return model_fetch.fetch_all(config, **kwargs), calls

    def test_the_local_pipeline_fetches_everything_in_order(self):
        checks, calls = self._run(_config())

        assert calls == ["voice", "runtime", "speech", "llm"]
        assert all(c.ok for c in checks)

    def test_the_demo_profile_only_needs_the_voice_and_a_key(self):
        _checks, calls = self._run(_config(stt="openai"))

        assert calls == ["voice", "llm"]

    def test_a_cloud_voice_needs_no_download(self):
        voice = SimpleNamespace(provider="elevenlabs", voice_path="", voice_id="v")

        assert model_fetch.fetch_voice_for(voice) is None
        assert model_fetch.voice_status(voice) is None

    def test_the_speech_build_can_be_skipped(self):
        checks, calls = self._run(_config(), speech=False)

        assert "speech" not in calls
        assert "skipped" in checks[2].detail and not checks[2].ok

    def test_a_stock_model_name_needs_no_build(self):
        _checks, calls = self._run(_config(model_size="large-v3"))

        assert calls == ["voice", "runtime", "llm"]

    def test_a_missing_model_is_pulled_and_checked_again(self):
        answers = [Check(False, "not pulled", pullable=True), Check(True, "served")]

        checks, calls = self._run(_config(), llm_fn=lambda config: answers.pop(0))

        assert calls[-1] == "pull"
        assert checks[-1].detail == "served"

    def test_a_failed_pull_is_reported(self):
        checks, _calls = self._run(
            _config(),
            llm_fn=lambda config: Check(False, "not pulled", pullable=True),
            pull_fn=lambda model: Check(False, "no ollama"),
        )

        assert checks[-1].detail == "no ollama"

    def test_no_llm_section_adds_no_line(self):
        checks, _calls = self._run(_config(), llm_fn=lambda config: None)

        assert len(checks) == 3


class TestFetchModelsCommand:
    @pytest.mark.parametrize(("ok", "code", "says"), [(True, 0, "shefa serve"), (False, 1, "Fix")])
    def test_prints_each_check_and_exits_on_the_result(self, monkeypatch, capsys, ok, code, says):
        seen = {}

        def fetch_all(config, speech):
            seen["speech"] = speech
            return [Check(True, "voice present"), Check(ok, "language model")]

        monkeypatch.setattr(model_fetch, "fetch_all", fetch_all)

        assert cli.main(["fetch-models", "--skip-speech"]) == code
        out = capsys.readouterr().out
        assert "  ok       voice present" in out
        assert says in out
        assert seen["speech"] is False


class TestSetupDemo:
    def test_demo_profile_moves_speech_and_llm_to_openai(self, tmp_path, monkeypatch, capsys):
        import yaml

        from shefa.config.settings import load_config

        (tmp_path / "configs").mkdir()
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        assert cli.main(["setup", "--demo", "--clinic", "missing.yaml"]) == 0
        out = capsys.readouterr().out
        assert "demos only" in out
        assert "Put OPENAI_API_KEY" in out

        written = yaml.safe_load((tmp_path / "configs" / "local.yaml").read_text())
        assert written["pipeline"]["stt"]["provider"] == "openai"
        assert written["auth"]["principals"][0]["role"] == "admin"

        shipped = Path(__file__).resolve().parents[2] / "configs" / "default.yaml"
        (tmp_path / "configs" / "default.yaml").write_text(shipped.read_text())
        config = load_config(tmp_path / "configs" / "default.yaml")
        assert config.pipeline.llm.provider == "openai"
        assert config.pipeline.llm.tool_calls is False  # the router path, as in production
        assert config.pipeline.tts.provider == "piper"

    def test_demo_note_confirms_a_key_that_is_set(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        assert "OPENAI_API_KEY is set" in cli._demo_note()

    def test_plain_setup_keeps_the_local_pipeline(self, tmp_path, monkeypatch, capsys):
        import yaml

        (tmp_path / "configs").mkdir()
        monkeypatch.chdir(tmp_path)

        assert cli.main(["setup", "--clinic", "missing.yaml"]) == 0
        assert "Demo profile" not in capsys.readouterr().out
        written = yaml.safe_load((tmp_path / "configs" / "local.yaml").read_text())
        assert "pipeline" not in written


class TestDoctorLanguageModel:
    @pytest.mark.parametrize("ok", [True, False])
    def test_doctor_reports_the_language_model(self, monkeypatch, ok):
        monkeypatch.setattr(
            model_fetch, "llm_check_for", lambda config: Check(ok, "language model")
        )

        text, passed = cli.doctor_report()

        assert ("  ok       language model" if ok else "  BLOCKER  language model") in text
        if ok is False:
            assert passed is False


class TestVoicesOfEveryKind:
    def test_configured_voices_are_resolved_and_deduplicated(self):
        from shefa.config.settings import TTSConfig, VoiceConfig

        tts = TTSConfig(
            provider="piper",
            voice_path="bn.onnx",
            voices={
                "bn": VoiceConfig(),
                "en": VoiceConfig(provider="kokoro", voice_id="af_heart"),
            },
        )

        voices = model_fetch.configured_voices(tts)

        assert [(v.provider, v.voice_path or v.voice_id) for v in voices] == [
            ("piper", "bn.onnx"),
            ("kokoro", "af_heart"),
        ]

    def test_fetch_dispatches_by_provider(self, monkeypatch):
        seen = []
        monkeypatch.setattr(model_fetch, "fetch_voice", lambda path: seen.append(path) or "p")
        monkeypatch.setattr(model_fetch, "kokoro_check", lambda v: seen.append(v) or "k")
        monkeypatch.setattr(
            model_fetch, "fetch_vits_voice", lambda d, repo: seen.append((d, repo)) or "v"
        )

        results = [
            model_fetch.fetch_voice_for(SimpleNamespace(provider=p, voice_path="x", voice_id="y",
                                                        model="r"))
            for p in ("piper", "kokoro", "vits")
        ]

        assert results == ["p", "k", "v"]
        assert seen == ["x", "y", ("x", "r")]

    def test_kokoro_needs_its_extra(self):
        missing = model_fetch.kokoro_check("af_heart", lambda name: None)
        present = model_fetch.kokoro_check("af_heart", lambda name: object())

        assert not missing.ok and "--extra kokoro" in missing.detail
        assert present.ok

    def _vits_dir(self, tmp_path):
        directory = tmp_path / "vits"
        directory.mkdir()
        (directory / "best.pth").write_bytes(b"x")
        (directory / "config.json").write_text("{}")
        return directory

    def test_vits_needs_coqui(self, tmp_path):
        check = model_fetch.fetch_vits_voice(str(tmp_path), "repo", lambda name: None)

        assert not check.ok and "--extra bangla-vits" in check.detail

    def test_a_present_vits_voice_is_not_downloaded(self, tmp_path):
        directory = self._vits_dir(tmp_path)

        assert model_fetch.fetch_vits_voice(str(directory), "", lambda n: object()).ok

    def test_a_vits_voice_without_a_repo_cannot_be_fetched(self, tmp_path):
        check = model_fetch.fetch_vits_voice(str(tmp_path / "v"), "", lambda n: object())

        assert not check.ok and "Hugging Face repo" in check.detail

    def test_vits_download_needs_huggingface_hub(self, tmp_path):
        check = model_fetch.fetch_vits_voice(
            str(tmp_path / "v"), "org/voice", lambda n: None if n == "huggingface_hub" else 1
        )

        assert not check.ok and "huggingface_hub" in check.detail

    def test_vits_download(self, tmp_path):
        target = tmp_path / "v"

        def download(repo, directory):
            directory.mkdir()
            (directory / "m.pth").write_bytes(b"x")
            (directory / "config.json").write_text("{}")

        check = model_fetch.fetch_vits_voice(str(target), "org/voice", lambda n: 1, download)

        assert check.ok and "org/voice" in check.detail

    def test_a_vits_download_without_a_config_is_reported(self, tmp_path):
        """The published bangla-speech-processing voices ship a 0-byte config: the
        checkpoint check after download catches a repo that does not hold a voice."""

        def download(repo, directory):
            directory.mkdir()

        check = model_fetch.fetch_vits_voice(str(tmp_path / "v"), "org/x", lambda n: 1, download)

        assert not check.ok and "could not download" in check.detail

    def test_the_default_vits_downloader_is_a_hub_snapshot(self, monkeypatch, tmp_path):
        calls = []
        module = SimpleNamespace(snapshot_download=lambda repo, local_dir: calls.append(
            (repo, local_dir)))
        monkeypatch.setitem(sys.modules, "huggingface_hub", module)

        model_fetch._hf_snapshot("org/voice", tmp_path)

        assert calls == [("org/voice", str(tmp_path))]

    def test_voice_status_never_downloads(self, tmp_path):
        piper = tmp_path / "v.onnx"
        missing = model_fetch.voice_status(SimpleNamespace(provider="piper", voice_path=str(piper)))
        piper.write_bytes(b"x")
        (tmp_path / "v.onnx.json").write_text("{}")
        found = model_fetch.voice_status(SimpleNamespace(provider="piper", voice_path=str(piper)))

        assert not missing.ok and "fetch-models" in missing.detail
        assert found.ok

    def test_voice_status_for_kokoro_and_vits(self, tmp_path):
        kokoro = SimpleNamespace(provider="kokoro", voice_id="af_heart")
        vits_dir = self._vits_dir(tmp_path)
        vits = SimpleNamespace(provider="vits", voice_path=str(vits_dir))
        gone = SimpleNamespace(provider="vits", voice_path=str(tmp_path / "gone"))

        assert model_fetch.voice_status(kokoro, lambda n: None).ok is False
        assert model_fetch.voice_status(vits, lambda n: None).ok is False
        assert model_fetch.voice_status(vits, lambda n: object()).ok is True
        assert model_fetch.voice_status(gone, lambda n: object()).ok is False


class TestDoctorVoices:
    def test_doctor_reports_each_extra_voice(self, monkeypatch):
        monkeypatch.setattr(
            model_fetch,
            "voice_status",
            lambda voice: None if voice.provider == "elevenlabs" else Check(False, "voice x"),
        )
        from shefa.config.settings import VoiceConfig, settings

        monkeypatch.setattr(
            settings.pipeline.tts,
            "voices",
            {"en": VoiceConfig(provider="kokoro"), "xx": VoiceConfig(provider="elevenlabs")},
        )

        text, ok = cli.doctor_report()

        assert "  BLOCKER  en voice x" in text
        assert "xx" not in text
        assert ok is False
