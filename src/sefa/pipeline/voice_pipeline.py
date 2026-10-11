"""Core voice pipeline: STT -> Language Detection -> LLM -> TTS.

Orchestrates the full real-time conversation loop for each call session.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from sefa.audio import AudioFrame

    # D-ENG21: the pipeline is handed a *sink*, not a queue. `MediaQueues.put_playback`
    # carries the put timeout; a bare `asyncio.Queue` does not, so a queue passed in
    # here turns a stalled playback consumer into a call that hangs forever.
    PlaybackSink = Callable[[AudioFrame], Awaitable[None]]

from sefa.config.settings import settings
from sefa.models.base import Language
from sefa.models.registry import registry
from sefa.pipeline.actions import confirmation_text, extract_action, tool_result_note
from sefa.pipeline.error_taxonomy import (
    FailureKind,
    MalformedLLMOutputError,
    backoff_delay,
)
from sefa.pipeline.language_detector import evaluate_transcript
from sefa.pipeline.vad import EnergyVAD
from sefa.session.manager import CallSession, SessionManager
from sefa.session.messages import build_messages
from sefa.tools.definitions import get_tool_definitions
from sefa.tools.executor import execute_tool

logger = logging.getLogger(__name__)

DEFAULT_TERMINAL_PROMPT = (
    "I'm having trouble hearing you, so I'll connect you to our front desk. "
    "Please hold, or press star at any time."
)

DEFAULT_OTHER_LANGUAGE_PROMPT = (
    "I'll connect you to our front desk now. Please hold, or press star for a callback."
)

# A sentence ends at a Bangla danda, a run of terminal punctuation, a newline,
# or a period followed by whitespace/end-of-string (so "3.5" and URLs survive).
_SENTENCE_BOUNDARY = re.compile(r"[।?!\n]+|\.(?=\s|$)")


class _SynthesisError(Exception):
    """Internal marker: a failure came from synthesis, not the model."""


def split_complete_sentences(text: str) -> tuple[list[str], str]:
    """Split ``text`` into finished sentences, returning them plus the tail.

    The tail is the fragment after the last boundary — it has no closing
    punctuation yet, so speaking it now would cut a word in half. The caller
    keeps it buffered until more tokens arrive (or the stream ends).
    """
    sentences: list[str] = []
    start = 0
    for match in _SENTENCE_BOUNDARY.finditer(text):
        sentence = text[start : match.end()].strip()
        if sentence:
            sentences.append(sentence)
        start = match.end()
    return sentences, text[start:]


async def speak_to(
    tts: Any,
    text: str,
    language: str,
    put_playback: PlaybackSink,
) -> None:
    """Stream a reply to `put_playback` one sentence at a time.

    `synthesize` builds the whole utterance before returning, so a push after it
    leaves the patient hearing nothing for the full synthesis latency. Piper
    yields one chunk per sentence, so the first audio moves while the rest is
    still being generated. A barge-in during a long reply therefore stops
    synthesis instead of finishing audio nobody will hear.
    """
    async for frame in tts.synthesize_stream(text, language=language):
        if not frame.is_empty:
            await put_playback(frame)


class VoicePipeline:
    """Real-time voice conversation pipeline."""

    def __init__(self) -> None:
        self._session_manager = SessionManager()
        self._buffer_duration_ms: int = 800
        self._audio_buffers: dict[str, list[bytes]] = {}
        # Consecutive classified turn failures per call; reset on the next
        # successful turn (D-ENG12). `_sleep` is an instance seam so tests
        # can observe the backoff without sleeping.
        self._failures: dict[str, int] = {}
        self._sleep = asyncio.sleep

    async def process_audio_stream(
        self,
        call_sid: str,
        audio_queue: asyncio.Queue[bytes],
        put_playback: PlaybackSink,
    ) -> None:
        """Process incoming audio from a call and stream TTS responses back."""
        session = await self._session_manager.get_or_create(call_sid)

        if session.state == "greeting":
            greetings = settings.languages.default_greeting
            greeting = greetings.get(
                session.language.value,
                greetings.get("en", ""),
            )
            tts = await registry.get_tts()
            await speak_to(tts, greeting, session.language.value, put_playback)
            session.add_turn("assistant", greeting)
            session.state = "active"
            await self._session_manager.save(session)

        self._audio_buffers.setdefault(call_sid, [])
        stt = await registry.get_stt()
        llm = await registry.get_llm()

        # Turn segmentation is owned by the RMS VAD (D-ENG11), not by a silent
        # tick count. Whisper's vad_filter stays as an internal per-utterance
        # filter: it trims leading/trailing silence inside the audio we hand
        # it. The pipeline decides where one utterance ends and the next
        # begins, using an adaptive noise floor and an explicit max_buffer
        # flush so a noisy clinic room can neither stall a turn nor grow the
        # buffer without bound.
        vad = EnergyVAD()

        while True:
            try:
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.1)
                self._audio_buffers[call_sid].append(chunk)
                decision = vad.update(chunk)
            except TimeoutError:
                decision = vad.tick_silence()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Pipeline error for %s", call_sid)
                self._audio_buffers.setdefault(call_sid, [])
                continue

            if not decision.flush:
                continue

            buffer = b"".join(self._audio_buffers.pop(call_sid, []))
            if not buffer or len(buffer) < 1600:
                self._audio_buffers.setdefault(call_sid, [])
                continue

            # Log what the VAD actually handed on, so a silent caller can be
            # told apart from one the codec mangled upstream: RMS below the
            # gate means no turn, near-zero means the bytes are not speech.
            samples = np.frombuffer(buffer, dtype="<i2").astype(np.float64)
            _rms = float(np.sqrt((samples**2).mean()))
            logger.info(
                "VAD flush [%s]: %.2fs, %d bytes, rms=%.0f",
                call_sid,
                len(buffer) / 32000,
                len(buffer),
                _rms,
            )

            # Named rescue paths (D-ENG12): a failure is classified, counted,
            # backed off exponentially, and after max_transfer_attempts the
            # call is closed with a courtesy + DTMF/transfer prompt instead
            # of the old bare except-swallow-and-continue hot loop.
            try:
                start = time.monotonic()
                stt_result = await stt.transcribe(buffer)
                stt_ms = (time.monotonic() - start) * 1000
                logger.info(
                    "STT [%s]: '%s' (lang=%s, %.0fms)",
                    call_sid,
                    stt_result.text,
                    stt_result.language.value,
                    stt_ms,
                )
            except asyncio.CancelledError:
                break
            except TimeoutError:
                if await self._rescue(
                    call_sid, session, put_playback, FailureKind.STT_TIMEOUT
                ):
                    break
                self._audio_buffers.setdefault(call_sid, [])
                continue
            except Exception:
                if await self._rescue(
                    call_sid, session, put_playback, FailureKind.STT_ERROR
                ):
                    break
                self._audio_buffers.setdefault(call_sid, [])
                continue

            if not stt_result.text.strip():
                logger.info(
                    "STT [%s]: heard nothing from %.2fs of audio "
                    "(rms=%.0f, lang=%s, conf=%.2f) — codec or mic problem?",
                    call_sid,
                    len(buffer) / 32000,
                    _rms,
                    stt_result.language.value,
                    stt_result.confidence,
                )
                self._audio_buffers.setdefault(call_sid, [])
                if await self._rescue(
                    call_sid, session, put_playback, FailureKind.EMPTY_TRANSCRIPTION
                ):
                    break
                continue

            detected_lang = stt_result.language
            if detected_lang == Language.OTHER:
                # D-ENG16: neither-en-nor-bn is an explicit route, not English.
                # Coercing it to ENGLISH made the agent reply in the wrong
                # language; instead the caller gets a warm transfer/DTMF offer
                # and the loop leaves. No reply is ever generated for it.
                other_prompt = settings.escalation.other_language_prompt.get(
                    session.language.value,
                    settings.escalation.other_language_prompt.get(
                        "en", DEFAULT_OTHER_LANGUAGE_PROMPT
                    ),
                )
                tts = await registry.get_tts()
                await speak_to(tts, other_prompt, "en", put_playback)
                session.add_turn("assistant", other_prompt, Language.OTHER)
                session.state = "escaped"
                await self._session_manager.save(session)
                logger.info(
                    "Unsupported language %s on %s; offered warm transfer",
                    detected_lang.value,
                    call_sid,
                )
                break

            if detected_lang != session.language:
                session.language = detected_lang
                logger.info("Language switched to %s for %s", detected_lang.value, call_sid)

            decision = evaluate_transcript(
                stt_result.text, session.language, stt_result.confidence
            )

            if decision.should_escalate:
                escalation_msg = settings.escalation.transfer_greeting.get(
                    session.language.value,
                    settings.escalation.transfer_greeting.get("en", "Transferring you now."),
                )
                tts = await registry.get_tts()
                await speak_to(tts, escalation_msg, session.language.value, put_playback)
                session.add_turn("assistant", escalation_msg, session.language)
                session.state = "escalated"
                await self._session_manager.save(session)
                break

            if decision.needs_repeat:
                repeat_msg = settings.escalation.repeat_prompt.get(
                    session.language.value,
                    settings.escalation.repeat_prompt.get(
                        "en", "Sorry, I didn't catch that. Could you repeat?"
                    ),
                )
                tts = await registry.get_tts()
                await speak_to(tts, repeat_msg, session.language.value, put_playback)
                session.add_turn("assistant", repeat_msg, session.language)
                self._audio_buffers.setdefault(call_sid, [])
                continue

            session.add_turn("user", stt_result.text, detected_lang)
            tts = await registry.get_tts()

            try:
                start = time.monotonic()
                reply_text = await self._generate_reply(
                    llm, tts, session, put_playback
                )
                llm_ms = (time.monotonic() - start) * 1000
                logger.info("LLM [%s]: '%s' (%.0fms)", call_sid, reply_text[:80], llm_ms)
            except asyncio.CancelledError:
                break
            except _SynthesisError as exc:
                logger.error("TTS failed for %s: %s", call_sid, exc)
                if await self._rescue(
                    call_sid, session, put_playback, FailureKind.TTS_FAILURE
                ):
                    break
                self._audio_buffers.setdefault(call_sid, [])
                continue
            except Exception as exc:
                # Log the cause before classifying: a bare `except` that
                # reports only MALFORMED_LLM_OUTPUT hides transport faults
                # (an unsupported tool_choice, a dead server) behind a label
                # that points at the model's output instead.
                logger.error(
                    "LLM call failed for %s: %s: %s",
                    call_sid,
                    type(exc).__name__,
                    exc,
                )
                if await self._rescue(
                    call_sid, session, put_playback, FailureKind.MALFORMED_LLM_OUTPUT
                ):
                    break
                self._audio_buffers.setdefault(call_sid, [])
                continue

            session.add_turn("assistant", reply_text, session.language)
            await self._session_manager.save(session)
            self._failures[call_sid] = 0  # a successful turn resets the counter
            self._audio_buffers.setdefault(call_sid, [])

    async def _stream_reply(
        self,
        llm: Any,
        tts: Any,
        messages: list[dict[str, Any]],
        tools: list[Any],
        language: str,
        put_playback: PlaybackSink,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Speak a reply sentence-by-sentence as the model streams it.

        A non-streaming ``generate()`` made the patient wait for the *whole*
        reply before the first sound. Here each finished sentence is synthesized
        the moment its final token arrives, so time-to-first-audio is governed
        by the first sentence, not the last. Tool calls are surfaced by the
        adapter after the text; the returned text is what enters history.
        """
        text_parts: list[str] = []
        pending = ""
        tool_calls: list[dict[str, Any]] = []
        async for event in llm.generate_events(messages, tools=tools):
            if event.tool_calls:
                tool_calls = event.tool_calls
            if not event.text:
                continue
            text_parts.append(event.text)
            pending += event.text
            sentences, pending = split_complete_sentences(pending)
            for sentence in sentences:
                await self._emit(tts, sentence, language, put_playback)

        remainder = pending.strip()
        if remainder:
            await self._emit(tts, remainder, language, put_playback)

        reply_text = "".join(text_parts)
        if not reply_text.strip() and not tool_calls:
            raise MalformedLLMOutputError("LLM stream produced no text or tool calls")
        return reply_text, tool_calls

    async def _generate_reply(
        self,
        llm: Any,
        tts: Any,
        session: CallSession,
        put_playback: PlaybackSink,
    ) -> str:
        """Stream a reply for the latest user turn and, when the model acts,
        the grounded confirmation that follows.

        Two modes, chosen by ``settings.pipeline.llm.tool_calls``:

        * Native tool_calls (Qwen/vLLM with a tool parser, cloud models): the
          reply streams with the tool definitions attached and the calls the
          model declares are executed; a grounded confirmation then streams.
        * Bangla pilot (Gemma-2): Ollama's gemma2 rejects any request carrying
          a ``tools`` array, so the reply streams as plain chat and the
          structured-JSON router decides whether to act. The tool result is
          injected into the follow-up request as a *context note* (not a tool
          message, which gemma2 also rejects) so the confirmation only says
          what the tool actually did.
        """
        messages = build_messages(session)
        if not settings.pipeline.llm.tool_calls:
            reply_text, _tool_calls = await self._stream_reply(
                llm, tts, messages, [], session.language.value, put_playback
            )
            action = await extract_action(llm, session)
            if action is not None:
                tool_result = await execute_tool(
                    action.name, action.arguments, session
                )
                # Facts (date/time/doctor/ID) come from the tool result rendered
                # in code, spoken verbatim; the model never gets to re-state
                # them. Only untemplated tools fall back to a grounded model
                # reply, with the result folded into the LEADING system message
                # (gemma2's chat template reads a trailing one loosely).
                fixed = confirmation_text(
                    action.name, tool_result, session.language.value
                )
                if fixed is not None:
                    await self._emit(
                        tts, fixed, session.language.value, put_playback
                    )
                    return fixed
                messages = build_messages(session)
                messages[0]["content"] += "\n\n" + tool_result_note(
                    action.name, tool_result
                )
                reply_text, _tool_calls = await self._stream_reply(
                    llm, tts, messages, [], session.language.value, put_playback
                )
            return reply_text

        tools = get_tool_definitions()
        reply_text, tool_calls = await self._stream_reply(
            llm, tts, messages, tools, session.language.value, put_playback
        )
        if not tool_calls:
            return reply_text

        # The assistant turn that declared the calls must stay in history: a
        # request carrying a `tool` message without the assistant `tool_calls`
        # message in front of it is rejected by OpenAI/Qwen-compatible servers
        # (D-ENG15).
        session.add_turn(
            "assistant",
            reply_text,
            session.language,
            tool_calls=tool_calls,
        )
        for tc in tool_calls:
            tool_result = await execute_tool(tc["name"], tc["arguments"], session)
            session.add_turn(
                "tool",
                str(tool_result),
                tool_call_id=tc["id"],
                tool_call_name=tc["name"],
            )

        messages = build_messages(session)
        reply_text, _tool_calls = await self._stream_reply(
            llm, tts, messages, tools, session.language.value, put_playback
        )
        return reply_text

    async def _emit(
        self,
        tts: Any,
        text: str,
        language: str,
        put_playback: PlaybackSink,
    ) -> None:
        """Speak one sentence, tagging a synthesis fault for the classifier."""
        try:
            await speak_to(tts, text, language, put_playback)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            raise _SynthesisError(str(exc)) from exc

    async def _rescue(
        self,
        call_sid: str,
        session: CallSession,
        put_playback: PlaybackSink,
        kind: FailureKind,
    ) -> bool:
        """Count a classified failure; back off; return True to close the call.

        ``max_transfer_attempts`` is read from config here, so the setting
        that drives the terminal transition is actually consumed (D-ENG12).
        """
        failures = self._failures.get(call_sid, 0) + 1
        self._failures[call_sid] = failures
        max_attempts = settings.escalation.max_transfer_attempts
        logger.warning(
            "Turn failure %d/%d for %s: %s",
            failures,
            max_attempts,
            call_sid,
            kind.value,
        )
        if failures >= max_attempts:
            await self._close_call(call_sid, session, put_playback)
            return True
        delay = backoff_delay(failures)
        logger.info("Backing off %.2fs after %s for %s", delay, kind.value, call_sid)
        await self._sleep(delay)
        return False

    async def _close_call(
        self,
        call_sid: str,
        session: CallSession,
        put_playback: PlaybackSink,
    ) -> None:
        """Terminal transition: courtesy + DTMF/transfer, then end the call."""
        prompt = settings.escalation.terminal_prompt.get(
            session.language.value,
            settings.escalation.terminal_prompt.get("en", DEFAULT_TERMINAL_PROMPT),
        )
        tts = await registry.get_tts()
        await speak_to(tts, prompt, session.language.value, put_playback)
        session.add_turn("assistant", prompt, session.language)
        session.state = "terminated"
        await self._session_manager.save(session)
        logger.warning(
            "Call %s closed after %d consecutive failures",
            call_sid,
            self._failures.get(call_sid, 0),
        )

    async def cleanup(self, call_sid: str) -> None:
        self._audio_buffers.pop(call_sid, None)
        self._failures.pop(call_sid, None)
        logger.info("Cleaned up pipeline for %s", call_sid)
