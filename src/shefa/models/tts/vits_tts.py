"""Coqui VITS voices, e.g. bangla-speech-processing/bangla_tts_female (MIT, Bangladeshi).

`uv sync --extra bangla-vits` installs the maintained `coqui-tts` fork. `model_dir` holds
the checkpoint (`*.pth`) and its `config.json`, as `shefa fetch-models` downloads them.
The previous adapter loaded a placeholder `repo_owner/vits_bangla` hub entry and could
never have run.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from shefa.models.tts.threaded import ThreadedTTS, float_to_frame

if TYPE_CHECKING:
    from collections.abc import Iterator

    from shefa.audio import AudioFrame


def checkpoint_files(model_dir: str) -> tuple[Path, Path]:
    """(checkpoint, config) inside `model_dir`; raises FileNotFoundError naming what is missing."""
    directory = Path(model_dir)
    config = directory / "config.json"
    checkpoints = sorted(directory.glob("*.pth"))
    if not checkpoints or not config.exists():
        raise FileNotFoundError(f"no *.pth checkpoint and config.json in {directory}")
    return checkpoints[0], config


class VITSTTS(ThreadedTTS):
    def __init__(self, model_dir: str = "models/vits/bangla_tts_female", use_cuda: bool = False):
        super().__init__()
        self.model_dir = model_dir
        self.use_cuda = use_cuda

    def _load(self) -> Any:
        from TTS.utils.synthesizer import Synthesizer

        checkpoint, config = checkpoint_files(self.model_dir)
        return Synthesizer(
            tts_checkpoint=str(checkpoint), tts_config_path=str(config), use_cuda=self.use_cuda
        )

    def _frames(self, model: Any, text: str) -> Iterator[AudioFrame]:
        yield float_to_frame(model.tts(text), int(model.output_sample_rate))
