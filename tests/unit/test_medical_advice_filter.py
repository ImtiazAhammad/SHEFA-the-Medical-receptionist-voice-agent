"""The agent never says a dose or a diagnosis, whatever the model writes."""

from __future__ import annotations

import pytest

from shefa.config.settings import settings
from shefa.pipeline.replycheck import gives_medical_advice, speakable


@pytest.mark.parametrize(
    "sentence",
    [
        "Take two tablets of paracetamol every six hours.",
        "Give your child 5 ml of the syrup twice a day.",
        "You probably have a viral infection.",
        "It sounds like dengue.",
        "Your child has pneumonia, so take antibiotics.",
        "প্যারাসিটামল দিনে তিনবার খাবেন।",
        "আপনার বাচ্চার ডেঙ্গু হতে পারে।",
        "৫০০ মিলিগ্রাম ট্যাবলেট খান।",
    ],
)
def test_doses_and_diagnoses_are_blocked(sentence):
    assert gives_medical_advice(sentence)
    assert not speakable(sentence, "bn" if any("ঀ" <= c <= "৿" for c in sentence) else "en")


@pytest.mark.parametrize(
    "sentence",
    [
        "Dr. Rahman sees patients on Sunday at 9 am.",
        "The visit fee is 800 taka.",
        "Please arrive ten minutes early and bring your reports.",
        "ডাক্তার রহমান রবিবার সকাল নয়টায় বসেন।",
        "আপনার অ্যাপয়েন্টমেন্ট নিশ্চিত করা হয়েছে।",
        "The Medicine department has three doctors.",
    ],
)
def test_ordinary_clinic_answers_pass(sentence):
    assert not gives_medical_advice(sentence)


async def test_a_model_that_gives_a_dose_is_replaced_by_the_refusal():
    from shefa.audio import AudioFrame
    from shefa.models.base import StreamEvent
    from shefa.pipeline.voice_pipeline import VoicePipeline

    class Llm:
        async def generate_events(self, messages, tools=None, **kwargs):
            yield StreamEvent(text="Tomorrow at nine is free. ")
            yield StreamEvent(text="Take two tablets of paracetamol. ")
            yield StreamEvent(text="Then rest.")

    spoken: list[str] = []

    class Tts:
        async def synthesize_stream(self, text, language="en"):
            spoken.append(text)
            yield AudioFrame(b"\x00" * 160, rate=22050)

    async def sink(frame):
        return None

    text, _ = await VoicePipeline()._stream_reply(Llm(), Tts(), [], [], "en", sink)

    refusal = settings.escalation.medical_refusal["en"]
    assert spoken[-1] == refusal and "paracetamol" not in text and "tablets" not in text
    assert "Tomorrow at nine is free." in spoken[0]
