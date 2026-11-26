"""Compose the model's prompt: persona, conduct, the directory, then this turn's cues and facts.

One leading system message (gemma2 reads that best; see `_speak_tool_result`), then the last few
user/assistant turns. What stays the same for the whole call comes first (persona, conduct, the
directory, whether the caller is identified) so vLLM's prefix cache reuses it from turn to turn;
the 8b probe saw a 68 ms first token on a cached prompt against ~350 ms when the directory came
after the per-turn parts. The tool protocol is not here: the router (`shefa.brain.router`)
decides tools. Prompt text can hold literal braces, so sections are joined as plain strings, never
run through `format`. Persona, conduct and the cues are never trimmed; history, the directory and
the hits give way, in that order, when the budget is short.
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

# The brain's directory header: the clinic's own (shefa.clinic.brief.HEADER) also tells the model
# to "offer to book", which pushed information callers toward a booking.
DIRECTORY_HEADER = (
    "## Clinic directory\n"
    "This is the ONLY source of facts about our doctors. Answer questions about doctors, "
    "departments, rooms, fees and who sees which problem from it, and never add to it. "
    "'sees' lists the problems a doctor treats: when a patient describes a problem, name the "
    "department or doctor whose list fits, and never diagnose. Urgent symptoms are emergencies, "
    "not a directory question.\n"
)
IDENTIFIED = (
    "The caller is already identified by their phone number: never ask for their number or name "
    "to look them up."
)

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
    identified: bool,
) -> str:
    # The same for the whole call: the prefix the server can cache.
    sections = [config["prompt.persona"], config["prompt.conduct"], directory]
    if identified:
        sections.append(IDENTIFIED)
    # This turn's parts.
    sections.append("Language: reply in " + ("Bangla" if state.language == "bn" else "English"))
    cues = [c for c in (MOOD_CUES.get(state.mood, ""), GOAL_CUES.get(state.goal, "")) if c]
    if cues:
        sections.append("Caller now: " + " ".join(cues))
    known = summary(state)
    if known:
        sections.append("Known so far: " + known)
    sections.append(_facts(hits, state.language))
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
    identified: bool = False,
) -> list[dict[str, str]]:
    """The messages for the model; `directory_for(max_chars)` gives a smaller directory block;
    `identified` says the caller is known by caller ID."""
    budget = settings.brain.prompt_budget_tokens
    # The correction goes last so the model reads the reason for the retry right before replying.
    extras = [e for e in (tool_note, boundary_note, correction) if e]
    turns = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m.get("role") in ("user", "assistant")
    ]
    whole = len(turns)
    turns = turns[-settings.brain.history_turns :] if settings.brain.history_turns else []

    def lead_with_caller() -> None:
        # The gemma2 template folds the system text into the first user turn: a cut history that
        # opens on an assistant turn puts a different reply before it each turn, and vLLM's
        # prefix cache misses (600-700 ms first token in the probe's longer call). An uncut
        # history keeps the greeting: it is the same on every call. Never below MIN_HISTORY: the
        # clinic's last question is what a short answer ("হ্যাঁ") replies to.
        while (
            len(turns) < whole and len(turns) > MIN_HISTORY and turns[0]["role"] == "assistant"
        ):
            turns.pop(0)

    lead_with_caller()
    kept = list(hits)

    def build(directory_text: str) -> list[dict[str, str]]:
        system = _system(state, config, kept, directory_text, extras, identified)
        return [{"role": "system", "content": system}, *turns]

    messages = build(directory)
    # 1. history, oldest first, down to the last turns
    while _tokens(messages) > budget and len(turns) > MIN_HISTORY:
        turns.pop(0)
        lead_with_caller()
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
