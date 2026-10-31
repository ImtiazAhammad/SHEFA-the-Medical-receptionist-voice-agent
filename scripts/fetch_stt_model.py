"""Fetch the Bangla speech model and convert it for faster-whisper (CTranslate2).

    python scripts/fetch_stt_model.py            # -> models/stt/bangla-whisper-medium-ct2

`OmiKhan/bangla-asr-whisper-medium` (Apache-2.0) scores 16.5% WER on real Bengali speech
where stock `large-v3` scores 70% (docs/model-selection.md). It ships as a transformers
checkpoint, so it has to be converted once. Conversion needs `torch` and `transformers`
(`pip install torch transformers`); running the product afterwards does not.

The fine-tune has its OWN tokenizer.json. Pair the converted weights with Whisper's
stock tokenizer and the output is fluent-looking multilingual garbage, so the
fine-tune's tokenizer is copied next to the weights and verified. Only the 80-bin
feature-extractor config, which the repo lacks, comes from the base model.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path

REPO = "OmiKhan/bangla-asr-whisper-medium"
BASE = "openai/whisper-medium"
DEFAULT_TARGET = Path("models/stt/bangla-whisper-medium-ct2")


def convert(target: Path, work: Path | None = None) -> Path:
    from ctranslate2.converters import TransformersConverter
    from huggingface_hub import hf_hub_download, snapshot_download

    source = Path(snapshot_download(REPO))
    stock = Path(hf_hub_download(BASE, "tokenizer.json"))
    own = source / "tokenizer.json"
    if _digest(own) == _digest(stock):
        raise RuntimeError(f"{REPO} tokenizer.json is identical to {BASE}; refusing to convert")
    staging = work or target.parent / ".convert-src"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    try:
        for item in source.iterdir():
            shutil.copy2(item, staging / item.name)
        preprocessor = hf_hub_download(BASE, "preprocessor_config.json")
        shutil.copy2(preprocessor, staging / "preprocessor_config.json")
        TransformersConverter(
            str(staging), copy_files=["tokenizer.json", "preprocessor_config.json"]
        ).convert(str(target), quantization="float16", force=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    shutil.copy2(own, target / "tokenizer.json")
    return target


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args()
    args.target.parent.mkdir(parents=True, exist_ok=True)
    print(f"converted -> {convert(args.target)}")


if __name__ == "__main__":
    main()
