"""Bangla and English in one call: each sentence gets its language's voice, each turn its
language's speech model. No model weights: every engine is a fake."""

from __future__ import annotations

import sys
import unicodedata
from types import SimpleNamespace

import numpy as np
import pytest

from shefa.audio import AudioFrame
from shefa.config.settings import TTSConfig, VoiceConfig, settings
from shefa.models.base import Language, STTResult, TTSResult
from shefa.models.registry import registry
from shefa.models.stt.routed import LanguageRoutedSTT, pick_language
from shefa.models.stt.whisper_local import WhisperLocalSTT
from shefa.models.tts import threaded
from shefa.models.tts.kokoro_tts import KokoroTTS
from shefa.models.tts.routed import LanguageRoutedTTS, script_language
from shefa.models.tts.vits_tts import VITSTTS, checkpoint_files


class _Voice:
    def __init__(self, name):
        self.name = name
        self.spoken: list[tuple[str, str]] = []
        self.closed = 0

    async def synthesize(self, text, language="en"):
        self.spoken.append((text, language))
        return TTSResult(audio_bytes=self.name.encode(), sample_rate=16000)

    async def synthesize_stream(self, text, language="en"):
        self.spoken.append((text, language))
        yield AudioFrame(self.name.encode() * 2)

    async def close(self):
        self.closed += 1


class TestScriptRouting:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("আপনার অ্যাপয়েন্টমেন্ট নিশ্চিত হয়েছে।", "bn"),
            ("Your appointment is confirmed.", "en"),
            ("ডাক্তার Rahman কাল বসবেন।", "bn"),
            ("09:30, 2026-11-05", None),
        ],
    )
    def test_script_language(self, text, expected):
        assert script_language(text) == expected

    async def test_each_sentence_goes_to_the_voice_for_its_script(self):
        bn, en = _Voice("bn"), _Voice("en")
        tts = LanguageRoutedTTS({"bn": bn, "en": en}, default="bn")

        frames = [f async for f in tts.synthesize_stream("Thank you for waiting.", "bn")]
        await tts.synthesize("আপনাকে ধন্যবাদ।", "en")

        assert en.spoken == [("Thank you for waiting.", "en")]
        assert bn.spoken == [("আপনাকে ধন্যবাদ।", "bn")]
        assert frames[0].data == b"enen"

    async def test_numbers_alone_use_the_call_language_then_the_default(self):
        bn, en = _Voice("bn"), _Voice("en")
        tts = LanguageRoutedTTS({"bn": bn, "en": en}, default="bn")

        assert tts.language_for("09:30", "en") == "en"
        assert tts.language_for("09:30", "fr") == "bn"

    async def test_a_shared_voice_is_closed_once(self):
        shared = _Voice("x")
        tts = LanguageRoutedTTS({"bn": shared, "en": shared}, default="bn")

        await tts.close()

        assert shared.closed == 1

    def test_the_default_voice_must_exist(self):
        with pytest.raises(ValueError, match="default voice"):
            LanguageRoutedTTS({"en": _Voice("en")}, default="bn")


class TestVoiceConfig:
    def test_a_language_without_its_own_voice_uses_the_primary_voice(self):
        tts = TTSConfig(provider="piper", voice_path="bn.onnx")

        assert tts.voice_for("en") == VoiceConfig(provider="piper", voice_path="bn.onnx",
                                                  voice_id=tts.voice_id, model=tts.model)

    def test_another_provider_inherits_nothing(self):
        tts = TTSConfig(
            provider="piper",
            voice_path="bn.onnx",
            voices={"en": VoiceConfig(provider="kokoro", voice_id="bf_emma", device="cpu")},
        )

        voice = tts.voice_for("en")

        assert voice == VoiceConfig(provider="kokoro", voice_id="bf_emma", device="cpu")

    def test_the_same_provider_inherits_unset_fields(self):
        tts = TTSConfig(
            provider="piper",
            voice_path="bn.onnx",
            voices={"en": VoiceConfig(voice_path="en.onnx")},
        )

        assert tts.voice_for("en").provider == "piper"
        assert tts.voice_for("en").voice_path == "en.onnx"

    def test_the_shipped_config_gives_english_its_own_voice(self):
        assert settings.pipeline.tts.voice_for("en").provider == "kokoro"
        assert settings.pipeline.tts.voice_for("bn").provider == "piper"


class TestRegistry:
    async def test_configured_voices_build_a_routed_voice(self, monkeypatch):
        monkeypatch.setattr(settings.pipeline.tts, "provider", "piper")
        monkeypatch.setattr(
            settings.pipeline.tts,
            "voices",
            {
                "en": VoiceConfig(provider="kokoro", voice_id="bf_emma", device="cpu"),
                "hi": VoiceConfig(provider="vits", voice_path="models/vits/x", device="cuda"),
                "xx": VoiceConfig(provider="elevenlabs", voice_id="v", model="m"),
            },
        )
        monkeypatch.setattr(settings.languages, "primary", "bn")

        tts = await registry._create_tts()

        assert isinstance(tts, LanguageRoutedTTS)
        assert tts.default == "bn"
        assert tts.voices["bn"].model_path == settings.pipeline.tts.voice_path
        assert (tts.voices["en"].voice, tts.voices["en"].device) == ("bf_emma", "cpu")
        assert (tts.voices["hi"].model_dir, tts.voices["hi"].use_cuda) == ("models/vits/x", True)
        assert tts.voices["xx"].voice_id == "v"
        await tts.voices["xx"].close()

    async def test_an_unknown_voice_provider_is_refused(self, monkeypatch):
        monkeypatch.setattr(settings.pipeline.tts, "voices", {})
        monkeypatch.setattr(settings.pipeline.tts, "provider", "nope")

        with pytest.raises(ValueError, match="Unknown TTS provider"):
            await registry._create_tts()

    async def test_per_language_speech_models_share_one_instance_per_adapter(self, monkeypatch):
        monkeypatch.setattr(settings.pipeline.stt, "provider", "whisper_local")

        stt = await registry._create_stt()

        assert isinstance(stt, LanguageRoutedSTT)
        assert stt.models["en"] is stt.detector
        assert stt.detector.model_size == "small"
        assert stt.models["bn"].model_size == "models/stt/bangla-whisper-medium-ct2"

    async def test_without_per_language_models_it_is_one_whisper(self, monkeypatch):
        monkeypatch.setattr(settings.pipeline.stt, "provider", "whisper_local")
        monkeypatch.setattr(settings.pipeline.stt, "per_language", {})

        stt = await registry._create_stt()

        assert isinstance(stt, WhisperLocalSTT)

    def test_a_speech_role_must_name_a_whisper_adapter(self):
        with pytest.raises(ValueError, match="whisper_local_stt"):
            registry._whisper("llm_local")


class TestLanguagePick:
    @pytest.mark.parametrize(
        ("top", "probability", "probabilities", "expected"),
        [
            ("bn", 0.9, {"bn": 0.9, "en": 0.05}, "bn"),
            ("as", 0.5, {"as": 0.5, "bn": 0.3, "en": 0.1}, "bn"),  # Assamese = Bangla script
            ("en", 0.8, {"en": 0.8, "bn": 0.1}, "en"),
            ("en", 0.7, {}, "en"),
            ("hi", 0.6, {"hi": 0.6, "bn": 0.1, "en": 0.2}, "en"),  # unsure: stay in the pair
            ("hi", 0.95, {"hi": 0.95}, "hi"),  # sure: a third language
        ],
    )
    def test_pick(self, top, probability, probabilities, expected):
        assert pick_language(top, probability, probabilities) == expected


class _Stt:
    def __init__(self, name, detected=("bn", 0.9, {"bn": 0.9})):
        self.name = name
        self.detected = detected
        self.calls: list[str] = []
        self.closed = 0

    async def detect_language(self, audio):
        return self.detected

    async def transcribe(self, audio, language="auto"):
        self.calls.append(language)
        return STTResult(text=self.name, language=Language.ENGLISH, confidence=1.0)

    async def close(self):
        self.closed += 1


class TestRoutedSpeech:
    async def test_a_bangla_turn_goes_to_the_bangla_model(self):
        english, bangla = _Stt("en"), _Stt("bn")
        stt = LanguageRoutedSTT(english, {"bn": bangla, "en": english})

        assert (await stt.transcribe(b"pcm")).text == "bn"
        assert bangla.calls == ["bn"]

    async def test_an_english_turn_goes_to_the_english_model(self):
        english = _Stt("en", ("en", 0.95, {"en": 0.95}))
        stt = LanguageRoutedSTT(english, {"bn": _Stt("bn"), "en": english})

        assert (await stt.transcribe_stream(b"pcm")).text == "en"

    async def test_a_known_language_skips_detection(self):
        english, bangla = _Stt("en", ("en", 1.0, {})), _Stt("bn")
        stt = LanguageRoutedSTT(english, {"bn": bangla, "en": english})

        await stt.transcribe(b"pcm", language="bn")

        assert bangla.calls == ["bn"]

    async def test_a_third_language_is_heard_by_the_multilingual_model(self):
        english = _Stt("multi", ("hi", 0.97, {"hi": 0.97}))
        stt = LanguageRoutedSTT(english, {"bn": _Stt("bn"), "en": english})

        result = await stt.transcribe(b"pcm")

        assert result.text == "multi" and english.calls == ["hi"]

    async def test_close_releases_each_model_once(self):
        english, bangla = _Stt("en"), _Stt("bn")
        stt = LanguageRoutedSTT(english, {"bn": bangla, "en": english})

        await stt.close()

        assert (english.closed, bangla.closed) == (1, 1)


class TestWhisperAdditions:
    def _install(self, monkeypatch, model_cls):
        monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=model_cls))
        return WhisperLocalSTT(device="cpu", compute_type="int8")

    async def test_detect_language_uses_the_encoder_only_api(self, monkeypatch):
        class Model:
            def __init__(self, *args, **kwargs):
                pass

            def detect_language(self, audio):
                return "bn", 0.8, [("bn", 0.8), ("en", 0.1)]

        stt = self._install(monkeypatch, Model)

        assert await stt.detect_language(b"\x00\x00" * 100) == ("bn", 0.8, {"bn": 0.8, "en": 0.1})

    async def test_older_faster_whisper_detects_through_transcribe(self, monkeypatch):
        class Model:
            def __init__(self, *args, **kwargs):
                pass

            def transcribe(self, audio, beam_size):
                info = SimpleNamespace(
                    language="en", language_probability=0.7, all_language_probs=None
                )
                return iter([]), info

        stt = self._install(monkeypatch, Model)

        assert await stt.detect_language(b"\x00\x00" * 100) == ("en", 0.7, {})

    async def test_detection_falls_back_to_cpu(self, monkeypatch):
        built = []

        class Model:
            def __init__(self, size, device, compute_type):
                built.append(device)
                self.device = device

            def detect_language(self, audio):
                if self.device == "cuda":
                    raise RuntimeError("libcublas.so.12")
                return "en", 0.9, []

        monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model))
        monkeypatch.setattr("shefa.models.stt.whisper_local._preload_cuda_libraries", lambda: None)
        stt = WhisperLocalSTT(device="cuda", compute_type="float16")

        assert (await stt.detect_language(b"\x00\x00" * 10))[0] == "en"
        assert built == ["cuda", "cpu"]

    async def test_cpu_detection_failure_propagates(self, monkeypatch):
        class Model:
            def __init__(self, *args, **kwargs):
                pass

            def detect_language(self, audio):
                raise RuntimeError("boom")

        stt = self._install(monkeypatch, Model)

        with pytest.raises(RuntimeError, match="boom"):
            await stt.detect_language(b"\x00\x00" * 10)

    async def test_transcripts_are_nfc_normalised(self, monkeypatch):
        decomposed = unicodedata.normalize("NFD", "আমি কোথায় যাব")  # ো decomposes

        class Model:
            def __init__(self, *args, **kwargs):
                pass

            def transcribe(self, *args, **kwargs):
                segment = SimpleNamespace(text=decomposed, avg_logprob=-0.1, no_speech_prob=0.0)
                info = SimpleNamespace(language="bn", language_probability=0.99, duration=1.0)
                return iter([segment]), info

        stt = self._install(monkeypatch, Model)

        result = await stt.transcribe(b"\x00\x00" * 100)

        assert result.text == unicodedata.normalize("NFC", decomposed)
        assert result.text != decomposed


class TestLocalNeuralVoices:
    def test_float_frames_accept_lists_numpy_and_tensors(self):
        class Tensor:
            def detach(self):
                return self

            def cpu(self):
                return self

            def numpy(self):
                return np.array([0.0, 1.0, -2.0], dtype=np.float32)

        frame = threaded.float_to_frame(Tensor(), 24000)

        assert frame.rate == 24000
        assert np.frombuffer(frame.data, dtype="<i2").tolist() == [0, 32767, -32767]
        assert threaded.float_to_frame([0.5], 16000).data == np.int16(16383).tobytes()

    async def test_kokoro_streams_each_chunk_and_loads_once(self, monkeypatch):
        loads = []

        class Pipeline:
            def __init__(self, lang_code, device):
                loads.append((lang_code, device))

            def __call__(self, text, voice):
                yield ("g", "p", np.zeros(240, dtype=np.float32))
                yield SimpleNamespace(audio=np.ones(240, dtype=np.float32) * 0.1)
                yield SimpleNamespace(audio=None)

        monkeypatch.setitem(sys.modules, "kokoro", SimpleNamespace(KPipeline=Pipeline))
        tts = KokoroTTS(voice="bf_emma", device="cpu")

        frames = [f async for f in tts.synthesize_stream("Hello there.")]
        result = await tts.synthesize("Again.", language="en")
        empty = [f async for f in tts.synthesize_stream("   ")]

        assert loads == [("b", "cpu")]
        assert [f.rate for f in frames] == [24000, 24000]
        assert result.sample_rate == 24000 and result.duration_ms == pytest.approx(20.0)
        assert result.language is Language.ENGLISH
        assert empty == []
        await tts.close()
        assert tts._model is None

    async def test_a_synthesis_error_reaches_the_caller(self, monkeypatch):
        class Pipeline:
            def __init__(self, **kwargs):
                pass

            def __call__(self, text, voice):
                raise RuntimeError("espeak-ng missing")
                yield  # pragma: no cover - makes this a generator

        monkeypatch.setitem(sys.modules, "kokoro", SimpleNamespace(KPipeline=Pipeline))

        with pytest.raises(RuntimeError, match="espeak-ng"):
            await KokoroTTS().synthesize("Hi", language="xx")

    async def test_closing_the_stream_early_stops_the_worker(self, monkeypatch):
        """Barge-in: the worker abandons the reply at the next chunk instead of finishing."""
        import asyncio
        import threading

        resume, finished = threading.Event(), threading.Event()
        produced = []

        class Pipeline:
            def __init__(self, **kwargs):
                pass

            def __call__(self, text, voice):
                try:
                    for index in range(50):
                        produced.append(index)
                        yield ("g", "p", np.ones(10, dtype=np.float32))
                        resume.wait(timeout=5)
                finally:
                    finished.set()

        monkeypatch.setitem(sys.modules, "kokoro", SimpleNamespace(KPipeline=Pipeline))
        stream = KokoroTTS().synthesize_stream("long reply")

        first = await stream.__anext__()
        await stream.aclose()  # sets the stop flag while the worker is paused
        resume.set()
        await asyncio.to_thread(finished.wait, 5)

        assert first.rate == 24000
        assert produced == [0, 1]  # the second chunk was made, then dropped, then it stopped

    async def test_an_empty_reply_is_an_empty_result(self, monkeypatch):
        class Pipeline:
            def __init__(self, **kwargs):
                pass

            def __call__(self, text, voice):
                return iter(())

        monkeypatch.setitem(sys.modules, "kokoro", SimpleNamespace(KPipeline=Pipeline))

        result = await KokoroTTS().synthesize("Hi", language="xx")

        assert result.audio_bytes == b"" and result.sample_rate == 24000
        assert result.language is Language.ENGLISH

    def test_vits_needs_a_checkpoint_and_its_config(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="config.json"):
            checkpoint_files(str(tmp_path))
        (tmp_path / "model.pth").write_bytes(b"x")
        (tmp_path / "config.json").write_text("{}")

        assert checkpoint_files(str(tmp_path)) == (tmp_path / "model.pth", tmp_path / "config.json")

    async def test_vits_speaks_through_the_coqui_synthesizer(self, monkeypatch, tmp_path):
        (tmp_path / "best.pth").write_bytes(b"x")
        (tmp_path / "config.json").write_text("{}")
        made = {}

        class Synthesizer:
            output_sample_rate = 22050

            def __init__(self, tts_checkpoint, tts_config_path, use_cuda):
                made.update(checkpoint=tts_checkpoint, cuda=use_cuda)

            def tts(self, text):
                return [0.0, 0.5]

        module = SimpleNamespace(Synthesizer=Synthesizer)
        monkeypatch.setitem(sys.modules, "TTS", SimpleNamespace())
        monkeypatch.setitem(sys.modules, "TTS.utils", SimpleNamespace())
        monkeypatch.setitem(sys.modules, "TTS.utils.synthesizer", module)

        result = await VITSTTS(model_dir=str(tmp_path), use_cuda=False).synthesize("হ্যালো", "bn")

        assert made == {"checkpoint": str(tmp_path / "best.pth"), "cuda": False}
        assert result.sample_rate == 22050 and result.language is Language.BANGLA
