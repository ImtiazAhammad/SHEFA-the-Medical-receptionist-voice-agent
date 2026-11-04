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


def _http_get_json(url: str, api_key: str = "") -> Any:
    import httpx

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    response = httpx.get(url, headers=headers, timeout=5.0)
    response.raise_for_status()
    return response.json()


def llm_status(
    provider: str,
    base_url: str,
    model: str,
    env: Mapping[str, str] = os.environ,
    get_json: Callable[..., Any] = _http_get_json,
    api_key: str = "",
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
    if api_key.startswith("${"):  # the config names an environment variable that is unset
        return Check(False, f"language model: {api_key[2:-1]} is not set (put it in .env)")
    base = base_url.rstrip("/")
    try:
        listing = get_json(f"{base}/models", api_key) if api_key else get_json(f"{base}/models")
    except Exception as error:  # noqa: BLE001 - reported, never raised
        fix = ("check the API key in .env and the network" if api_key
               else "Start it with: ollama serve")
        return Check(
            False, f"language model: no answer from {base} ({type(error).__name__}). {fix}"
        )
    served = {item.get("id") for item in (listing or {}).get("data", []) if isinstance(item, dict)}
    # Gemini lists its models as "models/<name>".
    if model not in served and f"models/{model}" not in served:
        if api_key:
            return Check(False, f"language model: {base} does not offer {model} to this key")
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
    from shefa.models.registry import hosted_key

    return llm_status(
        llm.provider,
        getattr(adapter, "base_url", ""),
        getattr(adapter, "model", ""),
        api_key=hosted_key(adapter),
        **kwargs,
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


def configured_voices(tts: Any) -> list[Any]:
    """Every voice the config speaks with, resolved: the primary voice, then each
    per-language voice in `tts.voices` (duplicates dropped)."""
    voices = [tts.voice_for("")] if hasattr(tts, "voice_for") else [tts]
    for language in getattr(tts, "voices", None) or {}:
        voices.append(tts.voice_for(language))
    unique: list[Any] = []
    seen: set[tuple[str, str, str]] = set()
    for voice in voices:
        key = (voice.provider, voice.voice_path, getattr(voice, "voice_id", ""))
        if key not in seen:
            seen.add(key)
            unique.append(voice)
    return unique


def _hf_snapshot(repo: str, directory: Path) -> None:
    from huggingface_hub import snapshot_download

    snapshot_download(repo, local_dir=str(directory))


def fetch_vits_voice(
    model_dir: str,
    repo: str,
    find_spec: Callable[[str], Any] = importlib.util.find_spec,
    download: Callable[[str, Path], None] = _hf_snapshot,
) -> Check:
    """A Coqui VITS voice (checkpoint + config.json) from its Hugging Face repo."""
    from shefa.models.tts.vits_tts import checkpoint_files

    if find_spec("TTS") is None:
        return Check(False, f"VITS voice {model_dir} needs: uv sync --extra bangla-vits")
    try:
        checkpoint_files(model_dir)
        return Check(True, f"voice present: {model_dir}")
    except FileNotFoundError:
        pass
    if not repo:
        return Check(False, f"voice missing: {model_dir} (set `model` to its Hugging Face repo)")
    if find_spec("huggingface_hub") is None:
        return Check(False, "downloading a VITS voice needs huggingface_hub: uv pip install it")
    try:
        download(repo, Path(model_dir))
        checkpoint_files(model_dir)
    except Exception as error:  # noqa: BLE001 - reported, never raised
        return Check(False, f"could not download voice {repo}: {error}")
    return Check(True, f"voice downloaded: {model_dir} from {repo}")


def kokoro_check(voice: str, find_spec: Callable[[str], Any] = importlib.util.find_spec) -> Check:
    if find_spec("kokoro") is None:
        return Check(
            False,
            "English voice (Kokoro) needs: uv sync --extra kokoro, and espeak-ng "
            "(apt install espeak-ng / brew install espeak-ng)",
        )
    return Check(True, f"Kokoro voice {voice} installed (weights download on first use)")


def voice_status(voice: Any, find_spec: Callable[[str], Any] = importlib.util.find_spec) -> (
    Check | None
):
    """Whether one resolved voice is ready, without downloading anything (for doctor)."""
    if voice.provider == "piper":
        model = Path(voice.voice_path)
        if _present(model) and _present(model.with_name(model.name + ".json")):
            return Check(True, f"voice found: {model}")
        return Check(False, f"voice missing: {model} (download it with: shefa fetch-models)")
    if voice.provider == "kokoro":
        return kokoro_check(voice.voice_id, find_spec)
    if voice.provider == "azure":
        return azure_check(voice.voice_id)
    if voice.provider == "vits":
        from shefa.models.tts.vits_tts import checkpoint_files

        if find_spec("TTS") is None:
            return Check(False, f"VITS voice {voice.voice_path} needs: uv sync --extra bangla-vits")
        try:
            checkpoint_files(voice.voice_path)
        except FileNotFoundError:
            return Check(False, f"voice missing: {voice.voice_path} (run: shefa fetch-models)")
        return Check(True, f"voice found: {voice.voice_path}")
    return None


def azure_check(voice: str, env: Mapping[str, str] = os.environ) -> Check:
    if not env.get("AZURE_SPEECH_KEY"):
        return Check(
            False, f"Azure voice {voice} needs AZURE_SPEECH_KEY and AZURE_SPEECH_REGION in .env"
        )
    return Check(True, f"Azure voice {voice} (key set; text is sent to Azure)")


def fetch_voice_for(voice: Any) -> Check | None:
    """Fetch or check one resolved voice; None for cloud voices (nothing to fetch)."""
    if voice.provider == "azure":
        return azure_check(voice.voice_id)
    if voice.provider == "piper":
        return fetch_voice(voice.voice_path)
    if voice.provider == "kokoro":
        return kokoro_check(voice.voice_id)
    if voice.provider == "vits":
        return fetch_vits_voice(voice.voice_path, voice.model)
    return None


def fetch_all(
    config: Any,
    *,
    speech: bool = True,
    voice_fn: Callable[[Any], Check | None] = fetch_voice_for,
    runtime_fn: Callable[[], Check] = speech_runtime_check,
    speech_fn: Callable[[str], Check] = fetch_speech_model,
    llm_fn: Callable[[Any], Check | None] = llm_check_for,
    pull_fn: Callable[[str], Check] = pull_llm,
) -> list[Check]:
    """Fetch what the configured providers need, in order: voices, speech, language model."""
    checks: list[Check] = []
    pipeline = config.pipeline
    for voice in configured_voices(pipeline.tts):
        check = voice_fn(voice)
        if check is not None:
            checks.append(check)
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
