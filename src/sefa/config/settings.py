"""Application settings loaded from YAML config and environment variables."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class Language(StrEnum):
    ENGLISH = "en"
    BANGLA = "bn"


class STTConfig(BaseModel):
    provider: str = "openai"
    model: str = "whisper-1"
    language: str = "auto"
    temperature: float = 0.0
    enable_vad: bool = True
    streaming: bool = True


class TTSConfig(BaseModel):
    provider: str = "elevenlabs"
    model: str = "eleven_multilingual_v2"
    voice_id: str = "pNInz6obpgDQGcFmaJgB"
    stability: float = 0.5
    similarity_boost: float = 0.75
    speed: float = 1.0
    sample_rate: int = 24000


class LLMConfig(BaseModel):
    provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.3
    max_tokens: int = 512
    system_prompt_file: str = "configs/prompts/system.md"


class LanguageDetectionConfig(BaseModel):
    provider: str = "simple"
    confidence_threshold: float = 0.6


class PipelineConfig(BaseModel):
    stt: STTConfig = Field(default_factory=STTConfig)
    tts: TTSConfig = Field(default_factory=TTSConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    language_detection: LanguageDetectionConfig = Field(
        default_factory=LanguageDetectionConfig
    )


class LanguagesConfig(BaseModel):
    primary: str = "en"
    supported: list[str] = Field(default_factory=lambda: ["en", "bn"])
    code_switching: bool = True
    default_greeting: dict[str, str] = Field(default_factory=dict)


class TwilioConfig(BaseModel):
    account_sid: str = ""
    auth_token: str = ""
    phone_number: str = ""
    voice: str = "Polly.Matthew"
    max_call_duration: int = 1800


class TelephonyConfig(BaseModel):
    provider: str = "twilio"
    twilio: TwilioConfig = Field(default_factory=TwilioConfig)


class SessionConfig(BaseModel):
    backend: str = "redis"
    ttl_seconds: int = 3600
    max_history_turns: int = 50


class EscalationConfig(BaseModel):
    confidence_threshold: float = 0.7
    max_transfer_attempts: int = 3
    emergency_keywords: dict[str, list[str]] = Field(default_factory=dict)
    transfer_greeting: dict[str, str] = Field(default_factory=dict)


class ComplianceConfig(BaseModel):
    hipaa_enabled: bool = True
    encryption_algorithm: str = "AES-256-GCM"
    audit_log_enabled: bool = True
    call_recording_consent_required: bool = True
    data_retention_days: int = 2555
    phi_access_logging: bool = True
    max_session_ttl: int = 3600


class MonitoringConfig(BaseModel):
    prometheus_enabled: bool = True
    sentry_enabled: bool = False
    log_level: str = "INFO"
    log_format: str = "json"
    phi_masking: bool = True


class AppConfig(BaseModel):
    """Root configuration loaded from YAML."""

    languages: LanguagesConfig = Field(default_factory=LanguagesConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    telephony: TelephonyConfig = Field(default_factory=TelephonyConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    escalation: EscalationConfig = Field(default_factory=EscalationConfig)
    compliance: ComplianceConfig = Field(default_factory=ComplianceConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)


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
