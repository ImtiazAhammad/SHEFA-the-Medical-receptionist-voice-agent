"""Fetch and check the models the configured pipeline needs.

Getting a fresh checkout to speak used to take four manual steps: find the Piper Bangla
voice, convert the Bangla Whisper fine-tune, install Ollama and pull the language model.
`shefa fetch-models` does what can be done for the configured providers and says exactly
what is left; `shefa doctor` reuses the same checks.

Every function takes its dependencies as arguments (downloader, HTTP getter, process
runner) so the logic is tested without a network, a GPU or Ollama.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

STT_SCRIPT = Path("scripts/fetch_stt_model.py")
CONVERSION_PACKAGES = ("torch", "transformers", "ctranslate2", "huggingface_hub")
API_KEY_ENV = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


@dataclass
class Check:
    """One line of a fetch or doctor report."""

    ok: bool
    detail: str
    # The model server answered but does not have the model: `ollama pull` fixes it.
    pullable: bool = False

    def line(self) -> str:
        return f"  {'ok' if self.ok else 'BLOCKER':<7}  {self.detail}"


def _present(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def _piper_download(name: str, directory: Path) -> None:
    from piper.download_voices import download_voice

    download_voice(name, directory)


def fetch_voice(
    voice_path: str, download: Callable[[str, Path], None] | None = None
) -> Check:
    """Download a Piper voice (`.onnx` and `.onnx.json`) from the rhasspy catalog.

    The voice name is the file name, so `models/piper/bn_BD-google-medium.onnx` fetches
    `bn_BD-google-medium`. Files land in a temporary directory first and are moved into
    place only once both exist, so an interrupted download never leaves a truncated voice.
    """
    model = Path(voice_path)
    config = model.with_name(model.name + ".json")
    if _present(model) and _present(config):
        return Check(True, f"voice present: {model}")
    name = model.name.removesuffix(".onnx")
    model.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=model.parent) as tmp:
        try:
            (download or _piper_download)(name, Path(tmp))
            for target in (model, config):
                os.replace(Path(tmp) / target.name, target)
        except Exception as error:  # noqa: BLE001 - reported, never raised
            return Check(False, f"could not download voice {name}: {error}")
    return Check(True, f"voice downloaded: {model}")


def speech_runtime_check(find_spec: Callable[[str], Any] = importlib.util.find_spec) -> Check:
    if find_spec("faster_whisper") is None:
        return Check(
            False,
            "faster-whisper is not installed: uv sync --extra local-stt-gpu "
            "(or --extra local-stt on a machine without an NVIDIA GPU)",
        )
    return Check(True, "speech runtime installed (faster-whisper)")


def fetch_speech_model(
    model_dir: str,
    run: Callable[..., Any] = subprocess.run,
    find_spec: Callable[[str], Any] = importlib.util.find_spec,
) -> Check:
    """Build the Bangla Whisper model with `scripts/fetch_stt_model.py` if it is missing.

    The conversion needs torch and transformers once; running the product does not, so
    they are not dependencies. When they are absent the check says how to add them.
    """
    target = Path(model_dir)
    if (target / "model.bin").exists():
        return Check(True, f"speech model present: {target}")
    missing = [name for name in CONVERSION_PACKAGES if find_spec(name) is None]
    if missing:
        return Check(
            False,
            f"speech model missing: {target}. Building it once needs "
            f"{', '.join(missing)}: uv pip install torch transformers ctranslate2 "
            "huggingface_hub, then run shefa fetch-models again",
        )
    if not STT_SCRIPT.exists():
        return Check(False, f"speech model missing and {STT_SCRIPT} not found (run from the repo)")
    target.parent.mkdir(parents=True, exist_ok=True)
    done = run([sys.executable, str(STT_SCRIPT), "--target", str(target)], check=False)
    if done.returncode != 0 or not (target / "model.bin").exists():
        return Check(False, f"speech model conversion failed (exit {done.returncode})")
    return Check(True, f"speech model built: {target}")


def _http_get_json(url: str) -> Any:
    import httpx

    response = httpx.get(url, timeout=5.0)
    response.raise_for_status()
    return response.json()


def llm_status(
    provider: str,
    base_url: str,
    model: str,
    env: Mapping[str, str] = os.environ,
    get_json: Callable[[str], Any] = _http_get_json,
) -> Check:
    """Whether the configured language model can answer.

    Cloud providers need their API key; a local server (Ollama, vLLM) must answer the
    OpenAI-compatible `/models` route and list the configured model.
    """
    if provider in API_KEY_ENV:
        variable = API_KEY_ENV[provider]
        if not env.get(variable):
            return Check(False, f"language model: {variable} is not set (put it in .env)")
        return Check(True, f"language model: {provider} {model} (key set)")
    base = base_url.rstrip("/")
    try:
        listing = get_json(f"{base}/models")
    except Exception as error:  # noqa: BLE001 - reported, never raised
        return Check(
            False,
            f"language model: no server at {base} ({type(error).__name__}). "
            "Start it with: ollama serve",
        )
    served = {item.get("id") for item in (listing or {}).get("data", []) if isinstance(item, dict)}
    if model not in served:
        return Check(
            False,
            f"language model: {model} is not on the server at {base} (run: ollama pull {model})",
            pullable=True,
        )
    return Check(True, f"language model: {model} served at {base}")


def llm_check_for(config: Any, **kwargs: Any) -> Check | None:
    """`llm_status` for a loaded config, or None when the config has no LLM section."""
    llm = getattr(getattr(config, "pipeline", None), "llm", None)
    models = getattr(config, "models", None)
    if llm is None or models is None:
        return None
    try:
        _, adapter = models.resolve_llm_adapter(llm.provider)
    except ValueError as error:
        return Check(False, f"language model: {error}")
    return llm_status(
        llm.provider, getattr(adapter, "base_url", ""), getattr(adapter, "model", ""), **kwargs
    )


def pull_llm(
    model: str,
    which: Callable[[str], str | None] = shutil.which,
    run: Callable[..., Any] = subprocess.run,
) -> Check:
    if which("ollama") is None:
        return Check(
            False,
            f"Ollama is not installed: get it from https://ollama.com, then: ollama pull {model}",
        )
    done = run(["ollama", "pull", model], check=False)
    if done.returncode != 0:
        return Check(False, f"ollama pull {model} failed (exit {done.returncode})")
    return Check(True, f"language model pulled: {model}")


def fetch_all(
    config: Any,
    *,
    speech: bool = True,
    fetch_voice_fn: Callable[[str], Check] = fetch_voice,
    runtime_fn: Callable[[], Check] = speech_runtime_check,
    speech_fn: Callable[[str], Check] = fetch_speech_model,
    llm_fn: Callable[[Any], Check | None] = llm_check_for,
    pull_fn: Callable[[str], Check] = pull_llm,
) -> list[Check]:
    """Fetch what the configured providers need, in order: voice, speech, language model."""
    checks: list[Check] = []
    pipeline = config.pipeline
    if pipeline.tts.provider == "piper":
        checks.append(fetch_voice_fn(pipeline.tts.voice_path))
    adapter = config.models.adapters.get("stt_whisper_local")
    model_dir = getattr(adapter, "model_size", "") or ""
    if pipeline.stt.provider == "whisper_local":
        checks.append(runtime_fn())
        if "/" in model_dir and speech:
            checks.append(speech_fn(model_dir))
        elif "/" in model_dir:
            checks.append(Check(False, f"speech model skipped (--skip-speech): {model_dir}"))
    status = llm_fn(config)
    if status is not None and status.pullable:
        _, llm_adapter = config.models.resolve_llm_adapter(pipeline.llm.provider)
        pulled = pull_fn(llm_adapter.model)
        status = llm_fn(config) if pulled.ok else pulled
    if status is not None:
        checks.append(status)
    return checks
