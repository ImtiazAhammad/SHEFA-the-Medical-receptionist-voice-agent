"""Render the Asterisk config files from templates plus environment credentials."""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

from shefa.config.settings import settings

if TYPE_CHECKING:
    from collections.abc import Mapping

REQUIRED = ("ARI_PASSWORD",)
TRUNK = ("SIP_TRUNK_HOST", "SIP_TRUNK_USER", "SIP_TRUNK_PASSWORD")
TEMPLATES = ("pjsip.conf", "extensions.conf", "ari.conf", "http.conf", "modules.conf")
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


# Extension 1001: register a softphone with this username and password to call the agent
# (dial 1000) and to be called by it. Optional: only rendered when SOFTPHONE_PASSWORD is set.
_SOFTPHONE = """[1001]
type=aor
max_contacts=2

[1001]
type=auth
auth_type=userpass
username=1001
password={{SOFTPHONE_PASSWORD}}

[1001]
type=endpoint
transport=transport-udp
context=shefa-local
disallow=all
allow=alaw
allow=ulaw
auth=1001
aors=1001
direct_media=no
rtp_symmetric=yes
force_rport=yes
rewrite_contact=yes
"""


def template_dir() -> Path:
    """`deploy/asterisk` in a source checkout (the kit is not part of the wheel)."""
    return Path(str(resources.files("shefa"))).parents[1] / "deploy" / "asterisk"


def render_asterisk_config(
    env: Mapping[str, str], templates: Path | None = None
) -> dict[str, str]:
    """Map output file name -> text. Raises ValueError naming every missing variable."""
    # The carrier trunk is optional: with no SIP_TRUNK_HOST you get a softphone-only setup.
    trunk = bool(env.get("SIP_TRUNK_HOST"))
    needed = (*REQUIRED, *TRUNK) if trunk else REQUIRED
    missing = [name for name in needed if not env.get(name)]
    if missing:
        raise ValueError("Missing environment variables: " + ", ".join(missing))
    cfg = settings.telephony.asterisk
    public_ip = env.get("PUBLIC_IP", "")
    values = {
        **{name: env[name] for name in needed},
        "SIP_TRUNK_PORT": env.get("SIP_TRUNK_PORT") or "5060",
        "ARI_USER": cfg.ari_user,
        "AUDIOSOCKET_ADDRESS": f"{cfg.audiosocket_host}:{cfg.audiosocket_port}",
        "EXTERNAL_ADDRESS": (
            f"external_media_address={public_ip}\nexternal_signaling_address={public_ip}"
            if public_ip
            else ""
        ),
    }
    softphone = env.get("SOFTPHONE_PASSWORD", "")
    values["SOFTPHONE_BLOCK"] = (
        _SOFTPHONE.replace("{{SOFTPHONE_PASSWORD}}", softphone) if softphone else ""
    )
    source = templates or template_dir()
    rendered: dict[str, str] = {}
    for name in TEMPLATES:
        path = source / f"{name}.tmpl"
        if not path.exists():
            path = source / name
        text = path.read_text(encoding="utf-8")
        if not trunk:
            text = re.sub(r"; --- trunk ---.*?; --- end trunk ---\n", "", text, flags=re.DOTALL)
        rendered[name] = _PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)
    return rendered
