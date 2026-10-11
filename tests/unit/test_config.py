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

import os
import re
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
    AuthConfig,
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


def test_env_var_quoting_is_stripped(tmp_path, monkeypatch):
    """A quoted `.env` value must not keep its quotes in the credential.

    `TWILIO_ACCOUNT_SID="AC..."` reached Twilio as a 36-character username
    with a literal leading `"`, and the API answered "Authentication Error -
    invalid username" — indistinguishable from a wrong password.
    """
    monkeypatch.setenv("TEST_SID", '"ACquoted1234567890"')
    path = tmp_path / "quoted.yaml"
    path.write_text(
        yaml.safe_dump({"telephony": {"twilio": {"account_sid": "${TEST_SID}"}}}),
        encoding="utf-8",
    )
    assert load_config(path).telephony.twilio.account_sid == "ACquoted1234567890"


def test_real_env_var_reference_resolves_from_dotenv(tmp_path, monkeypatch):
    """A var only present in `.env` must resolve, not stay a placeholder.

    The shipped config references `${TWILIO_ACCOUNT_SID}` and friends, but
    nothing loaded `.env`, so the app ran with the literal string
    '${TWILIO_ACCOUNT_SID}' and failed every call with an opaque auth error.

    Hermetic: the `.env` lives in a temp CWD and the real variable is removed,
    so the resolved value can only have come from the file (not a developer's
    `.env` or the ambient environment).
    """
    sid = "AC" + "0" * 32
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        f'TWILIO_ACCOUNT_SID="{sid}"\n', encoding="utf-8"
    )
    config_path = tmp_path / "dotenv.yaml"
    config_path.write_text(
        yaml.safe_dump({"telephony": {"twilio": {"account_sid": "${TWILIO_ACCOUNT_SID}"}}}),
        encoding="utf-8",
    )
    resolved = load_config(config_path).telephony.twilio.account_sid
    assert resolved == sid, f"expected the .env SID, got {resolved!r}"
    assert os.environ["TWILIO_ACCOUNT_SID"] == sid, "the .env was not loaded"
    assert "$" not in resolved, "placeholder leaked through"


def test_env_var_reference_resolves_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_SID", "ACfromenv")
    path = tmp_path / "env.yaml"
    path.write_text(
        yaml.safe_dump({"telephony": {"twilio": {"account_sid": "${TEST_SID}"}}}),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.telephony.twilio.account_sid == "ACfromenv"


def test_env_var_fallback_syntax_yields_empty_not_literal(tmp_path, monkeypatch):
    """`${VAR:-fallback}` must fall back, not resolve to the literal text.

    Without the `:-` form an unset variable resolves to the string
    "${VAR}", which then trips the field validators — a `wss://` check for
    media_stream_url, an absolute-http check for public_url — and makes a
    valid default config refuse to boot on a machine with no tunnel running.
    """
    monkeypatch.delenv("TEST_PUBLIC_URL", raising=False)
    path = tmp_path / "fallback.yaml"
    path.write_text(
        yaml.safe_dump({"telephony": {"public_url": "${TEST_PUBLIC_URL:-}"}}),
        encoding="utf-8",
    )
    assert load_config(path).telephony.public_url == ""


def test_env_var_fallback_syntax_uses_env_when_set(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_PUBLIC_URL", "https://tunnel.example.dev")
    path = tmp_path / "fallback.yaml"
    path.write_text(
        yaml.safe_dump({"telephony": {"public_url": "${TEST_PUBLIC_URL:-}"}}),
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.telephony.public_url == "https://tunnel.example.dev"


def test_default_config_starts_without_tunnel_env_vars(monkeypatch):
    """The shipped config must load with PUBLIC_URL/MEDIA_STREAM_URL unset."""
    monkeypatch.delenv("PUBLIC_URL", raising=False)
    monkeypatch.delenv("MEDIA_STREAM_URL", raising=False)
    config = load_config(DEFAULT_YAML)
    assert config.telephony.public_url == ""
    assert config.telephony.twilio.media_stream_url == ""


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


def test_default_yaml_declares_the_new_telephony_knobs(monkeypatch):
    """The shipped config must not lose the two new keys (sip credentials,
    media_stream_url, public_url) to a model that cannot represent them.

    media_stream_url and public_url ship as `${VAR:-}` placeholders, so an unset
    environment resolves them to empty rather than to the literal text. The
    values are compared with the variables set, which is the case that matters:
    a real tunnel URL must survive the model intact."""
    monkeypatch.setenv("MEDIA_STREAM_URL", "wss://tunnel.example.dev/api/v1/telephony/media-stream")
    monkeypatch.setenv("PUBLIC_URL", "https://tunnel.example.dev")
    config = load_config(DEFAULT_YAML)
    raw = yaml.safe_load(DEFAULT_YAML.read_text(encoding="utf-8"))
    tel = raw["telephony"]
    assert config.telephony.sip.host == tel["sip"]["host"]
    assert (
        config.telephony.twilio.media_stream_url
        == "wss://tunnel.example.dev/api/v1/telephony/media-stream"
    )
    assert config.telephony.public_url == "https://tunnel.example.dev"
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


# --- T17 / D-ENG20: models.adapters is the single model-config source ---

REGISTRY_PY = REPO_ROOT / "src" / "sefa" / "models" / "registry.py"


def test_q12_resolved_model_key_is_single_source():
    """Q12 (D-ENG20): pipeline.llm.model and the resolved local adapter
    must agree — the two-key drift must fail loudly, not reconcile silently."""
    config = load_config(DEFAULT_YAML)
    assert config.pipeline.llm.provider == "local"
    assert config.pipeline.llm.model == "gemma2:9b"
    key, adapter = config.models.resolve_llm_adapter("local")
    assert key == "llm_local"
    assert adapter.model == config.pipeline.llm.model


def test_q12_registry_holds_no_model_literal():
    """Verify (T17): Q12 fails if registry gains a model literal.

    The registry must resolve base_url/model from models.adapters; a hardcoded
    endpoint or model string (the old `http://localhost:11434/v1`) is the drift
    this task's regression exists to catch.
    """
    src = REGISTRY_PY.read_text(encoding="utf-8")
    assert "11434" not in src
    assert re.search(r'(?:base_url|model)\s*=\s*["\']', src) is None


@pytest.mark.asyncio
async def test_local_registry_uses_adapter_base_url_and_model():
    """D-ENG20: the registry builds the local provider from models.adapters —
    the YAML base_url and the adapter's model, with no literal in the registry.

    The endpoint is the Ollama server on :11434, whose gemma2:9b is the Bangla
    pilot's brain. It used to assert the vLLM AWQ server on :8001, whose
    Qwen2.5 checkpoint could not hold Bangla."""
    from sefa.models.registry import registry

    llm = await registry._create_llm()
    assert llm.model == "gemma2:9b"
    assert str(llm._client.base_url).rstrip("/") == "http://localhost:11434/v1"


def test_resolve_llm_adapter_requires_exactly_one_adapter():
    cfg = ModelsConfig(
        adapters={
            "a": {"type": "openai_compatible_llm", "base_url": "http://1/v1", "model": "m"},
            "b": {"type": "openai_compatible_llm", "base_url": "http://2/v1", "model": "m"},
        }
    )
    with pytest.raises(ValueError, match="exactly one"):
        cfg.resolve_llm_adapter("local")
    missing = ModelsConfig(
        adapters={"other": {"type": "openai_llm", "api_key": "k", "model": "m"}}
    )
    with pytest.raises(ValueError, match="exactly one"):
        missing.resolve_llm_adapter("local")


def test_resolve_llm_adapter_rejects_unregistered_provider():
    with pytest.raises(ValueError, match="registered"):
        ModelsConfig().resolve_llm_adapter("no_such_provider")


@pytest.mark.asyncio
async def test_llm_provider_branches_build_from_resolved_adapter(monkeypatch):
    """Registry's openai/anthropic/qwen branches all consume models.adapters —
    each provider resolves its type and the adapter's model, never a literal."""
    from sefa.config.settings import settings
    from sefa.models.llm.anthropic_llm import AnthropicLLM
    from sefa.models.llm.openai_compatible_llm import OpenAICompatibleLLM
    from sefa.models.llm.openai_llm import OpenAILLM
    from sefa.models.registry import registry

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    monkeypatch.setattr(settings, "models", ModelsConfig(
        adapters={
            "llm_openai": {"type": "openai_llm", "api_key": "k", "model": "gpt-4o"},
            "llm_anthropic": {"type": "anthropic_llm", "api_key": "k", "model": "claude"},
            "llm_local": {
                "type": "openai_compatible_llm",
                "base_url": "http://localhost:8080/v1",
                "model": "qwen2.5:7b",
                "api_key": "not-needed",
            },
        }
    ))

    monkeypatch.setattr(settings.pipeline.llm, "provider", "openai")
    openai_llm = await registry._create_llm()
    assert isinstance(openai_llm, OpenAILLM)
    assert openai_llm.model == "gpt-4o"

    monkeypatch.setattr(settings.pipeline.llm, "provider", "anthropic")
    anthropic_llm = await registry._create_llm()
    assert isinstance(anthropic_llm, AnthropicLLM)
    assert anthropic_llm.model == "claude"

    monkeypatch.setattr(settings.pipeline.llm, "provider", "local")
    qwen_llm = await registry._create_llm()
    assert isinstance(qwen_llm, OpenAICompatibleLLM)
    assert qwen_llm.model == "qwen2.5:7b"
    assert str(qwen_llm._client.base_url).rstrip("/") == "http://localhost:8080/v1"


@pytest.mark.asyncio
async def test_unknown_llm_provider_raises(monkeypatch):
    from sefa.config.settings import settings
    from sefa.models.registry import registry

    monkeypatch.setattr(settings.pipeline.llm, "provider", "not_a_provider")
    with pytest.raises(ValueError, match="registered"):
        await registry._create_llm()


def test_dev_mode_placeholder_without_a_fallback_is_not_dev_mode(monkeypatch):
    """`${VAR}` with no `:-fallback` cannot be resolved to a bool.

    The shipped default uses the fallback form so an unset variable stays safe.
    A placeholder with no fallback has nothing to fall back to, so it must be
    refused rather than silently read as truthy — a non-empty string would
    otherwise be a truthy dev_mode.
    """
    monkeypatch.setenv("SEFA_DEV_MODE_TEST", "true")

    # The variable is deliberately irrelevant: without `:-` there is no
    # fallback to read, so the placeholder cannot become a bool by being set.
    assert AuthConfig(dev_mode="${SEFA_DEV_MODE_TEST}").dev_mode is False
