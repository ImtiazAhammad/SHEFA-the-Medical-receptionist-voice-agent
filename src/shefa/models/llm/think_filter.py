"""Remove a model's written-out reasoning (<think>…</think>) before anything is spoken.

Some reasoning models (Qwen3 builds from Hugging Face served by Ollama, for one) write their
thinking into the reply itself instead of a separate field. Spoken, the caller would hear the
model talk to itself, so every reply passes through here. Reasoning that never closes (the
reply cap ran out mid-thought) says nothing at all.
"""

from __future__ import annotations

import re

OPEN = "<think>"
CLOSE = "</think>"
_BLOCK = re.compile(r"\s*<think>.*?(?:</think>|\Z)\s*", re.DOTALL)


def strip_thinking(text: str) -> str:
    """`text` without its reasoning blocks. A block between two words leaves one space; a
    closing tag with no opening one (the chat template put `<think>` in the prompt) drops
    everything before it."""
    close, open_ = text.find(CLOSE), text.find(OPEN)
    if close >= 0 and (open_ < 0 or close < open_):
        text = text[close + len(CLOSE) :]
    if OPEN not in text:
        return text.lstrip() if close >= 0 else text

    def gap(match: re.Match[str]) -> str:
        inside = match.start() > 0 and match.end() < len(text)
        return " " if inside else ""

    return _BLOCK.sub(gap, text).lstrip()


def _held_back(text: str, *tags: str) -> int:
    """How many characters at the end of `text` could be the start of one of `tags`."""
    for size in range(min(max(len(t) for t in tags) - 1, len(text)), 0, -1):
        if any(tag.startswith(text[-size:]) for tag in tags):
            return size
    return 0


class ThinkFilter:
    """The streamed form: feed each text chunk, speak what comes back, flush at the end.

    Only the few characters that might be the start of a tag are held back, so a reply with
    no reasoning streams through as fast as it arrives. A closing tag with no opening one drops
    the unspoken text before it and is never spoken itself; text already handed out before it
    cannot be taken back, so a model whose template opens the reasoning in the prompt must not
    be streamed without its reasoning turned off.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._inside = False
        self._after_block = False  # drop the blank space right after a closing tag
        self._last = ""  # the last character handed out

    def _out(self, out: list[str], text: str) -> None:
        if not text:
            return
        if self._after_block and self._last and not self._last.isspace():
            text = " " + text  # a block between two words leaves one space
        self._after_block = False
        out.append(text)
        self._last = text[-1]

    def feed(self, chunk: str) -> str:
        self._buffer += chunk
        out: list[str] = []
        while self._buffer:
            if self._inside:
                end = self._buffer.find(CLOSE)
                if end < 0:
                    keep = _held_back(self._buffer, CLOSE)
                    self._buffer = self._buffer[len(self._buffer) - keep :] if keep else ""
                    break
                self._buffer = self._buffer[end + len(CLOSE) :]
                self._inside = False
                self._after_block = True
                continue
            if self._after_block:
                self._buffer = self._buffer.lstrip()
                if not self._buffer:
                    break
            start, close = self._buffer.find(OPEN), self._buffer.find(CLOSE)
            if close >= 0 and (start < 0 or close < start):
                self._buffer = self._buffer[close + len(CLOSE) :]  # reasoning opened in the prompt
                self._after_block = True
                continue
            if start >= 0:
                before = self._buffer[:start]
                self._out(out, before.rstrip() if before.strip() else "")
                self._buffer = self._buffer[start + len(OPEN) :]
                self._inside = True
                continue
            keep = _held_back(self._buffer, OPEN, CLOSE)
            cut = len(self._buffer) - keep
            self._out(out, self._buffer[:cut])
            self._buffer = self._buffer[cut:]
            break
        return "".join(out)

    def flush(self) -> str:
        """What is left at the end of the stream: nothing if it was inside reasoning."""
        out: list[str] = []
        if not self._inside:
            self._out(out, self._buffer.lstrip() if self._after_block else self._buffer)
        self._buffer = ""
        return "".join(out)
