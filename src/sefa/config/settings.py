"""Application settings loaded from YAML config and environment variables.

Every model inherits `StrictModel`, so a key that no model declares is a
validation error rather than a silent drop. Config drift is only detectable if
it is loud: the previous flat `MonitoringConfig` read `log_level` while the
shipped YAML nested it under `logging:`, and pydantic's default of "INFO"
matched the file, so the mismatch stayed invisible.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Language(StrEnum):
    ENGLISH = "en"
    BANGLA = "bn"


class StrictModel(BaseModel):
    """Base for every settings model: unknown keys are errors, not drops."""

    model_config = ConfigDict(extra="forbid")


class AppInfoConfig(StrictModel):
    name: str = "Sefa Receptionist"
    version: str = "0.1.0"
    environment: str = "development"
    debug: bool = True


class STTConfig(StrictModel):
    provider: str = "openai"
    model: str = "whisper-1"
    language: str = "auto"
    temperature: float = 0.0
    enable_vad: bool = True
    streaming: bool = True


class TTSConfig(StrictModel):
    provider: str = "elevenlabs"
    model: str = "eleven_multilingual_v2"
    voice_id: str = "pNInz6obpgDQGcFmaJgB"
    stability: float = 0.5
    similarity_boost: float = 0.75
    speed: float = 1.0
    sample_rate: int = 24000


class LLMConfig(StrictModel):
    provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.3
    max_tokens: int = 512
    system_prompt_file: str = "configs/prompts/system.md"


class LanguageDetectionConfig(StrictModel):
    provider: str = "simple"
    confidence_threshold: float = 0.6


class PipelineConfig(StrictModel):
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    language_detection: LanguageDetectionConfig = Field(
        default_factory=LanguageDetectionConfig
    )


class LanguagesConfig(StrictModel):
    primary: str = "en"
    supported: list[str] = Field(default_factory=lambda: ["en", "bn"])
    code_switching: bool = True
    default_greeting: dict[str, str] = Field(default_factory=dict)


class TwilioConfig(StrictModel):
    account_sid: str = ""
    auth_token: str = ""
    phone_number: str = ""
    voice: str = "Polly.Matthew"
    max_call_duration: int = 1800


class WebSocketConfig(StrictModel):
    host: str = "0.0.0.0"
    port: int = 8765


class TelephonyConfig(StrictModel):
    provider: str = "twilio"
    twilio: TwilioConfig = Field(default_factory=TwilioConfig)
    websocket: WebSocketConfig = Field(default_factory=WebSocketConfig)


class SessionConfig(StrictModel):
    backend: str = "redis"
    ttl_seconds: int = 3600
    max_history_turns: int = 50


class EscalationConfig(StrictModel):
    confidence_threshold: float = 0.7
    max_transfer_attempts: int = 3
    emergency_keywords: dict[str, list[str]] = Field(default_factory=dict)
    transfer_greeting: dict[str, str] = Field(default_factory=dict)


class ComplianceConfig(StrictModel):
    hipaa_enabled: bool = True
    encryption_algorithm: str = "AES-256-GCM"
    audit_log_enabled: bool = True
    call_recording_consent_required: bool = True
    data_retention_days: int = 2555
    phi_access_logging: bool = True
    max_session_ttl: int = 3600


class PrometheusConfig(StrictModel):
    enabled: bool = True
    port: int = 9090


class SentryConfig(StrictModel):
    enabled: bool = False
    dsn: str = ""


class LoggingConfig(StrictModel):
    level: str = "INFO"
    format: str = "json"
    phi_masking: bool = True


class MonitoringConfig(StrictModel):
    prometheus: PrometheusConfig = Field(default_factory=PrometheusConfig)
    sentry: SentryConfig = Field(default_factory=SentryConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


class OpenAIAdapterConfig(StrictModel):
    type: Literal["openai_stt", "openai_llm"]
    api_key: str = ""
    model: str = ""


class AnthropicAdapterConfig(StrictModel):
    type: Literal["anthropic_llm"]
    api_key: str = ""
    model: str = ""


class OpenAICompatibleAdapterConfig(StrictModel):
    type: Literal["openai_compatible_llm"]
    base_url: str = ""
    model: str = ""
    api_key: str = ""


class ElevenLabsSTTAdapterConfig(StrictModel):
    type: Literal["elevenlabs_stt"]
    api_key: str = ""


class ElevenLabsTTSAdapterConfig(StrictModel):
    type: Literal["elevenlabs_tts"]
    api_key: str = ""


class WhisperLocalAdapterConfig(StrictModel):
    type: Literal["whisper_local_stt"]
    model_size: str = "large-v3"
    device: str = "cuda"
    compute_type: str = "float16"
    bangla_finetuned: bool = True


class PiperAdapterConfig(StrictModel):
    type: Literal["piper_tts"]
    model_path: str = ""


class VITSAdapterConfig(StrictModel):
    type: Literal["vits_tts"]
    model_path: str = ""
AdapterConfig = Annotated[
    OpenAIAdapterConfig
    | AnthropicAdapterConfig
    | OpenAICompatibleAdapterConfig
    | ElevenLabsSTTAdapterConfig
    | ElevenLabsTTSAdapterConfig
    | WhisperLocalAdapterConfig
    | PiperAdapterConfig
    | VITSAdapterConfig,
    Field(discriminator="type"),
]

class RoutingConfig(StrictModel):
    strategy: str = "config"
    fallback_provider: str = "openai"


class ModelsConfig(StrictModel):
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    adapters: dict[str, AdapterConfig] = Field(default_factory=dict)


class GoogleCalendarConfig(StrictModel):
    credentials_path: str = ""
    calendar_id: str = "primary"


class CalendarConfig(StrictModel):
    provider: str = "google"
    google: GoogleCalendarConfig = Field(default_factory=GoogleCalendarConfig)


class CustomEHRConfig(StrictModel):
    base_url: str = ""
    api_key: str = ""


class EHRConfig(StrictModel):
    provider: str = "custom"
    custom: CustomEHRConfig = Field(default_factory=CustomEHRConfig)


class SMSChannelConfig(StrictModel):
    provider: str = "twilio"


class EmailChannelConfig(StrictModel):
    provider: str = "smtp"
    smtp_host: str = ""
    smtp_port: int = 587
    from_address: str = ""


class NotificationsConfig(StrictModel):
    sms: SMSChannelConfig = Field(default_factory=SMSChannelConfig)
    email: EmailChannelConfig = Field(default_factory=EmailChannelConfig)


class IntegrationsConfig(StrictModel):
    calendar: CalendarConfig = Field(default_factory=CalendarConfig)
    ehr: EHRConfig = Field(default_factory=EHRConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)


class AppConfig(StrictModel):
    """Root configuration loaded from YAML."""

    app: AppInfoConfig = Field(default_factory=AppInfoConfig)
    languages: LanguagesConfig = Field(default_factory=LanguagesConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    telephony: TelephonyConfig = Field(default_factory=TelephonyConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    escalation: EscalationConfig = Field(default_factory=EscalationConfig)
    compliance: ComplianceConfig = Field(default_factory=ComplianceConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    models: ModelsConfig = Field(default_factory=ModelsConfig)
    integrations: IntegrationsConfig = Field(default_factory=IntegrationsConfig)


def _resolve_env_vars(obj: Any) -> Any:
    """Recursively resolve ${ENV_VAR} references in config values."""
    if isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
        import os

        var_name = obj[2:-1]
        return os.environ.get(var_name, obj)
    elif isinstance(obj, dict):
        return {k: _resolve_env_vars(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_resolve_env_vars(i) for i in obj]
    return obj


def load_config(config_path: str | Path = "configs/default.yaml") -> AppConfig:
    """Load configuration from YAML file with env var resolution."""
    path = Path(config_path)
    if path.exists():
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        resolved = _resolve_env_vars(raw)
        return AppConfig(**resolved)
    return AppConfig()


settings = load_config()
