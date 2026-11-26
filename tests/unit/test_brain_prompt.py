"""Prompt composition: one system message, cues, facts, and the token budget."""

from __future__ import annotations

import math

from shefa.brain import prompt
from shefa.brain.config import defaults
from shefa.brain.knowledge import Entry
from shefa.brain.prompt import _SEP, GOAL_CUES, IDENTIFIED, MOOD_CUES, compose
from shefa.brain.retrieve import Hit
from shefa.brain.state import CallState
from shefa.config.settings import settings

CONFIG = {
    "prompt.persona": "PERSONA-TEXT",
    "prompt.conduct": "CONDUCT-TEXT",
    "prompt.tools": 'TOOL {"name": "<tool>", "args": {...}}',
    "prompt.greeting": "hello",
}


def _hit(i: int, bn: str = "বাংলা তথ্য", en: str = "english fact") -> Hit:
    entry = Entry(i, "platform", "t", (), bn, en, True, 1)
    return Hit(entry, 1.0 / (i + 1), "words")


def _history(n: int, size: int = 10) -> list[dict[str, str]]:
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"turn{i} " + "x" * size}
        for i in range(n)
    ]


def _tokens(messages: list[dict[str, str]]) -> int:
    return sum(math.ceil(len(m["content"]) / 2) for m in messages)


def _system(messages: list[dict[str, str]]) -> str:
    assert messages[0]["role"] == "system"
    return messages[0]["content"]


def test_cue_texts_are_exact() -> None:
    assert MOOD_CUES["calm"] == ""
    assert MOOD_CUES["angry"] == (
        "The caller is angry: apologise briefly for the trouble, do not argue, and get to "
        "what they need."
    )
    assert GOAL_CUES["information"] == (
        "The caller only wants information: answer it, and do not offer a booking unless "
        "they ask for one."
    )
    assert GOAL_CUES["booking"] == ""
    assert set(MOOD_CUES) >= {"calm", "anxious", "upset", "angry", "confused", "rushed"}


def test_angry_and_information_cues_appear() -> None:
    state = CallState(goal="information", mood="angry")
    text = _system(compose(state, CONFIG, [], "", []))
    assert MOOD_CUES["angry"] in text
    assert GOAL_CUES["information"] in text
    calm = _system(compose(CallState(), CONFIG, [], "", []))
    assert MOOD_CUES["angry"] not in calm
    assert GOAL_CUES["information"] not in calm


def test_layout_and_language() -> None:
    # Changed in 8c: call-constant parts first (persona, conduct, directory) so the server's prefix
    # cache reuses them; the per-turn parts after; the tool protocol is no longer in the reply.
    state = CallState(language="en", mood="angry", booking={"doctor": "Dr. Rahman"})
    text = _system(compose(state, CONFIG, [_hit(7)], "DIRECTORY-BLOCK", [], tool_note="NOTE"))
    order = [
        "PERSONA-TEXT",
        "CONDUCT-TEXT",
        "DIRECTORY-BLOCK",
        "Language: reply in English",
        "Caller now:",
        "Known so far:",
        "Facts you may use:",
        "NOTE",
    ]
    positions = [text.index(p) for p in order]
    assert positions == sorted(positions)
    assert "TOOL {" not in text
    assert "Language: reply in Bangla" in _system(compose(CallState(), CONFIG, [], "", []))


def test_the_fixed_prefix_is_identical_across_turns_of_one_call() -> None:
    first = _system(compose(CallState(), CONFIG, [_hit(1)], "DIR", _history(2)))
    second = _system(
        compose(
            CallState(language="en", mood="angry", goal="information", booking={"date": "x"}),
            CONFIG,
            [_hit(5, en="other fact")],
            "DIR",
            _history(4),
            correction="FIX",
        )
    )
    prefix = _SEP.join(["PERSONA-TEXT", "CONDUCT-TEXT", "DIR"]) + _SEP
    assert first.startswith(prefix)
    assert second.startswith(prefix)


def test_an_identified_caller_is_never_asked_for_number_or_name() -> None:
    text = _system(compose(CallState(), CONFIG, [], "DIR", [], identified=True))
    assert IDENTIFIED in text
    assert text.index("DIR") < text.index(IDENTIFIED) < text.index("Language:")
    assert IDENTIFIED not in _system(compose(CallState(), CONFIG, [], "DIR", []))


def test_braces_in_prompt_text_survive() -> None:
    config = dict(CONFIG, **{"prompt.persona": 'say {"x": 1}'})
    text = _system(compose(CallState(), config, [], "dir {x}", []))
    assert 'say {"x": 1}' in text
    assert "dir {x}" in text


def test_hits_in_callers_language() -> None:
    hits = [_hit(3), _hit(9, bn="", en="only english")]
    bn = _system(compose(CallState(language="bn"), CONFIG, hits, "", []))
    assert "[kb:3] বাংলা তথ্য" in bn
    assert "[kb:9] only english" in bn  # falls back to the other language
    en = _system(compose(CallState(language="en"), CONFIG, hits, "", []))
    assert "[kb:3] english fact" in en


def test_no_hits_says_none() -> None:
    text = _system(compose(CallState(), CONFIG, [], "", []))
    assert "Facts you may use: none for this question." in text


def test_history_cut_to_configured_turns() -> None:
    messages = compose(CallState(), CONFIG, [], "", _history(10))
    rest = messages[1:]
    assert len(rest) == settings.brain.history_turns == 6
    assert rest[-1]["content"].startswith("turn9")
    assert rest[0]["content"].startswith("turn4")


def test_history_keeps_only_user_and_assistant() -> None:
    history = [{"role": "system", "content": "sneaky"}, *_history(2)]
    messages = compose(CallState(), CONFIG, [], "", history)
    assert [m["role"] for m in messages[1:]] == ["user", "assistant"]


def test_correction_is_last_in_system_message() -> None:
    text = _system(
        compose(
            CallState(),
            CONFIG,
            [],
            "DIR",
            [],
            tool_note="TOOLNOTE",
            correction="FIX-THIS",
            boundary_note="BOUNDARY",
        )
    )
    assert text.rstrip().endswith("FIX-THIS")
    assert text.index("TOOLNOTE") < text.index("FIX-THIS")
    assert "BOUNDARY" in text


def test_seeds_from_config_snapshot() -> None:
    seeded = _system(compose(CallState(), defaults(), [], "", []))
    assert defaults()["prompt.persona"] in seeded
    published = dict(defaults(), **{"prompt.persona": "A NEWLY PUBLISHED PERSONA"})
    text = _system(compose(CallState(), published, [], "", []))
    assert "A NEWLY PUBLISHED PERSONA" in text
    assert defaults()["prompt.persona"] not in text


def test_over_budget_trims_history_then_directory_then_hits(monkeypatch) -> None:
    monkeypatch.setattr(settings.brain, "prompt_budget_tokens", 1200)
    big_dir = "D" * 6000
    asked: list[int] = []

    def directory_for(max_chars: int) -> str:
        asked.append(max_chars)
        return "d" * max_chars

    history = _history(10, size=300)
    hits = [_hit(i, bn="ক" * 200) for i in range(4)]
    messages = compose(CallState(), CONFIG, hits, big_dir, history, directory_for=directory_for)
    assert _tokens(messages) <= 1200
    text = _system(messages)
    assert "PERSONA-TEXT" in text
    assert "CONDUCT-TEXT" in text
    assert "TOOL {" not in text
    assert [m["content"][:5] for m in messages[1:]] == ["turn8", "turn9"]
    assert asked  # the directory was shrunk, not kept whole
    assert big_dir not in text


def test_over_budget_without_directory_for_drops_directory(monkeypatch) -> None:
    monkeypatch.setattr(settings.brain, "prompt_budget_tokens", 600)
    messages = compose(CallState(), CONFIG, [], "D" * 4000, _history(6))
    assert _tokens(messages) <= 600
    assert "DDDD" not in _system(messages)
    assert len(messages) == 3  # system plus the last 2 turns


def test_over_budget_trims_hits_to_two_last(monkeypatch) -> None:
    monkeypatch.setattr(settings.brain, "prompt_budget_tokens", 400)
    hits = [_hit(i, bn="ক" * 300) for i in range(4)]
    messages = compose(CallState(), CONFIG, hits, "", _history(4))
    text = _system(messages)
    assert _tokens(messages) <= 400
    assert "[kb:0]" in text
    assert "[kb:1]" in text
    assert "[kb:2]" not in text
    assert "[kb:3]" not in text


def test_under_budget_changes_nothing() -> None:
    hits = [_hit(i) for i in range(4)]
    messages = compose(CallState(), CONFIG, hits, "DIR", _history(6))
    text = _system(messages)
    assert all(f"[kb:{i}]" in text for i in range(4))
    assert "DIR" in text
    assert len(messages) == 7


def test_module_exports() -> None:
    assert callable(prompt.compose)


def test_directory_for_that_overshoots_is_shrunk_again_then_dropped(monkeypatch) -> None:
    monkeypatch.setattr(settings.brain, "prompt_budget_tokens", 500)
    calls: list[int] = []

    def stubborn(max_chars: int) -> str:
        calls.append(max_chars)
        return "Z" * (max_chars + 400) if len(calls) < 3 else ""

    messages = compose(CallState(), CONFIG, [], "Z" * 5000, [], directory_for=stubborn)
    assert len(calls) == 3
    assert calls[1] < calls[0]
    assert "ZZZZ" not in _system(messages)
    assert _tokens(messages) <= 500


def test_a_cut_history_starts_with_the_caller_so_the_system_text_leads_the_prompt() -> None:
    # The gemma2 template folds the system text into the first user turn. A cut history that
    # starts with an assistant turn puts a different reply in front of it every turn, and the
    # server's prefix cache misses (probe: 600-700 ms first token from the fourth turn on).
    history = _history(9)  # turn0 (user) .. turn8; the last six start with turn3, an assistant
    kept = compose(CallState(), CONFIG, [], "", history)[1:]
    assert kept[0]["role"] == "user"
    assert kept[0]["content"].startswith("turn4")
    assert kept[-1]["content"].startswith("turn8")
    assert len(kept) == 5


def test_an_uncut_history_keeps_the_greeting_first() -> None:
    history = [{"role": "assistant", "content": "GREETING"}, *_history(1)]
    kept = compose(CallState(), CONFIG, [], "", history)[1:]
    assert kept[0]["content"] == "GREETING"


def test_budget_trimming_never_cuts_history_below_the_minimum(monkeypatch) -> None:
    # Leading with the caller must not drop the clinic's last question the caller is answering
    # ("হ্যাঁ" is meaningless without "shall I book 5 pm?").
    monkeypatch.setattr(settings.brain, "prompt_budget_tokens", 450)
    history = _history(5, size=300)  # user, assistant, user, assistant, user
    kept = compose(CallState(), CONFIG, [], "", history)[1:]
    assert [m["content"][:5] for m in kept] == ["turn3", "turn4"]
    assert len(kept) == prompt.MIN_HISTORY
