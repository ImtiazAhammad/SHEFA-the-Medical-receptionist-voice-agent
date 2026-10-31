"""Place a scripted call against the real stack, playing Asterisk's part.

    LD_LIBRARY_PATH=<cu12 libs> PYTHONPATH=src python scripts/simulate_call.py \
        "আমাকে কার্ডিওলজির ডাক্তার দেখাতে চাই" "আপনাদের কোন কোন বিভাগ আছে?"

Starts SHEFA's AudioSocket server in-process (provider=asterisk), connects as a fake
Asterisk, speaks each argument as a caller (synthesised with Piper, sent as 8 kHz
20 ms frames in real time), then waits for the agent's spoken reply. Prints the
transcript and the turn latency. Uses a throw-away clinic database seeded from
configs/clinic.example.yaml, so nothing real is touched.
"""

from __future__ import annotations

import argparse
import asyncio
import tempfile
import time
import uuid
from pathlib import Path

from shefa.audio import AudioFrame, s16le_16k_mono_to_slin8k
from shefa.clinic import ClinicStore, set_default_clinic_store
from shefa.clinic.loader import import_directory_file
from shefa.config.settings import TelephonyProvider, settings
from shefa.telephony import asterisk
from shefa.telephony.audiosocket import KIND_AUDIO, KIND_HANGUP, KIND_UUID, encode_frame, read_frame

FRAME = 320


async def speak(writer: asyncio.StreamWriter, pcm_8k: bytes) -> None:
    for start in range(0, len(pcm_8k), FRAME):
        writer.write(encode_frame(KIND_AUDIO, pcm_8k[start : start + FRAME].ljust(FRAME, b"\x00")))
        await writer.drain()
        await asyncio.sleep(0.02)


async def silence(writer: asyncio.StreamWriter, seconds: float) -> None:
    await speak(writer, b"\x00" * int(8000 * 2 * seconds))


async def listen(reader: asyncio.StreamReader, quiet_after: float) -> tuple[float, float]:
    """Seconds until the first reply frame, and total reply audio length."""
    started = time.monotonic()
    first = None
    frames = 0
    while True:
        try:
            frame = await asyncio.wait_for(read_frame(reader), quiet_after if first else 60.0)
        except TimeoutError:
            break
        if frame is None:
            break
        if frame[0] == KIND_AUDIO:
            first = first or time.monotonic() - started
            frames += 1
    return first or -1.0, frames * 0.02


async def run(utterances: list[str], voice: str) -> None:
    from shefa.models.tts.piper_tts import PiperTTS

    tmp = Path(tempfile.mkdtemp(prefix="shefa-sim-"))
    store = ClinicStore(tmp / "sim.db")
    import_directory_file(store, Path("configs/clinic.example.yaml"))
    set_default_clinic_store(store)
    settings.telephony.provider = TelephonyProvider.ASTERISK
    settings.telephony.asterisk.audiosocket_port = 45731
    settings.pipeline.stt.provider = "whisper_local"

    pipelines = []
    original = asterisk.pipeline_factory
    asterisk.pipeline_factory = lambda: pipelines.append(original()) or pipelines[-1]

    tts = PiperTTS(model_path=voice)
    server = await asterisk.start_audiosocket_server()
    reader, writer = await asyncio.open_connection("127.0.0.1", 45731)
    call_uuid = uuid.uuid4()
    writer.write(encode_frame(KIND_UUID, call_uuid.bytes))
    print(f"call {call_uuid} connected")

    # greeting
    first, length = await listen(reader, 2.5)
    print(f"[greeting] first audio after {first:.1f}s, {length:.1f}s long")
    for text in utterances:
        audio = await tts.synthesize(text)
        pcm = s16le_16k_mono_to_slin8k(AudioFrame.from_result(audio).to_s16le_16k_mono())
        print(f"\ncaller: {text}")
        await speak(writer, pcm)
        sent = time.monotonic()
        await silence(writer, 1.2)
        first, length = await listen(reader, 3.0)
        print(
            f"  reply began {first + 1.2:.1f}s after the caller stopped; {length:.1f}s of audio"
            f" (turn took {time.monotonic() - sent:.1f}s)"
        )
    print("\n--- transcript as the agent saw it ---")
    for pipeline in pipelines:
        for sid in list(pipeline._session_manager._sessions):  # noqa: SLF001
            session = await pipeline._session_manager.get_or_create(sid)  # noqa: SLF001
            for turn in session.history:
                print(f"{turn.role:>9}: {turn.content}")
    writer.write(encode_frame(KIND_HANGUP, b""))
    await writer.drain()
    await asyncio.sleep(0.5)

    server.close()
    await tts.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("utterances", nargs="+")
    parser.add_argument("--voice", default="models/piper/bn_BD-google-medium.onnx")
    args = parser.parse_args()
    asyncio.run(run(args.utterances, args.voice))


if __name__ == "__main__":
    main()
