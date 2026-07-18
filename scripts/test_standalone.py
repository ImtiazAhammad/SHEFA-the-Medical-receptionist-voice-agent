"""Standalone component test script.

Usage:
    uv run python scripts/test_standalone.py              # test all
    uv run python scripts/test_standalone.py --llm         # test LLM only
    uv run python scripts/test_standalone.py --stt         # test STT only
    uv run python scripts/test_standalone.py --tts         # test TTS only
    uv run python scripts/test_standalone.py --pipeline    # test full pipeline
"""

from __future__ import annotations

import argparse
import asyncio
import io
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


async def test_config() -> bool:
    print("=" * 60)
    print("TEST: Configuration Loading")
    print("=" * 60)
    try:
        from sefa.config.settings import settings
        print(f"  Languages:  {settings.languages.supported}")
        print(f"  STT:        {settings.pipeline.stt.provider}")
        print(f"  TTS:        {settings.pipeline.tts.provider}")
        print(f"  LLM:        {settings.pipeline.llm.provider}")
        print(f"  Session:    {settings.session.backend}")
        print("  PASS")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


async def test_language_detector() -> bool:
    print("\n" + "=" * 60)
    print("TEST: Language Detection")
    print("=" * 60)
    from sefa.pipeline.language_detector import (
        detect_language, is_emergency, needs_escalation,
    )
    from sefa.models.base import Language

    tests = [
        ("Hello, how are you?", Language.ENGLISH),
        ("নমস্কার, আমি কিভাবে সাহায্য পেতে পারি?", Language.BANGLA),
        ("Doctor er appointment কখন?", Language.BANGLA),
        ("I need to book an appointment", Language.ENGLISH),
    ]

    all_pass = True
    for text, expected in tests:
        lang, conf = detect_language(text)
        status = "PASS" if lang == expected else "FAIL"
        if status == "FAIL":
            all_pass = False
        print(f"  [{status}] '{text[:40]}...' -> {lang.value} (conf={conf:.2f})")

    assert is_emergency("chest pain", Language.ENGLISH)
    assert is_emergency("বুকে ব্যথা", Language.BANGLA)
    print("  [PASS] Emergency detection works")

    print("  PASS" if all_pass else "  SOME FAILED")
    return all_pass


async def test_session() -> bool:
    print("\n" + "=" * 60)
    print("TEST: Session Management")
    print("=" * 60)
    try:
        from sefa.session.manager import SessionManager, CallSession
        from sefa.models.base import Language

        mgr = SessionManager()
        session = await mgr.get_or_create("test_call_001")
        assert session.call_sid == "test_call_001"
        assert session.language == Language.ENGLISH

        session.add_turn("user", "Hello")
        session.add_turn("assistant", "Hi! How can I help?")
        assert len(session.history) == 2

        await mgr.save(session)
        loaded = await mgr.get("test_call_001")
        assert loaded is not None
        assert len(loaded.history) == 2

        await mgr.delete("test_call_001")
        assert await mgr.get("test_call_001") is None

        print("  Create, save, load, delete - PASS")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


async def test_stt() -> bool:
    print("\n" + "=" * 60)
    print("TEST: STT (Speech-to-Text) - Local Whisper")
    print("=" * 60)
    try:
        from sefa.models.stt.whisper_local import WhisperLocalSTT

        print("  Initializing Faster-Whisper (first run downloads model)...")
        stt = WhisperLocalSTT(model_size="tiny")  # use tiny for quick test
        print("  Model loaded. Generating test audio...")

        import numpy as np
        # Generate 1 second of silence as test audio
        audio = np.zeros(16000, dtype=np.float32)
        audio_bytes = audio.tobytes()

        start = time.monotonic()
        result = await stt.transcribe(audio_bytes)
        elapsed = (time.monotonic() - start) * 1000

        print(f"  Result: '{result.text}' (lang={result.language.value})")
        print(f"  Latency: {elapsed:.0f}ms")
        await stt.close()
        print("  PASS")
        return True
    except ImportError:
        print("  SKIP: faster-whisper not installed")
        print("  Run: uv sync --extra local-stt")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


async def test_tts() -> bool:
    print("\n" + "=" * 60)
    print("TEST: TTS (Text-to-Speech) - Piper")
    print("=" * 60)
    try:
        from sefa.models.tts.piper_tts import PiperTTS

        tts = PiperTTS()
        print("  Synthesizing test sentence...")

        start = time.monotonic()
        result = await tts.synthesize("Hello, welcome to Sefa Clinic.")
        elapsed = (time.monotonic() - start) * 1000

        print(f"  Audio size: {len(result.audio_bytes)} bytes")
        print(f"  Latency: {elapsed:.0f}ms")

        # Save to file for verification
        out_path = Path("test_output.wav")
        out_path.write_bytes(result.audio_bytes)
        print(f"  Saved to: {out_path}")
        print("  PASS")
        return True
    except FileNotFoundError:
        print("  SKIP: piper binary not found")
        print("  Install: pip install piper-tts")
        print("  Or download from: https://github.com/rhasspy/piper")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


async def test_llm() -> bool:
    print("\n" + "=" * 60)
    print("TEST: LLM - Ollama (Local)")
    print("=" * 60)
    try:
        import httpx

        # Check if Ollama is running
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            models = resp.json().get("models", [])
            if not models:
                print("  FAIL: No models installed in Ollama")
                print("  Run: ollama pull qwen3:8b")
                return False
            model_names = [m["name"] for m in models]
            print(f"  Available models: {model_names}")

        from sefa.models.llm.openai_compatible_llm import OpenAICompatibleLLM

        model = model_names[0].split(":")[0]
        print(f"  Using model: {model}")

        llm = OpenAICompatibleLLM(
            base_url="http://localhost:11434/v1",
            model=model,
        )

        messages = [
            {"role": "system", "content": "You are a helpful medical receptionist. Reply briefly."},
            {"role": "user", "content": "What are your clinic hours?"},
        ]

        start = time.monotonic()
        result = await llm.generate(messages)
        elapsed = (time.monotonic() - start) * 1000

        print(f"  Response: {result.text[:200]}")
        print(f"  Latency: {elapsed:.0f}ms")
        print(f"  Language: {result.language.value}")
        await llm.close()
        print("  PASS")
        return True
    except httpx.ConnectError:
        print("  FAIL: Ollama not running")
        print("  Start Ollama, then: ollama pull qwen3:8b")
        return False
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


async def test_full_pipeline() -> bool:
    print("\n" + "=" * 60)
    print("TEST: Full Voice Pipeline (simulated)")
    print("=" * 60)
    try:
        from sefa.session.manager import CallSession
        from sefa.models.base import Language
        from sefa.pipeline.language_detector import detect_language
        from sefa.tools.definitions import get_tool_definitions

        # Simulate a conversation turn
        session = CallSession(call_sid="test_pipeline_001")
        user_text = "I want to book an appointment with Dr. Rahman"
        lang, conf = detect_language(user_text)
        session.add_turn("user", user_text, lang)

        tools = get_tool_definitions()
        print(f"  Session created, {len(tools)} tools available")
        print(f"  User said: '{user_text}'")
        print(f"  Detected: {lang.value} (conf={conf:.2f})")

        # Test tool definitions parse correctly
        tool_names = [t.name for t in tools]
        print(f"  Tools: {tool_names}")

        # Test session serialization
        data = session.to_dict()
        restored = CallSession.from_dict(data)
        assert restored.call_sid == session.call_sid

        print("  PASS")
        return True
    except Exception as e:
        print(f"  FAIL: {e}")
        return False


async def main() -> None:
    parser = argparse.ArgumentParser(description="Test Sefa components")
    parser.add_argument("--llm", action="store_true", help="Test LLM only")
    parser.add_argument("--stt", action="store_true", help="Test STT only")
    parser.add_argument("--tts", action="store_true", help="Test TTS only")
    parser.add_argument("--pipeline", action="store_true", help="Test pipeline only")
    args = parser.parse_args()

    run_all = not (args.llm or args.stt or args.tts or args.pipeline)

    results = {}

    results["config"] = await test_config()
    results["language_detector"] = await test_language_detector()
    results["session"] = await test_session()

    if run_all or args.stt:
        results["stt"] = await test_stt()
    if run_all or args.tts:
        results["tts"] = await test_tts()
    if run_all or args.llm:
        results["llm"] = await test_llm()
    if run_all or args.pipeline:
        results["pipeline"] = await test_full_pipeline()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")

    total = len(results)
    passed = sum(1 for v in results.values() if v)
    print(f"\n  {passed}/{total} passed")


if __name__ == "__main__":
    asyncio.run(main())
