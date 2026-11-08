"""Picking a time out of the list the agent just read aloud."""

from __future__ import annotations

import pytest

from shefa.pipeline.choice import pick


@pytest.mark.parametrize(
    ("said", "count", "index"),
    [
        ("the second one", 3, 1),
        ("the last one please", 3, 2),
        ("first", 2, 0),
        ("number two", 3, 1),
        ("দ্বিতীয়টা ঠিক আছে", 3, 1),
        ("শেষেরটা", 4, 3),
        ("২ নম্বর", 3, 1),
        ("the earliest", 3, 0),
    ],
)
def test_a_position_is_a_pick(said, count, index):
    assert pick(said, count) == index


@pytest.mark.parametrize(
    ("said", "count"),
    [
        ("two thirty", 3),  # a clock time, not a position
        ("the second doctor on Tuesday would be fine for me", 3),  # a new request
        ("first or second", 3),  # no clear choice
        ("the third one", 2),  # beyond the list
        ("yes", 3),
        ("", 3),
        ("the second one", 1),  # one option is not a choice
        ("the second one", 9),  # lists this long are summarised, never read out
    ],
)
def test_anything_else_is_left_to_the_router(said, count):
    assert pick(said, count) is None
