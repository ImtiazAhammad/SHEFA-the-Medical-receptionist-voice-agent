"""A model's written-out reasoning (<think>…</think>) never reaches the caller."""

from __future__ import annotations

import pytest

from shefa.models.llm.think_filter import ThinkFilter, strip_thinking


def _stream(chunks: list[str]) -> str:
    f = ThinkFilter()
    return "".join(f.feed(c) for c in chunks) + f.flush()


def test_a_reply_without_reasoning_passes_untouched():
    assert strip_thinking("ডাক্তার রবিবার বসেন।") == "ডাক্তার রবিবার বসেন।"


def test_a_reasoning_block_and_the_space_after_it_are_removed():
    assert strip_thinking("<think>\nthe user wants…\n</think>\n\nআমি দেখছি।") == "আমি দেখছি।"


def test_an_empty_reasoning_block_is_removed():
    assert strip_thinking("<think>\n\n</think>\n\nহ্যাঁ।") == "হ্যাঁ।"


def test_reasoning_cut_off_before_it_closes_says_nothing():
    assert strip_thinking("<think>\nOkay, so the patient") == ""


@pytest.mark.parametrize(
    "chunks",
    [
        ["<think>\nhmm\n</think>\n\nআমি ", "দেখছি।"],
        ["<thi", "nk>hmm</th", "ink>", "আমি দেখছি।"],
        ["<", "think>", "hmm", "<", "/think>", "\n", "আমি দেখছি।"],
        ["আমি দেখছি।"],
        ["আমি ", "দেখছি।"],
    ],
)
def test_streamed_reasoning_is_removed_wherever_the_chunks_split_it(chunks):
    assert _stream(chunks) == "আমি দেখছি।"


def test_a_lone_angle_bracket_in_a_reply_is_kept():
    assert _stream(["2 < 3", " and done"]) == "2 < 3 and done"


def test_nothing_is_held_back_once_the_text_cannot_be_a_tag():
    f = ThinkFilter()
    assert f.feed("আমি দেখছি।") == "আমি দেখছি।"
    assert f.flush() == ""


def test_streamed_reasoning_that_never_closes_says_nothing():
    assert _stream(["<think>", "the patient is"]) == ""
