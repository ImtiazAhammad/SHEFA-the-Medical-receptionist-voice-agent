"""Candidate-model benchmark for the SHEFA pipeline (STT, LLM, TTS).

Needs heavy dependencies that the product deliberately does not ship (torch,
transformers, jiwer, datasets, coqui-tts), so run it from a throwaway venv:

    PYTHONPATH=src python scripts/bench_models.py data  --out bench-out
    PYTHONPATH=src python scripts/bench_models.py stt   --out bench-out --models large-v3 small omikhan
    PYTHONPATH=src python scripts/bench_models.py llm   --out bench-out --models gemma2:9b qwen3:8b
    PYTHONPATH=src python scripts/bench_models.py tts   --out bench-out

Audio conditions, because a clinic phone is not a studio microphone:
  clean        16 kHz as synthesized or recorded
  phone        8 kHz, 300-3400 Hz band-limit, mu-law quantization (what Asterisk hands us)
  phone_noise  the above plus clinic noise (babble + hiss) at 10 dB SNR
"""

from __future__ import annotations

import argparse
import json
import re
import time
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np

RATE = 16000

# What patients actually say to a clinic line. `text` doubles as the STT/TTS reference.
SENTENCES = [
    "আমি ডাক্তার রহমানের সাথে সোমবার সকাল নয়টায় একটি অ্যাপয়েন্টমেন্ট নিতে চাই।",
    "হৃদরোগ বিভাগে কোন কোন ডাক্তার বসেন?",
    "আমার নাম করিম, আমার ফোন নম্বর শূন্য এক সাত এক এক শূন্য শূন্য শূন্য শূন্য এক।",
    "কাল বিকেলে শিশু বিভাগে ডাক্তার সুলতানা আছেন কি?",
    "আমার অ্যাপয়েন্টমেন্টটা বাতিল করতে চাই।",
    "অ্যাপয়েন্টমেন্ট আগামী রবিবার সকালে পরিবর্তন করা যাবে?",
    "ডাক্তারের ভিজিট কত টাকা?",
    "আমার বুকে ব্যথা করছে, শ্বাস নিতে কষ্ট হচ্ছে।",
    "চোখের ডাক্তার কখন বসেন?",
    "আমি আমার মেয়ের জন্য ডাক্তার দেখাতে চাই, তার জ্বর।",
    "ক্লিনিক শুক্রবার খোলা থাকে?",
    "আমার রেফারেন্স নম্বর এ পি টি শূন্য শূন্য শূন্য চার দুই।",
    "আজ বিকাল চারটায় কোনো সিরিয়াল পাওয়া যাবে?",
    "মেডিসিন বিভাগের ডাক্তার কে কে আছেন?",
    "ধন্যবাদ, আমি পরে ফোন করব।",
    "আমি একজন মানুষের সাথে কথা বলতে চাই।",
]

TODAY = date(2026, 11, 2)  # a Monday, so "কাল" is 2026-11-03

# (utterance, acceptable tools — None means "no tool", required argument checks)
LLM_CASES: list[tuple[str, set[str | None], dict[str, str]]] = [
    ("ডাক্তার রহমানের সাথে কাল সকাল নয়টায় অ্যাপয়েন্টমেন্ট দিন",
     {"book_appointment", "check_appointment_slots", "verify_patient"}, {}),
    ("হৃদরোগ বিভাগে কোন কোন ডাক্তার আছেন?", {"list_departments", "list_doctors"}, {}),
    ("ডাক্তার সুলতানা কখন বসেন?", {"get_doctor_info", "list_doctors"}, {}),
    ("কাল শিশু বিভাগে সিরিয়াল আছে?", {"check_appointment_slots", "list_doctors"},
     {"date": "2026-11-03"}),
    ("আমার বাবার বুকে খুব ব্যথা, শ্বাস নিতে পারছেন না", {"transfer_to_human"}, {}),
    ("আমি একজন মানুষের সাথে কথা বলতে চাই", {"transfer_to_human"}, {}),
    ("ধন্যবাদ", {None}, {}),
    ("আমার অ্যাপয়েন্টমেন্ট APT-00042 বাতিল করুন, আমার আইডি ৭", {"cancel_appointment"},
     {"appointment_id": "APT-00042"}),
    ("Book me with Dr. Rahman tomorrow at 10:30",
     {"book_appointment", "check_appointment_slots", "verify_patient"}, {}),
    ("ক্লিনিকের ঠিকানা কী?", {None}, {}),
    ("Doctor er appointment কাল কখন available?",
     {"check_appointment_slots", "list_doctors", "list_departments"}, {}),
    ("আমার জ্বর, কী ওষুধ খাব?", {None, "transfer_to_human"}, {}),
]


# --------------------------------------------------------------------------- audio


def phone_band(audio: np.ndarray) -> np.ndarray:
    """8 kHz, 300-3400 Hz, 8-bit mu-law: the signal a SIP trunk actually delivers."""
    from scipy.signal import butter, resample_poly, sosfilt

    narrow = resample_poly(audio, 1, 2)
    narrow = sosfilt(butter(4, [300, 3400], btype="band", fs=RATE // 2, output="sos"), narrow)
    mu = 255.0
    peak = max(1e-6, float(np.max(np.abs(narrow))))
    x = narrow / peak
    companded = np.sign(x) * np.log1p(mu * np.abs(x)) / np.log1p(mu)
    quantized = np.round(companded * 127) / 127
    restored = np.sign(quantized) * ((1 + mu) ** np.abs(quantized) - 1) / mu
    return resample_poly(restored * peak, 2, 1).astype(np.float32)


def add_clinic_noise(
    audio: np.ndarray, babble_sources: list[np.ndarray], snr_db: float, rng: np.random.Generator
) -> np.ndarray:
    """Mix in murmuring voices and hiss at the given SNR (relative to speech RMS)."""
    babble = np.zeros_like(audio)
    for source in rng.choice(len(babble_sources), size=min(4, len(babble_sources)), replace=False):
        clip = babble_sources[int(source)]
        shifted = np.resize(np.roll(clip, int(rng.integers(0, len(clip)))), len(audio))
        babble += shifted
    hiss = rng.normal(0, 1, len(audio)).astype(np.float32)
    noise = babble / (np.std(babble) + 1e-9) * 0.8 + hiss * 0.3
    speech_rms = float(np.sqrt(np.mean(audio**2))) + 1e-9
    noise = noise / (np.sqrt(np.mean(noise**2)) + 1e-9) * speech_rms / (10 ** (snr_db / 20))
    mixed = audio + noise
    return (mixed / max(1.0, float(np.max(np.abs(mixed))))).astype(np.float32)


def write_wav(path: Path, audio: np.ndarray, rate: int = RATE) -> None:
    import soundfile as sf

    sf.write(str(path), audio, rate, subtype="PCM_16")


def read_wav(path: Path) -> np.ndarray:
    import soundfile as sf

    audio, rate = sf.read(str(path), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if rate != RATE:
        from scipy.signal import resample_poly

        audio = resample_poly(audio, RATE, rate).astype(np.float32)
    return audio


def synthesize_piper(text: str, voice_path: str) -> np.ndarray:
    from piper import PiperVoice
    from scipy.signal import resample_poly

    voice = PiperVoice.load(voice_path)
    chunks = [np.frombuffer(c.audio_int16_bytes, dtype=np.int16) for c in voice.synthesize(text)]
    audio = np.concatenate(chunks).astype(np.float32) / 32768.0
    rate = voice.config.sample_rate
    return resample_poly(audio, RATE, rate).astype(np.float32) if rate != RATE else audio


def fetch_real_speech(out: Path, count: int) -> list[dict[str, str]]:
    """A few real Bengali recordings (Google FLEURS test split) for ground truth."""
    import tarfile

    from huggingface_hub import hf_hub_download

    tsv = Path(hf_hub_download("google/fleurs", "data/bn_in/test.tsv", repo_type="dataset"))
    tar = Path(hf_hub_download("google/fleurs", "data/bn_in/audio/test.tar.gz", repo_type="dataset"))
    refs: dict[str, str] = {}
    for line in tsv.read_text(encoding="utf-8").splitlines():
        cols = line.split("\t")
        if len(cols) >= 3:
            refs[cols[1]] = cols[3] if len(cols) > 3 else cols[2]  # normalized transcription
    chosen: list[dict[str, str]] = []
    with tarfile.open(tar) as archive:
        for member in archive:
            name = Path(member.name).name
            if name in refs and member.isfile() and len(chosen) < count:
                target = out / "real" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())  # type: ignore[union-attr]
                chosen.append({"id": name, "wav": str(target), "text": refs[name]})
    return chosen


def cmd_data(args: argparse.Namespace) -> None:
    out = Path(args.out)
    for sub in ("clean", "phone", "phone_noise"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    clean = [synthesize_piper(t, args.piper_voice) for t in SENTENCES]
    manifest: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = [
        {"id": f"clinic{i:02d}", "text": t, "audio": a, "source": "piper-bn"}
        for i, (t, a) in enumerate(zip(SENTENCES, clean, strict=True))
    ]
    if args.real:
        for row in fetch_real_speech(out, args.real):
            entries.append(
                {"id": row["id"][:-4], "text": row["text"], "audio": read_wav(Path(row["wav"])),
                 "source": "fleurs-bn"}
            )
    babble = [e["audio"] for e in entries]
    for entry in entries:
        variants = {
            "clean": entry["audio"],
            "phone": phone_band(entry["audio"]),
        }
        variants["phone_noise"] = add_clinic_noise(variants["phone"], babble, 10.0, rng)
        files = {}
        for condition, audio in variants.items():
            path = out / condition / f"{entry['id']}.wav"
            write_wav(path, audio)
            files[condition] = str(path)
        manifest.append(
            {"id": entry["id"], "text": entry["text"], "source": entry["source"], "files": files}
        )
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    print(f"wrote {len(manifest)} utterances x 3 conditions to {out}")


# ----------------------------------------------------------------------------- STT


def normalize_bn(text: str) -> str:
    text = re.sub(r"[।,?!.\-\"'“”‘’:;()]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def error_rates(reference: str, hypothesis: str) -> tuple[float, float]:
    import jiwer

    ref, hyp = normalize_bn(reference), normalize_bn(hypothesis)
    if not ref:
        return 0.0, 0.0
    return jiwer.wer(ref, hyp or "-"), jiwer.cer(ref, hyp or "-")


def stt_model_path(name: str, models_dir: Path) -> str:
    if name == "omikhan":
        path = models_dir / "omikhan-ct2"
        if not (path / "model.bin").exists():
            convert_omikhan(path)
        return str(path)
    return name


def convert_omikhan(target: Path) -> None:
    """Convert OmiKhan/bangla-asr-whisper-medium to CTranslate2 for faster-whisper."""
    from ctranslate2.converters import TransformersConverter
    from huggingface_hub import hf_hub_download

    repo = "OmiKhan/bangla-asr-whisper-medium"
    target.parent.mkdir(parents=True, exist_ok=True)
    TransformersConverter(
        repo, copy_files=["tokenizer.json", "preprocessor_config.json"]
    ).convert(str(target), quantization="float16", force=True)
    for name in ("tokenizer.json", "preprocessor_config.json"):
        if not (target / name).exists():
            fallback = hf_hub_download("openai/whisper-medium", name)
            (target / name).write_bytes(Path(fallback).read_bytes())


def vram_mib() -> int | None:
    import subprocess

    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, check=True,
        ).stdout
        return int(out.splitlines()[0])
    except (OSError, ValueError, subprocess.CalledProcessError):
        return None


def cmd_stt(args: argparse.Namespace) -> None:
    from faster_whisper import WhisperModel

    out = Path(args.out)
    manifest = json.loads((out / "manifest.json").read_text())
    results: dict[str, Any] = {}
    for name in args.models:
        baseline = vram_mib() or 0
        model = WhisperModel(
            stt_model_path(name, out / "models"), device="cuda", compute_type="float16"
        )
        row: dict[str, Any] = {"vram_mib": (vram_mib() or 0) - baseline}
        for source in sorted({m["source"] for m in manifest}):
            for condition in ("clean", "phone", "phone_noise"):
                wers, cers, secs, audio_secs = [], [], 0.0, 0.0
                for item in (m for m in manifest if m["source"] == source):
                    audio = read_wav(Path(item["files"][condition]))
                    started = time.perf_counter()
                    segments, _ = model.transcribe(
                        audio, language="bn", beam_size=5, condition_on_previous_text=False
                    )
                    hypothesis = " ".join(s.text.strip() for s in segments)
                    secs += time.perf_counter() - started
                    audio_secs += len(audio) / RATE
                    wer, cer = error_rates(item["text"], hypothesis)
                    wers.append(wer)
                    cers.append(cer)
                row[f"{source}/{condition}"] = {
                    "wer": round(float(np.mean(wers)), 3),
                    "cer": round(float(np.mean(cers)), 3),
                    "rtf": round(secs / max(audio_secs, 1e-9), 3),
                    "n": len(wers),
                }
        results[name] = row
        print(name, json.dumps(row, ensure_ascii=False))
        del model
    (out / "stt-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))


# ----------------------------------------------------------------------------- LLM


def bangla_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    return sum("ঀ" <= c <= "৿" for c in letters) / len(letters) if letters else 0.0


def ollama_chat(model: str, messages: list[dict[str, str]], host: str) -> tuple[str, float]:
    import urllib.request

    body = json.dumps(
        {"model": model, "messages": messages, "stream": False, "keep_alive": "2m",
         "options": {"temperature": 0, "num_predict": 300}}
    ).encode()
    request = urllib.request.Request(
        f"{host}/api/chat", body, {"Content-Type": "application/json"}
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        payload = json.load(response)
    return payload["message"]["content"], time.perf_counter() - started


def cmd_llm(args: argparse.Namespace) -> None:
    from shefa.pipeline.actions import extractor_system_prompt, parse_action
    from shefa.prompts import system_prompt
    from shefa.tools.definitions import get_tool_definitions

    tools = get_tool_definitions()
    known = {t.name for t in tools}
    router = extractor_system_prompt(tools, TODAY)
    out = Path(args.out)
    results: dict[str, Any] = {}
    for model in args.models:
        valid = right_tool = right_args = 0
        latencies: list[float] = []
        for utterance, acceptable, required in LLM_CASES:
            text, seconds = ollama_chat(
                model,
                [{"role": "system", "content": router}, {"role": "user", "content": utterance}],
                args.host,
            )
            latencies.append(seconds)
            action = parse_action(text, known)
            parsed_ok = action is not None or '"tool": null' in text.replace("None", "null") or (
                re.search(r'"tool"\s*:\s*null', text) is not None
            )
            valid += parsed_ok
            tool = action.name if action else None
            if parsed_ok and tool in acceptable:
                right_tool += 1
                arguments = action.arguments if action else {}
                right_args += all(str(arguments.get(k)) == v for k, v in required.items())
        replies = []
        for utterance, _, _ in LLM_CASES:
            if re.search(r"[ঀ-৿]", utterance):
                text, seconds = ollama_chat(
                    model,
                    [{"role": "system", "content": system_prompt("bn", None)},
                     {"role": "user", "content": utterance}],
                    args.host,
                )
                replies.append(bangla_ratio(text))
                latencies.append(seconds)
        total = len(LLM_CASES)
        row = {
            "json_valid": f"{valid}/{total}",
            "right_tool": f"{right_tool}/{total}",
            "right_args": f"{right_args}/{total}",
            "bangla_purity": round(float(np.mean(replies)), 3),
            "median_s": round(float(np.median(latencies)), 2),
            "p95_s": round(float(np.percentile(latencies, 95)), 2),
            "vram_mib": vram_mib(),
        }
        results[model] = row
        print(model, json.dumps(row, ensure_ascii=False))
    (out / "llm-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1))


# ----------------------------------------------------------------------------- TTS


def cmd_tts(args: argparse.Namespace) -> None:
    """Round-trip intelligibility: synthesize, transcribe with a fixed STT, compare."""
    from faster_whisper import WhisperModel

    out = Path(args.out)
    (out / "tts").mkdir(parents=True, exist_ok=True)
    stt = WhisperModel(stt_model_path(args.judge, out / "models"), device="cuda",
                       compute_type="float16")
    engines: dict[str, Any] = {"piper-bn_BD-google": lambda t: synthesize_piper(t, args.piper_voice)}
    for name in args.coqui:
        engines[name] = coqui_engine(name)
    results: dict[str, Any] = {}
    for name, synth in engines.items():
        wers, rtfs = [], []
        for i, text in enumerate(SENTENCES):
            started = time.perf_counter()
            audio = synth(text)
            elapsed = time.perf_counter() - started
            rtfs.append(elapsed / max(len(audio) / RATE, 1e-9))
            write_wav(out / "tts" / f"{name.replace('/', '_')}-{i:02d}.wav", audio)
            segments, _ = stt.transcribe(audio, language="bn", beam_size=5)
            wers.append(error_rates(text, " ".join(s.text.strip() for s in segments))[0])
        results[name] = {
            "roundtrip_wer": round(float(np.mean(wers)), 3),
            "rtf": round(float(np.mean(rtfs)), 3),
        }
        print(name, json.dumps(results[name]))
    (out / "tts-results.json").write_text(json.dumps(results, indent=1))


def coqui_engine(repo: str):
    from huggingface_hub import snapshot_download
    from scipy.signal import resample_poly
    from TTS.utils.synthesizer import Synthesizer

    folder = Path(snapshot_download(repo))
    checkpoint = next(folder.glob("*.pth"))
    synthesizer = Synthesizer(str(checkpoint), str(folder / "config.json"), use_cuda=True)
    rate = synthesizer.output_sample_rate

    def run(text: str) -> np.ndarray:
        wav = np.asarray(synthesizer.tts(text), dtype=np.float32)
        return resample_poly(wav, RATE, rate).astype(np.float32)

    return run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("step", choices=["data", "stt", "llm", "tts"])
    parser.add_argument("--out", default="bench-out")
    parser.add_argument("--models", nargs="+", default=["large-v3"])
    parser.add_argument("--piper-voice", default="models/piper/bn_BD-google-medium.onnx")
    parser.add_argument("--real", type=int, default=30, help="FLEURS clips (data step)")
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--judge", default="large-v3", help="STT model that scores TTS output")
    parser.add_argument("--coqui", nargs="*", default=[], help="HF repos of Coqui VITS voices")
    args = parser.parse_args()
    {"data": cmd_data, "stt": cmd_stt, "llm": cmd_llm, "tts": cmd_tts}[args.step](args)


if __name__ == "__main__":
    main()
