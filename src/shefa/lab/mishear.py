"""A text-level model of speech-recognition mistakes, learned from real recordings.

The voice-collection portal stores, for every clip, what the volunteer was asked to say,
what the machine transcribed (`draft_text`) and, once reviewed, the corrected text. Lining
the two up word by word shows which words the machine really confuses and how often it
swallows a word. `mishear` then replays those mistakes on a simulated caller's line, so the
agent in the test bench receives text the way it would after a phone line and a recogniser.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import quote

if TYPE_CHECKING:
    import random

_DIGIT = re.compile(r"[0-9০-৯]")

_PAIRS_SQL = """
    select coalesce(nullif(final_text, ''), expected_text), draft_text from clips
    where coalesce(nullif(final_text, ''), expected_text) <> ''
      and draft_text <> ''
"""


@dataclass
class Confusions:
    """`subs`: word said -> words the machine has heard instead; `drop_rate`: words lost."""

    subs: dict[str, list[str]] = field(default_factory=dict)
    drop_rate: float = 0.0

    @classmethod
    def from_pairs(cls, pairs: list[tuple[str, str]]) -> Confusions:
        """Learn from `(what was said, what the machine heard)` pairs."""
        subs: dict[str, list[str]] = {}
        said_words = dropped = 0
        for said, heard in pairs:
            a, b = said.split(), heard.split()
            said_words += len(a)
            for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
                if tag == "delete":
                    dropped += i2 - i1
                elif tag == "replace" and i2 - i1 == j2 - j1:
                    for said_word, heard_word in zip(a[i1:i2], b[j1:j2], strict=True):
                        options = subs.setdefault(said_word, [])
                        if heard_word not in options:
                            options.append(heard_word)
        return cls(subs, dropped / said_words if said_words else 0.0)

    @classmethod
    def from_collector_db(cls, path: str | Path) -> Confusions:
        """Learn from the collector database, opened read-only (the server may be writing).

        Anything wrong with the file (missing, not a database, locked, no `clips` table)
        gives an empty table: the bench then runs with no mishearing rather than failing.
        """
        try:
            uri = f"file:{quote(str(Path(path).resolve()))}?mode=ro"
            con = sqlite3.connect(uri, uri=True)
            try:
                rows = con.execute(_PAIRS_SQL).fetchall()
            finally:
                con.close()
            return cls.from_pairs([(str(said), str(heard)) for said, heard in rows])
        except (sqlite3.Error, OSError):
            return cls({}, 0.0)

    def save(self, path: str | Path) -> None:
        payload = {"subs": self.subs, "drop_rate": self.drop_rate}
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> Confusions:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            {word: list(heard) for word, heard in data["subs"].items()},
            float(data["drop_rate"]),
        )


def mishear(text: str, table: Confusions, rate: float, rng: random.Random) -> str:
    """Replay recognition mistakes on `text`.

    Each word the table knows a confusion for is swapped with probability `rate`; any other
    word is dropped with probability `rate * table.drop_rate`. Tokens with a digit (phone
    numbers, times, ages) are never touched, so the bench tests the agent's handling of
    mishearing rather than numbers that no caller could be understood on.
    """
    if rate <= 0:
        return text
    out: list[str] = []
    for word in text.split():
        if _DIGIT.search(word):
            out.append(word)
        elif word in table.subs and rng.random() < rate:
            out.append(rng.choice(table.subs[word]))
        elif rng.random() < rate * table.drop_rate:
            continue
        else:
            out.append(word)
    return " ".join(out)
