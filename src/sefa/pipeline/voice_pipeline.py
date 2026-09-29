"""Core voice pipeline: STT -> Language Detection -> LLM -> TTS.

Orchestrates the full real-time conversation loop for each call session.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from sefa.audio import AudioFrame

from sefa.config.settings import settings
from sefa.models.base import Language
from sefa.models.registry import registry
from sefa.pipeline.error_taxonomy import (
    FailureKind,
    backoff_delay,
    require_llm_result,
)
from sefa.pipeline.language_detector import evaluate_transcript
from sefa.pipeline.vad import EnergyVAD
from sefa.session.manager import CallSession, SessionManager
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

SYSTEM_PROMPT_TEMPLATE = (
    "You are sefa Receptionist, a professional bilingual "
    "(English/Bangla) medical receptionist AI.\n\n"
    "## Core Rules\n"
    "- Always respond in the SAME LANGUAGE the patient is speaking.\n"
    "- If the patient mixes languages (code-switching), respond in "
    "the dominant language.\n"
    "- Be empathetic, professional, and concise.\n"
    "- Never fabricate medical advice. Route clinical questions to "
    "a human.\n"
    "- Use available tools to check schedules, book appointments, "
    "and verify patient info.\n"
    "- For emergencies, immediately inform the patient you are "
    "transferring them.\n\n"
    "## Languages\n"
    "- English (en): Standard professional English.\n"
    "- Bangla (bn): আদর্শ বাংলা, professional and respectful tone.\n\n"
    "## Current Session\n"
    "- Patient language preference: {language}\n"
    "- Patient name: {patient_name}\n"
)


async def speak_to(
    tts: Any,
    text: str,
    language: str,
    playback_queue: asyncio.Queue[AudioFrame],
) -> None:
    """Stream a reply into `playback_queue` one sentence at a time.

    `synthesize` builds the whole utterance before returning, so a push after it
    leaves the patient hearing nothing for the full synthesis latency. Piper
    yields one chunk per sentence, so the first audio moves while the rest is
    still being generated. A barge-in during a long reply therefore stops
    synthesis instead of finishing audio nobody will hear.
    """
    async for frame in tts.synthesize_stream(text, language=language):
        if not frame.is_empty:
            await playback_queue.put(frame)


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
        playback_queue: asyncio.Queue[AudioFrame],
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
            await speak_to(tts, greeting, session.language.value, playback_queue)
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
                    call_sid, session, playback_queue, FailureKind.STT_TIMEOUT
                ):
                    break
                self._audio_buffers.setdefault(call_sid, [])
                continue
            except Exception:
                if await self._rescue(
                    call_sid, session, playback_queue, FailureKind.STT_ERROR
                ):
                    break
                self._audio_buffers.setdefault(call_sid, [])
                continue

            if not stt_result.text.strip():
                self._audio_buffers.setdefault(call_sid, [])
                if await self._rescue(
                    call_sid, session, playback_queue, FailureKind.EMPTY_TRANSCRIPTION
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
                await speak_to(tts, other_prompt, "en", playback_queue)
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
                await speak_to(tts, escalation_msg, session.language.value, playback_queue)
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
                await speak_to(tts, repeat_msg, session.language.value, playback_queue)
                session.add_turn("assistant", repeat_msg, session.language)
                self._audio_buffers.setdefault(call_sid, [])
                continue

            session.add_turn("user", stt_result.text, detected_lang)
            messages = self._build_messages(session)
            tools = get_tool_definitions()

            try:
                start = time.monotonic()
                llm_result = await llm.generate(messages, tools=tools)
                llm_result = require_llm_result(llm_result)
                llm_ms = (time.monotonic() - start) * 1000
                logger.info("LLM [%s]: '%s' (%.0fms)", call_sid, llm_result.text[:80], llm_ms)

                if llm_result.tool_calls:
                    # The assistant turn that declared the calls must stay in
                    # history: a request carrying a `tool` message without the
                    # assistant `tool_calls` message in front of it is rejected
                    # by OpenAI/Qwen-compatible servers (D-ENG15).
                    session.add_turn(
                        "assistant",
                        llm_result.text,
                        llm_result.language,
                        tool_calls=llm_result.tool_calls,
                    )
                    for tc in llm_result.tool_calls:
                        tool_result = await execute_tool(
                            tc["name"], tc["arguments"], session
                        )
                        session.add_turn(
                            "tool",
                            str(tool_result),
                            tool_call_id=tc["id"],
                            tool_call_name=tc["name"],
                        )

                    messages = self._build_messages(session)
                    llm_result = await llm.generate(messages, tools=tools)
                    llm_result = require_llm_result(llm_result)
            except asyncio.CancelledError:
                break
            except Exception:
                if await self._rescue(
                    call_sid, session, playback_queue, FailureKind.MALFORMED_LLM_OUTPUT
                ):
                    break
                self._audio_buffers.setdefault(call_sid, [])
                continue

            try:
                tts = await registry.get_tts()
                await speak_to(tts, llm_result.text, session.language.value, playback_queue)
            except asyncio.CancelledError:
                break
            except Exception:
                if await self._rescue(
                    call_sid, session, playback_queue, FailureKind.TTS_FAILURE
                ):
                    break
                self._audio_buffers.setdefault(call_sid, [])
                continue

            session.add_turn("assistant", llm_result.text, llm_result.language)
            await self._session_manager.save(session)
            self._failures[call_sid] = 0  # a successful turn resets the counter
            self._audio_buffers.setdefault(call_sid, [])

    async def _rescue(
        self,
        call_sid: str,
        session: CallSession,
        playback_queue: asyncio.Queue[AudioFrame],
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
            await self._close_call(call_sid, session, playback_queue)
            return True
        delay = backoff_delay(failures)
        logger.info("Backing off %.2fs after %s for %s", delay, kind.value, call_sid)
        await self._sleep(delay)
        return False

    async def _close_call(
        self,
        call_sid: str,
        session: CallSession,
        playback_queue: asyncio.Queue[AudioFrame],
    ) -> None:
        """Terminal transition: courtesy + DTMF/transfer, then end the call."""
        prompt = settings.escalation.terminal_prompt.get(
            session.language.value,
            settings.escalation.terminal_prompt.get("en", DEFAULT_TERMINAL_PROMPT),
        )
        tts = await registry.get_tts()
        await speak_to(tts, prompt, session.language.value, playback_queue)
        session.add_turn("assistant", prompt, session.language)
        session.state = "terminated"
        await self._session_manager.save(session)
        logger.warning(
            "Call %s closed after %d consecutive failures",
            call_sid,
            self._failures.get(call_sid, 0),
        )

    def _build_messages(self, session: CallSession) -> list[dict[str, Any]]:
        system = SYSTEM_PROMPT_TEMPLATE.format(
            language=session.language.value,
            patient_name=session.patient_name or "Unknown",
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        tools_open = False
        for turn in session.history:
            if turn.role == "tool":
                # A `tool` message is only valid as the answer to an assistant
                # `tool_calls` message; anything else is an orphan (D-ENG15).
                if tools_open:
                    messages.append({"role": "tool", "content": turn.content})
                continue
            tools_open = turn.role == "assistant" and bool(turn.tool_calls)
            msg: dict[str, Any] = {"role": turn.role, "content": turn.content}
            if tools_open:
                msg["tool_calls"] = turn.tool_calls
            messages.append(msg)
        # A trailing declaration with no results after it would be sent as an
        # unanswered ``tool_calls`` request, which the API rejects. Truncation
        # keeps it so pending results can pair up; the request builder is where
        # it is retracted.
        if messages and messages[-1].get("tool_calls"):
            messages.pop()
        return messages

    async def cleanup(self, call_sid: str) -> None:
        self._audio_buffers.pop(call_sid, None)
        self._failures.pop(call_sid, None)
        logger.info("Cleaned up pipeline for %s", call_sid)
