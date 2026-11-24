"""The mishearing model: confusions learned from real recognition errors, applied to text."""

from __future__ import annotations

import random
import re
import sqlite3
from datetime import date
from pathlib import Path

import pytest

from shefa.config.settings import settings
from shefa.lab.mishear import Confusions, mishear
from shefa.lab.runner import Lab, word_error_rate
from shefa.lab.scenarios import Scenario

CLINIC = Path(__file__).resolve().parents[2] / "configs" / "clinic.example.yaml"
DIGIT = re.compile(r"[0-9০-৯]")


def test_from_pairs_learns_substitutions_and_drops():
    c = Confusions.from_pairs([("আমি দেখাতে চাই", "আমি ডাকাতে চাই"), ("কাল সকালে আসব", "কাল আসব")])
    assert c.subs["দেখাতে"] == ["ডাকাতে"]
    assert c.drop_rate == pytest.approx(1 / 6)


def test_from_pairs_ignores_unaligned_blocks_and_repeats():
    c = Confusions.from_pairs([("ক খ গ", "ক ঘ"), ("ক খ", "ক ঘ"), ("ক খ", "ক ঘ")])
    # "খ গ" -> "ঘ" has unequal lengths, so it teaches nothing; "খ -> ঘ" is stored once.
    assert c.subs == {"খ": ["ঘ"]}
    assert c.drop_rate == 0.0


def test_mishear_rate_zero_is_identity():
    c = Confusions({"দেখাতে": ["ডাকাতে"]}, 0.5)
    assert mishear("ডাক্তার দেখাতে চাই", c, 0.0, random.Random(1)) == "ডাক্তার দেখাতে চাই"


def test_mishear_rate_one_swaps_known_words_and_keeps_digits():
    c = Confusions({"দেখাতে": ["ডাকাতে"]}, 1.0)
    out = mishear("01711 দেখাতে", c, 1.0, random.Random(1))
    assert out.startswith("01711") and "ডাকাতে" in out


def test_digits_are_never_dropped_even_when_everything_else_is():
    c = Confusions({}, 1.0)
    out = mishear("আমার নম্বর 01711 ৪৫ b2 হলো", c, 1.0, random.Random(3))
    assert out.split() == ["01711", "৪৫", "b2"]


def test_same_seed_same_mishearing():
    c = Confusions({"ক": ["খ", "গ"], "চ": ["ছ"]}, 0.3)
    text = "ক চ ক চ ক চ ক চ ক চ"
    a = mishear(text, c, 0.6, random.Random(7))
    b = mishear(text, c, 0.6, random.Random(7))
    assert a == b and a != text


def test_empty_table_changes_nothing():
    assert mishear("ক খ গ", Confusions({}, 0.0), 1.0, random.Random(1)) == "ক খ গ"


def test_missing_or_broken_db_gives_empty_table(tmp_path):
    assert Confusions.from_collector_db(tmp_path / "nope.db").subs == {}
    (tmp_path / "bad.db").write_text("not a database")
    assert Confusions.from_collector_db(tmp_path / "bad.db").subs == {}


def test_db_without_a_clips_table_gives_empty_table(tmp_path):
    db = tmp_path / "other.db"
    con = sqlite3.connect(db)
    con.execute("create table something (x text)")
    con.commit()
    con.close()
    assert Confusions.from_collector_db(db) == Confusions({}, 0.0)


def _clips_db(tmp_path, rows, name="c.db"):
    db = tmp_path / name
    con = sqlite3.connect(db)
    con.execute("create table clips (expected_text text, draft_text text, final_text text)")
    con.executemany("insert into clips values (?, ?, ?)", rows)
    con.commit()
    con.close()
    return db


def test_from_collector_db_reads_reviewed_text_first(tmp_path):
    db = _clips_db(tmp_path, [("ক খ", "ক গ", "ক ঘ")])
    assert Confusions.from_collector_db(db).subs == {"ঘ": ["গ"]}


def test_from_collector_db_falls_back_to_expected_and_skips_empty_drafts(tmp_path):
    db = _clips_db(
        tmp_path,
        [("ক খ", "ক গ", ""), ("ক খ", "ক চ", None), ("ক ছ", "", "ক ছ"), ("ক ছ", None, None)],
    )
    assert Confusions.from_collector_db(db).subs == {"খ": ["গ", "চ"]}


def test_from_collector_db_is_read_only_and_handles_spaces_in_the_path(tmp_path):
    folder = tmp_path / "a folder #1"
    folder.mkdir()
    db = _clips_db(folder, [("ক খ", "ক গ", None)])
    before = db.read_bytes()
    assert Confusions.from_collector_db(db).subs == {"খ": ["গ"]}
    assert db.read_bytes() == before


def test_save_and_load_round_trip(tmp_path):
    c = Confusions({"দেখাতে": ["ডাকাতে", "দেখতে"]}, 0.125)
    c.save(tmp_path / "t.json")
    assert Confusions.load(tmp_path / "t.json") == c
    assert "দেখাতে" in (tmp_path / "t.json").read_text(encoding="utf-8")


class TestLabHook:
    @pytest.fixture
    def make_lab(self, tmp_path, monkeypatch):
        from shefa.models.registry import registry

        class Llm:
            async def stream_chat(self, *args, **kwargs):  # pragma: no cover - never reached
                raise AssertionError("the greeting turn should not call the model")

        monkeypatch.setattr(settings.pipeline.llm, "tool_calls", False)
        monkeypatch.setattr(settings.pipeline.llm, "filler_after_s", 0)
        monkeypatch.setattr(settings.languages, "primary", "bn")
        monkeypatch.setattr(registry, "_llm", Llm())
        return lambda **kw: Lab(
            clinic_file=CLINIC, work_dir=tmp_path / "work", today=date(2026, 11, 4), **kw
        )

    SAID = "ডাক্তার দেখাতে চাই 01711"
    SCENARIO = Scenario(id="m", title="t", tests="t", phone="01711000001", turns=[SAID, SAID])

    async def test_the_text_path_is_untouched_without_a_rate(self, make_lab):
        table = Confusions({"দেখাতে": ["ডাকাতে"]}, 0.0)
        lab = make_lab(mishear=table, mishear_rate=0.0)
        result = await lab.run(self.SCENARIO)
        assert [t.heard for t in result.turns] == [self.SAID, self.SAID]
        assert all(t.wer is None for t in result.turns)

    async def test_with_a_rate_the_agent_hears_the_mangled_line_and_the_wer_is_recorded(
        self, make_lab
    ):
        table = Confusions({"দেখাতে": ["ডাকাতে"]}, 0.0)
        lab = make_lab(mishear=table, mishear_rate=1.0, seed=5)
        result = await lab.run(self.SCENARIO)
        assert result.error is None
        for turn in result.turns:
            assert turn.said == self.SAID
            assert turn.heard == "ডাক্তার ডাকাতে চাই 01711"
            assert turn.wer == word_error_rate(turn.said, turn.heard) == pytest.approx(0.25)

    async def test_the_same_seed_reproduces_a_run(self, make_lab):
        table = Confusions({"দেখাতে": ["ডাকাতে"], "চাই": ["চায়"]}, 0.0)
        heard = []
        for _ in range(2):
            lab = make_lab(mishear=table, mishear_rate=0.5, seed=11)
            result = await lab.run(self.SCENARIO)
            heard.append([t.heard for t in result.turns])
        assert heard[0] == heard[1]
