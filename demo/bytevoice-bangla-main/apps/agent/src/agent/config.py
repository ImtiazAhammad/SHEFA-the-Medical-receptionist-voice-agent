from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from agent.constants import VoiceEngine


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")

    voice_engine: VoiceEngine = VoiceEngine.GEMINI_LIVE
    agent_name: str = "bytevoice-bn"
    max_call_seconds: int = 300

    gemini_live_model: str = "gemini-3.8-live"
    gemini_live_voice: str = "Kore"

    pipeline_stt_model: str = "gemini-3.5-transcribe-live"
    pipeline_llm_model: str = "gemini-2.5-flash"
    pipeline_tts_model: str = "gemini-3.8-flash-tts"
    pipeline_tts_voice: str = "Aoede"

    extraction_model: str = "gemini-2.5-flash"
    extraction_fallback_model: str = "gemini-2.5-flash-lite"
    google_api_key: str = ""

    supabase_url: str = ""
    supabase_service_role_key: str = ""
    clinic_id: str = "a7c1e5d2-1b3f-4c8e-9d20-5e6f7a8b9c01"

    internal_api_token: str = ""
    allowed_origins: str = "http://localhost:3000"
    user_away_timeout_seconds: float = 8.0


@lru_cache
def get_settings() -> AgentSettings:
    return AgentSettings()
