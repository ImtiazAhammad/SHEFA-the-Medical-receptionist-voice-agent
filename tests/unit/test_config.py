"""Tests for configuration loading.

T1 regression surface: `configs/default.yaml` declared sections that no
settings model claimed (`app`, `models`, `integrations`) and nested
`monitoring.logging.*` keys that the flat MonitoringConfig never read. Pydantic
silently ignored all of them, so the app booted on defaults that *looked* right
(`monitoring.log_level` defaulted to "INFO", the same string the YAML happened
to set). Every test here fails if config can drift from the declared surface
without a loud error.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml
from pydantic import BaseModel, ValidationError

from sefa.config.settings import (
    AnthropicAdapterConfig,
    AppConfig,
    AppInfoConfig,
    CalendarConfig,
    ComplianceConfig,
    CustomEHRConfig,
    EHRConfig,
    EmailChannelConfig,
    EscalationConfig,
    GoogleCalendarConfig,
    IntegrationsConfig,
    Language,
    LanguageDetectionConfig,
    LanguagesConfig,
    LLMConfig,
    LoggingConfig,
    ModelsConfig,
    MonitoringConfig,
    NotificationsConfig,
    OpenAIAdapterConfig,
    OpenAICompatibleAdapterConfig,
    PipelineConfig,
    PrometheusConfig,
    RoutingConfig,
    SentryConfig,
    SessionConfig,
    SipConfig,
    SMSChannelConfig,
    STTConfig,
    TelephonyConfig,
    TelephonyProvider,
    TTSConfig,
    TwilioConfig,
    WebSocketConfig,
    load_config,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_YAML = REPO_ROOT / "configs" / "default.yaml"


def test_default_config_loads():
    config = AppConfig()
    assert "en" in config.languages.supported
    assert "bn" in config.languages.supported
    assert config.pipeline.stt.provider == "openai"
    assert config.pipeline.tts.provider == "elevenlabs"
    assert config.pipeline.llm.provider == "openai"
    assert config.compliance.hipaa_enabled is True


def test_language_enum():
    assert Language.ENGLISH.value == "en"
    assert Language.BANGLA.value == "bn"


ALL_SUBMODELS = [
    AppInfoConfig(),
    LanguagesConfig(),
    STTConfig(),
    TTSConfig(),
    LLMConfig(),
    LanguageDetectionConfig(),
    PipelineConfig(),
    TelephonyConfig(),
    WebSocketConfig(),
    SessionConfig(),
    EscalationConfig(),
    ComplianceConfig(),
    PrometheusConfig(),
    SentryConfig(),
    LoggingConfig(),
    MonitoringConfig(),
    RoutingConfig(),
    ModelsConfig(),
    CalendarConfig(),
    GoogleCalendarConfig(),
    EHRConfig(),
    CustomEHRConfig(),
    SMSChannelConfig(),
    EmailChannelConfig(),
    NotificationsConfig(),
    IntegrationsConfig(),
    AppConfig(),
]

ADAPTER_PAYLOADS = [
    {"type": "openai_stt"},
    {"type": "openai_llm"},
    {"type": "anthropic_llm"},
    {"type": "openai_compatible_llm"},
    {"type": "elevenlabs_stt"},
    {"type": "elevenlabs_tts"},
    {"type": "whisper_local_stt"},
    {"type": "piper_tts"},
    {"type": "vits_tts"},
]


@pytest.mark.parametrize("model", ALL_SUBMODELS, ids=lambda m: type(m).__name__)
def test_every_submodel_forbids_unknown_keys(model):
    """A typo'd or stale config key must be an error, never a silent drop."""
    with pytest.raises(ValidationError):
        type(model).model_validate(
            {**model.model_dump(), "definitely_not_a_real_key": 1}
        )


@pytest.mark.parametrize("payload", ADAPTER_PAYLOADS, ids=lambda p: p["type"])
def test_every_adapter_model_forbids_unknown_keys(payload):
    with pytest.raises(ValidationError):
        ModelsConfig.model_validate(
            {"adapters": {"probe": {**payload, "not_a_real_field": 1}}}
        )


def test_adapter_models_carry_their_shipped_keys():
    assert OpenAIAdapterConfig.model_validate(
        {"type": "openai_llm", "api_key": "k", "model": "gpt-4o"}
    ).model == "gpt-4o"
    assert AnthropicAdapterConfig.model_validate(
        {"type": "anthropic_llm", "api_key": "k", "model": "claude"}
    ).model == "claude"
    assert OpenAICompatibleAdapterConfig.model_validate(
        {"type": "openai_compatible_llm", "base_url": "http://x/v1", "model": "q"}
    ).base_url == "http://x/v1"


def test_shipped_default_yaml_declares_no_dropped_section():
    """configs/default.yaml must not carry sections AppConfig cannot represent."""
    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    dropped = set(raw) - set(AppConfig.model_fields)
    assert not dropped, (
        f"configs/default.yaml declares sections no settings model claims: "
        f"{sorted(dropped)}. They are silently discarded on load. Add a model "
        f"or remove the section."
    )


def _nested_undeclared_keys(model, payload, path="") -> list[str]:
    """Walk a loaded model, reporting YAML keys that reached no model field."""
    undeclared = []
    for key, value in payload.items():
        if key not in type(model).model_fields:
            undeclared.append(f"{path}{key}")
            continue
        child = getattr(model, key)
        if isinstance(value, dict) and isinstance(child, BaseModel):
            undeclared += _nested_undeclared_keys(child, value, f"{path}{key}.")
    return undeclared


def test_no_nested_key_in_default_yaml_is_silently_discarded():
    """Whole-tree check: every YAML key must land in a declared model field."""
    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    config = AppConfig(**raw)
    undeclared = _nested_undeclared_keys(config, raw)
    assert not undeclared, (
        f"configs/default.yaml keys silently discarded: {sorted(undeclared)}"
    )


def test_monitoring_log_level_comes_from_yaml_not_the_model_default(tmp_path):
    """Regression: `monitoring.logging.level` must actually reach the config.

    The flat MonitoringConfig read `log_level` while the YAML nested it under
    `logging:`, so a DEBUG setting in the file was ignored and the process ran
    on the pydantic default.
    """
    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    raw["monitoring"]["logging"]["level"] = "DEBUG"
    path = tmp_path / "custom.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    config = load_config(path)
    assert config.monitoring.logging.level == "DEBUG"


def test_monitoring_log_level_is_not_an_alias_for_the_default():
    """The old flat key must be gone, so drift cannot keep working by luck."""
    with pytest.raises(ValidationError):
        MonitoringConfig.model_validate({"log_level": "DEBUG"})


def test_monitoring_phi_masking_is_configurable_per_plan_t8():
    config = MonitoringConfig.model_validate({"logging": {"phi_masking": False}})
    assert config.logging.phi_masking is False


def test_monitoring_nested_sections_are_typed():
    config = MonitoringConfig.model_validate(
        {
            "prometheus": {"enabled": True, "port": 9090},
            "sentry": {"enabled": False, "dsn": "https://x@y/1"},
            "logging": {"level": "WARNING", "format": "json"},
        }
    )
    assert config.prometheus.port == 9090
    assert config.sentry.enabled is False
    assert config.logging.format == "json"


def test_models_adapters_keep_every_shipped_adapter():
    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    config = AppConfig(**raw)
    shipped = set(raw["models"]["adapters"])
    assert set(config.models.adapters) == shipped


def test_telephony_websocket_section_is_retained():
    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    config = AppConfig(**raw)
    assert config.telephony.websocket.port == raw["telephony"]["websocket"]["port"]


def test_integrations_sections_are_retained():
    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    config = AppConfig(**raw)
    assert config.integrations.ehr.custom.base_url == raw["integrations"]["ehr"][
        "custom"
    ]["base_url"]
    assert config.integrations.calendar.google.calendar_id == "primary"
    assert config.integrations.notifications.email.smtp_port == 587


def test_app_section_is_retained():
    config = load_config(DEFAULT_YAML)
    assert config.app.name
    assert config.app.environment


def test_unknown_adapter_type_is_rejected():
    with pytest.raises(ValidationError):
        ModelsConfig.model_validate({"adapters": {"x": {"type": "not_a_type"}}})


def test_missing_config_path_falls_back_to_model_defaults():
    """No config file is not a boot failure — defaults are the contract."""
    config = load_config(REPO_ROOT / "configs" / "does_not_exist.yaml")
    assert config.pipeline.stt.provider == "openai"
    assert config.app.name


def test_env_var_reference_is_resolved(tmp_path):
    path = tmp_path / "env.yaml"
    path.write_text(
        yaml.safe_dump({"telephony": {"twilio": {"account_sid": "${TEST_SID}"}}}),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.telephony.twilio.account_sid == "${TEST_SID}"


def test_env_var_reference_resolves_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_SID", "ACfromenv")
    path = tmp_path / "env.yaml"
    path.write_text(
        yaml.safe_dump({"telephony": {"twilio": {"account_sid": "${TEST_SID}"}}}),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.telephony.twilio.account_sid == "ACfromenv"


def test_telephony_provider_is_a_single_enum_knob():
    """D-ENG13: provider selection is one knob, typed so a typo cannot load."""
    assert TelephonyProvider.TWILIO.value == "twilio"
    assert TelephonyProvider.ASTERISK.value == "asterisk"
    assert TelephonyProvider.FREESWITCH.value == "freeswitch"
    config = TelephonyConfig.model_validate({"provider": "twilio"})
    assert config.provider is TelephonyProvider.TWILIO


def test_telephony_provider_rejects_an_unknown_knob_value():
    """Flip the knob to a value that is not twilio|asterisk|freeswitch →
    a startup error, not a silently unbound router."""
    with pytest.raises(ValidationError):
        TelephonyConfig.model_validate({"provider": "twiliooo"})


def test_sip_carries_credentials_only_and_never_a_provider_key():
    sip = SipConfig.model_validate(
        {"host": "sip.example", "port": 5061, "username": "u", "password": "p"}
    )
    assert sip.port == 5061
    assert sip.password == "p"
    with pytest.raises(ValidationError):
        SipConfig.model_validate({"host": "sip.example", "provider": "asterisk"})


def test_two_provider_knobs_is_rejected_at_startup():
    """D-ENG13: `telephony.sip.provider` is the removed two-key state. A config
    carrying it must not boot quietly and lose calls."""
    with pytest.raises(ValidationError, match="sip.provider"):
        TelephonyConfig.model_validate(
            {
                "provider": "asterisk",
                "sip": {"host": "sip.example", "provider": "asterisk"},
            }
        )


def test_media_stream_url_must_be_wss():
    """Raw twilio websockets only accept wss:// — anything else is the wrong
    knob wired in and must error at startup, not mid-call."""
    with pytest.raises(ValidationError, match="wss://"):
        TwilioConfig.model_validate({"media_stream_url": "http://acme.twil.io/media-stream"})
    ok = TwilioConfig.model_validate({"media_stream_url": "wss://acme.twil.io/media-stream"})
    assert ok.media_stream_url == "wss://acme.twil.io/media-stream"


def test_media_stream_url_derives_from_account_sid_when_unset():
    config = TwilioConfig(account_sid="AC123")
    assert config.effective_media_stream_url == "wss://AC123.twil.io/media-stream"
    assert TwilioConfig().effective_media_stream_url == "wss://.twil.io/media-stream"


def test_twil_io_media_stream_rejected_when_provider_is_not_twilio():
    """Provider on the SIP knob while the media stream URL still resolves to
    *.twil.io → startup error (calls would ring nowhere), never silent."""
    with pytest.raises(ValidationError, match="twil.io"):
        TelephonyConfig.model_validate(
            {
                "provider": "asterisk",
                "twilio": {"media_stream_url": "wss://AC123.twil.io/media-stream"},
            }
        )
    with pytest.raises(ValidationError, match="twil.io"):
        TelephonyConfig(provider="freeswitch", twilio=TwilioConfig(account_sid="AC123"))
    ok = TelephonyConfig.model_validate(
        {
            "provider": "asterisk",
            "twilio": {"media_stream_url": "wss://media.example/ws"},
        }
    )
    assert ok.twilio.media_stream_url == "wss://media.example/ws"


def test_public_url_is_an_explicit_validated_config_key():
    """D-ENG25: no more localhost ngrok scraping — PUBLIC_URL is a config key,
    validated as an absolute http(s) URL when set."""
    assert TelephonyConfig().public_url == ""
    with pytest.raises(ValidationError):
        TelephonyConfig.model_validate({"public_url": "notaurl"})
    with pytest.raises(ValidationError):
        TelephonyConfig.model_validate({"public_url": "wss://x.example"})
    ok = TelephonyConfig.model_validate({"public_url": "https://tunnel.example"})
    assert ok.public_url == "https://tunnel.example"


def test_default_yaml_declares_the_new_telephony_knobs():
    """The shipped config must not lose the two new keys (sip credentials,
    media_stream_url, public_url) to a model that cannot represent them."""
    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    config = AppConfig(**raw)
    tel = raw["telephony"]
    assert config.telephony.sip.host == tel["sip"]["host"]
    assert config.telephony.twilio.media_stream_url == tel["twilio"]["media_stream_url"]
    assert config.telephony.public_url == tel["public_url"]
    assert "media_stream_url" in tel["twilio"]
    assert "public_url" in tel
    assert "sip" in tel


def test_default_yaml_telephony_section_has_no_provider_key_under_sip():
    """The shipped config must never reintroduce the two-key state."""
    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    assert "provider" not in raw["telephony"]["sip"]


def test_config_boots_from_a_fresh_interpreter():
    """`sefa doctor`'s precondition: a cold import must load real config.

    A fresh subprocess is the only honest way to prove module-import boot —
    an already-imported module would pass on whatever a prior test left in
    `sys.modules`.
    """
    script = textwrap.dedent(
        """
        import sefa
        from sefa.config.settings import settings
        assert settings.app.name, "config did not boot"
        print("BOOT_OK")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "BOOT_OK" in result.stdout


def test_every_module_imports_cleanly():
    """Fresh-interpreter import of every sefa module (module-import boot test)."""
    script = textwrap.dedent(
        """
        import importlib, pkgutil, sys
        import sefa
        failures = []
        for mod in pkgutil.walk_packages(sefa.__path__, "sefa."):
            try:
                importlib.import_module(mod.name)
            except Exception as exc:
                failures.append(f"{mod.name}: {type(exc).__name__}: {exc}")
        if failures:
            print("\\n".join(failures), file=sys.stderr)
            sys.exit(1)
        print("IMPORTS_OK")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 0, result.stderr
    assert "IMPORTS_OK" in result.stdout
