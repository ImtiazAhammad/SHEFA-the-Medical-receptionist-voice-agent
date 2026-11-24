"""The judge: a second model scores a whole call; parsing never raises on bad output."""

from __future__ import annotations

from shefa.lab.judge import DIMENSIONS, RUBRIC, JudgeScore, agreement, judge_call
from shefa.lab.scenarios import Scenario
from shefa.models.base import LLMResult


class FakeLLM:
    def __init__(self, text: str):
        self.text = text
        self.calls: list[list[dict[str, str]]] = []

    async def generate(self, messages):
        self.calls.append(messages)
        return LLMResult(text=self.text)


def scenario(language: str = "bn") -> Scenario:
    return Scenario(
        id="s",
        title="t",
        tests="an angry caller is calmed",
        language=language,
        caller_type="angry",
        goal="booking",
    )


async def test_parses_fenced_json_and_clamps():
    llm = FakeLLM('```json\n{"warmth": 7, "feelings_first": 0, "note": "ok"}\n```')
    s = await judge_call(llm, scenario(), [("patient", "hi"), ("agent", "hello")])
    assert s.scores == {"warmth": 5, "feelings_first": 1} and s.note == "ok"


async def test_prose_reply_gives_none():
    assert await judge_call(FakeLLM("The agent was polite."), scenario(), []) is None


async def test_no_known_dimension_gives_none():
    assert await judge_call(FakeLLM('{"mood": 3}'), scenario(), []) is None
    assert await judge_call(FakeLLM("{not json}"), scenario(), []) is None
    assert await judge_call(FakeLLM("[1, 2]"), scenario(), []) is None


async def test_coerces_strings_ignores_unknown_and_bad_values():
    reply = (
        'Sure: {"warmth": "4", "natural_bangla": 3.6, "no_repetition": "x",'
        ' "bogus": 5, "phone_clarity": true}'
    )
    s = await judge_call(FakeLLM(reply), scenario(), [])
    assert s.scores == {"warmth": 4, "natural_bangla": 4}
    assert s.note == ""


async def test_skips_a_bad_first_brace_span():
    s = await judge_call(FakeLLM('{oops} then {"tactful_limits": 2}'), scenario(), [])
    assert s.scores == {"tactful_limits": 2}


async def test_prompt_has_rubric_context_and_transcript():
    llm = FakeLLM('{"warmth": 3}')
    await judge_call(llm, scenario(), [("patient", "ডাক্তার কই?"), ("agent", "আমি দেখছি।")])
    system, user = llm.calls[0]
    assert system == {"role": "system", "content": RUBRIC}
    for text in (
        "angry",
        "booking",
        "an angry caller is calmed",
        "Caller: ডাক্তার কই?",
        "SHEFA: আমি দেখছি।",
    ):
        assert text in user["content"]
    for name in DIMENSIONS:
        assert name in RUBRIC


async def test_english_call_is_marked_for_the_judge():
    llm = FakeLLM('{"warmth": 3}')
    await judge_call(llm, scenario("en"), [])
    assert "English" in llm.calls[0][1]["content"]


def test_dimensions_order_and_mean():
    assert DIMENSIONS == (
        "warmth",
        "feelings_first",
        "no_repetition",
        "phone_clarity",
        "natural_bangla",
        "tactful_limits",
        "recovers_mishearing",
    )
    assert JudgeScore({"warmth": 4, "phone_clarity": 5}).mean == 4.5
    assert JudgeScore({}).mean is None


def test_agreement_counts_within_one():
    a = agreement({"x": JudgeScore({"warmth": 4})}, {"x": {"warmth": 2}})
    assert a == {"n": 1, "mean_abs_diff": 2.0, "within_one": 0.0}


def test_agreement_uses_shared_ids_and_dimensions_only():
    judge = {
        "a": JudgeScore({"warmth": 4, "phone_clarity": 3}),
        "b": JudgeScore({"warmth": 1}),
        "only_judge": JudgeScore({"warmth": 5}),
    }
    human = {
        "a": {"warmth": 5, "natural_bangla": 1},
        "b": {"warmth": 3},
        "only_human": {"warmth": 1},
    }
    assert agreement(judge, human) == {"n": 2, "mean_abs_diff": 1.5, "within_one": 0.5}


def test_agreement_with_nothing_shared():
    assert agreement({}, {}) == {"n": 0, "mean_abs_diff": None, "within_one": None}
