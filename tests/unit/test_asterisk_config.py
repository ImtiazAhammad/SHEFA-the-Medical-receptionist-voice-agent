from __future__ import annotations

import pytest

from shefa.cli import main
from shefa.telephony.asterisk_config import render_asterisk_config

ENV = {
    "SIP_TRUNK_HOST": "sip.carrier.example",
    "SIP_TRUNK_USER": "clinic01",
    "SIP_TRUNK_PASSWORD": "s3cret-pass",
    "ARI_PASSWORD": "ari-pass",
}


def test_renders_trunk_audiosocket_and_ari():
    files = render_asterisk_config(ENV)
    assert "server_uri=sip:sip.carrier.example:5060" in files["pjsip.conf"]
    assert "username=clinic01" in files["pjsip.conf"]
    assert "AudioSocket(${SHEFA_UUID},127.0.0.1:4573)" in files["extensions.conf"]
    assert "SHEFA_CALLER=${CALLERID(num)}" in files["extensions.conf"]
    assert "password=ari-pass" in files["ari.conf"]
    assert "bindaddr=127.0.0.1" in files["http.conf"]
    assert "{{" not in "".join(files.values())  # every placeholder was filled


def test_public_ip_sets_the_nat_addresses_and_port_can_change():
    files = render_asterisk_config({**ENV, "PUBLIC_IP": "203.0.113.9", "SIP_TRUNK_PORT": "5080"})
    assert "external_media_address=203.0.113.9" in files["pjsip.conf"]
    assert "sip.carrier.example:5080" in files["pjsip.conf"]
    assert "external_media_address" not in render_asterisk_config(ENV)["pjsip.conf"]


def test_missing_variables_are_all_named():
    with pytest.raises(ValueError) as error:
        render_asterisk_config({"SIP_TRUNK_HOST": "h"})
    assert "SIP_TRUNK_USER" in str(error.value)
    assert "ARI_PASSWORD" in str(error.value)


def test_without_a_trunk_only_the_ari_password_is_needed_and_no_trunk_is_rendered():
    files = render_asterisk_config({"ARI_PASSWORD": "a", "SOFTPHONE_PASSWORD": "p"})
    assert "[trunk" not in files["pjsip.conf"] and "registration" not in files["pjsip.conf"]
    assert "[1001]" in files["pjsip.conf"] and "{{" not in files["pjsip.conf"]
    with pytest.raises(ValueError, match="ARI_PASSWORD"):
        render_asterisk_config({})


def test_cli_writes_the_files_privately(tmp_path, monkeypatch, capsys):
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    out = tmp_path / "rendered"
    assert main(["asterisk", "render", "--out", str(out)]) == 0
    assert (out / "pjsip.conf").read_text().count("clinic01") >= 2
    assert (out.stat().st_mode & 0o777) == 0o700
    assert "keep it private" in capsys.readouterr().out


def test_cli_reports_missing_credentials(tmp_path, monkeypatch, capsys):
    for key in ENV:
        monkeypatch.delenv(key, raising=False)
    assert main(["asterisk", "render", "--out", str(tmp_path / "x")]) == 1
    assert "ARI_PASSWORD" in capsys.readouterr().err


def test_cli_requires_a_subcommand(capsys):
    assert main(["asterisk"]) == 2


def test_the_kit_in_the_repo_never_contains_a_password():
    from shefa.telephony.asterisk_config import template_dir

    for path in template_dir().iterdir():
        if path.suffix in {".tmpl", ".conf", ".yml"}:
            assert "s3cret" not in path.read_text()


def test_softphone_extension_is_rendered_only_when_a_password_is_given():
    plain = render_asterisk_config(ENV)
    assert "[1001]" not in plain["pjsip.conf"] and "{{" not in plain["pjsip.conf"]
    phone = render_asterisk_config({**ENV, "SOFTPHONE_PASSWORD": "phone-pass"})
    assert "username=1001" in phone["pjsip.conf"] and "password=phone-pass" in phone["pjsip.conf"]
    assert "exten => 1000,1" in phone["extensions.conf"]
