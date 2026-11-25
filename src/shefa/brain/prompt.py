"""Compose the model's prompt: persona, conduct, tools, the caller's state, facts, recent turns.

One leading system message (gemma2 reads that best; see `_speak_tool_result`), then the last few
user/assistant turns. Prompt text holds literal braces (`TOOL {"name": ...}`), so sections are
joined as plain strings, never run through `format`. Persona, conduct, tools and the cues are
never trimmed; history, the directory and the hits give way, in that order, when the budget is
short.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

from shefa.brain.state import CallState, summary
from shefa.config.settings import settings

if TYPE_CHECKING:
    from collections.abc import Callable

    from shefa.brain.retrieve import Hit

MOOD_CUES: dict[str, str] = {
    "calm": "",
    "anxious": "The caller is worried: reassure them in a few words first; be clear and calm.",
    "upset": (
        "The caller is upset: acknowledge it in a few words before anything else; "
        "keep sentences short."
    ),
    "angry": (
        "The caller is angry: apologise briefly for the trouble, do not argue, "
        "and get to what they need."
    ),
    "confused": (
        "The caller is confused: use very simple words, one thing at a time, "
        "and offer two clear choices."
    ),
    "rushed": "The caller is in a hurry: answer at once in one short sentence.",
    "chatty": (
        "The caller is chatty: reply warmly in a few words, then bring them back to what they need."
    ),
    "quiet": "The caller says little: ask one simple question to help them.",
}

GOAL_CUES: dict[str, str] = {
    "information": (
        "The caller only wants information: answer it, and do not offer a booking "
        "unless they ask for one."
    ),
    "booking": "",
    "change": "",
    "lookup": "",
    "complaint": "",
    "small_talk": "",
    "unknown": "",
}

MIN_HISTORY = 2  # the last turns kept however short the budget is
MIN_HITS = 2
_SEP = "\n\n"


def _tokens(messages: list[dict[str, str]]) -> int:
    """Conservative estimate: Bangla runs close to one token per two characters."""
    return sum(math.ceil(len(m["content"]) / 2) for m in messages)


def _facts(hits: list[Hit], language: str) -> str:
    if not hits:
        return "Facts you may use: none for this question."
    lines = [f"[kb:{h.entry.id}] {h.entry.text(language)}" for h in hits]
    return "\n".join(["Facts you may use:", *lines])


def _system(
    state: CallState,
    config: dict[str, Any],
    hits: list[Hit],
    directory: str,
    extras: list[str],
) -> str:
    sections = [config["prompt.persona"], config["prompt.conduct"], config["prompt.tools"]]
    cues = [c for c in (MOOD_CUES.get(state.mood, ""), GOAL_CUES.get(state.goal, "")) if c]
    if cues:
        sections.append("Caller now: " + " ".join(cues))
    sections.append("Language: reply in " + ("Bangla" if state.language == "bn" else "English"))
    known = summary(state)
    if known:
        sections.append("Known so far: " + known)
    sections.append(_facts(hits, state.language))
    if directory:
        sections.append(directory)
    sections.extend(extras)
    return _SEP.join(s for s in sections if s)


def compose(
    state: CallState,
    config: dict[str, Any],
    hits: list[Hit],
    directory: str,
    history: list[dict[str, str]],
    *,
    tool_note: str = "",
    correction: str = "",
    boundary_note: str = "",
    directory_for: Callable[[int], str] | None = None,
) -> list[dict[str, str]]:
    """The messages for the model; `directory_for(max_chars)` gives a smaller directory block."""
    budget = settings.brain.prompt_budget_tokens
    # The correction goes last so the model reads the reason for the retry right before replying.
    extras = [e for e in (tool_note, boundary_note, correction) if e]
    turns = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m.get("role") in ("user", "assistant")
    ]
    turns = turns[-settings.brain.history_turns :] if settings.brain.history_turns else []
    kept = list(hits)

    def build(directory_text: str) -> list[dict[str, str]]:
        system = _system(state, config, kept, directory_text, extras)
        return [{"role": "system", "content": system}, *turns]

    messages = build(directory)
    # 1. history, oldest first, down to the last turns
    while _tokens(messages) > budget and len(turns) > MIN_HISTORY:
        turns.pop(0)
        messages = build(directory)
    # 2. the directory: a smaller block that fits, else none
    if _tokens(messages) > budget and directory:
        directory = _fit_directory(build, directory_for, budget)
        messages = build(directory)
    # 3. hits, from the lowest ranked, down to two
    while _tokens(messages) > budget and len(kept) > MIN_HITS:
        kept.pop()
        messages = build(directory)
    return messages


def _fit_directory(
    build: Callable[[str], list[dict[str, str]]],
    directory_for: Callable[[int], str] | None,
    budget: int,
) -> str:
    if directory_for is None:
        return ""
    room = budget - _tokens(build(""))
    max_chars = room * 2 - len(_SEP) - 2
    while max_chars > 0:
        block = directory_for(max_chars)
        if not block:
            return ""
        if _tokens(build(block)) <= budget:
            return block
        max_chars = int(max_chars * 0.8)
    return ""
