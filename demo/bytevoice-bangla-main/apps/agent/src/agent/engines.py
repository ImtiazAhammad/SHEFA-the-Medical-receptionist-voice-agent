import logging

from google.genai import types
from livekit.agents import NOT_GIVEN, AgentSession
from livekit.plugins import google, silero

from agent.config import AgentSettings
from agent.constants import (
    BANGLADESH_LANGUAGE_CODE,
    BANGLADESHI_ACCENT_INSTRUCTIONS,
    LOGGER_NAME,
    RECOGNITION_LANGUAGE_CODES,
    SPEECH_PHRASE_HINTS,
    VoiceEngine,
)

logger = logging.getLogger(LOGGER_NAME)


def build_session(settings: AgentSettings, api_key: str | None = None) -> AgentSession:
    engine = settings.voice_engine
    key = api_key if api_key else NOT_GIVEN
    logger.debug("building agent session", extra={"voice_engine": engine.value})

    if engine is VoiceEngine.GEMINI_LIVE:
        return AgentSession(
            user_away_timeout=settings.user_away_timeout_seconds,
            llm=google.realtime.RealtimeModel(
                model=settings.gemini_live_model,
                api_key=key,
                voice=settings.gemini_live_voice,
                language=BANGLADESH_LANGUAGE_CODE,
                temperature=0.6,
                input_audio_transcription=types.AudioTranscriptionConfig(),
                output_audio_transcription=types.AudioTranscriptionConfig(),
            ),
        )

    if engine is VoiceEngine.GEMINI_PIPELINE:
        return AgentSession(
            user_away_timeout=settings.user_away_timeout_seconds,
            vad=silero.VAD.load(),
            stt=google.beta.GeminiSTT(
                model=settings.pipeline_stt_model,
                api_key=key,
                language_codes=RECOGNITION_LANGUAGE_CODES,
                custom_vocabulary=SPEECH_PHRASE_HINTS,
            ),
            llm=google.LLM(model=settings.pipeline_llm_model, temperature=0.6, api_key=key),
            tts=google.beta.GeminiTTS(
                model=settings.pipeline_tts_model,
                api_key=key,
                voice_name=settings.pipeline_tts_voice,
                instructions=BANGLADESHI_ACCENT_INSTRUCTIONS,
            ),
        )

    raise ValueError(f"Unsupported voice engine: {engine}")
