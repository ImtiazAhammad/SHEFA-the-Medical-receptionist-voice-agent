"""Core voice pipeline: STT -> Language Detection -> LLM -> TTS.

Orchestrates the full real-time conversation loop for each call session.
"""

from __future__ import annotations

import asyncio
import logging
import time

from sefa.config.settings import settings
from sefa.models.base import Language
from sefa.models.registry import registry
from sefa.pipeline.language_detector import needs_escalation
from sefa.session.manager import CallSession, SessionManager
from sefa.tools.definitions import get_tool_definitions
from sefa.tools.executor import execute_tool

logger = logging.getLogger(__name__)

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


class VoicePipeline:
    """Real-time voice conversation pipeline."""

    def __init__(self) -> None:
        self._session_manager = SessionManager()
        self._buffer_duration_ms: int = 800
        self._audio_buffers: dict[str, list[bytes]] = {}

    async def process_audio_stream(
        self,
        call_sid: str,
        audio_queue: asyncio.Queue[bytes],
        playback_queue: asyncio.Queue[bytes],
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
            audio_result = await tts.synthesize(
                greeting, language=session.language.value
            )
            await playback_queue.put(audio_result.audio_bytes)
            session.add_turn("assistant", greeting)
            session.state = "active"
            await self._session_manager.save(session)

        self._audio_buffers.setdefault(call_sid, [])
        stt = await registry.get_stt()
        llm = await registry.get_llm()

        silence_threshold = 15
        silence_count = 0

        while True:
            try:
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.1)
                self._audio_buffers[call_sid].append(chunk)
                silence_count = 0
            except TimeoutError:
                silence_count += 1
                if silence_count < silence_threshold:
                    continue
                buffer = b"".join(self._audio_buffers.pop(call_sid, []))
                if not buffer or len(buffer) < 1600:
                    self._audio_buffers.setdefault(call_sid, [])
                    continue

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

                if not stt_result.text.strip():
                    self._audio_buffers.setdefault(call_sid, [])
                    continue

                detected_lang = stt_result.language
                if detected_lang != session.language:
                    session.language = detected_lang
                    logger.info("Language switched to %s for %s", detected_lang.value, call_sid)

                if needs_escalation(stt_result.confidence, stt_result.text, session.language):
                    escalation_msg = settings.escalation.transfer_greeting.get(
                        session.language.value,
                        settings.escalation.transfer_greeting.get("en", "Transferring you now."),
                    )
                    tts = await registry.get_tts()
                    audio_result = await tts.synthesize(
                        escalation_msg,
                        language=session.language.value,
                    )
                    await playback_queue.put(audio_result.audio_bytes)
                    session.add_turn("assistant", escalation_msg, Language.BANGLA)
                    session.state = "escalated"
                    await self._session_manager.save(session)
                    break

                session.add_turn("user", stt_result.text, detected_lang)
                messages = self._build_messages(session)
                tools = get_tool_definitions()

                start = time.monotonic()
                llm_result = await llm.generate(messages, tools=tools)
                llm_ms = (time.monotonic() - start) * 1000
                logger.info("LLM [%s]: '%s' (%.0fms)", call_sid, llm_result.text[:80], llm_ms)

                if llm_result.tool_calls:
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

                tts = await registry.get_tts()
                audio_result = await tts.synthesize(
                    llm_result.text,
                    language=session.language.value,
                )
                await playback_queue.put(audio_result.audio_bytes)
                session.add_turn("assistant", llm_result.text, llm_result.language)
                await self._session_manager.save(session)
                self._audio_buffers.setdefault(call_sid, [])

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Pipeline error for %s", call_sid)
                self._audio_buffers.setdefault(call_sid, [])
                continue

    def _build_messages(self, session: CallSession) -> list[dict[str, str]]:
        system = SYSTEM_PROMPT_TEMPLATE.format(
            language=session.language.value,
            patient_name=session.patient_name or "Unknown",
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        for turn in session.history:
            if turn.role == "tool":
                messages.append({
                    "role": "tool",
                    "content": turn.content,
                })
            else:
                messages.append({"role": turn.role, "content": turn.content})
        return messages

    async def cleanup(self, call_sid: str) -> None:
        self._audio_buffers.pop(call_sid, None)
        logger.info("Cleaned up pipeline for %s", call_sid)
