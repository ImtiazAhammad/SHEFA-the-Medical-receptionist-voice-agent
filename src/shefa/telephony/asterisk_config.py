"""Render the Asterisk config files from templates plus environment credentials."""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

from shefa.config.settings import settings

if TYPE_CHECKING:
    from collections.abc import Mapping

REQUIRED = ("SIP_TRUNK_HOST", "SIP_TRUNK_USER", "SIP_TRUNK_PASSWORD", "ARI_PASSWORD")
TEMPLATES = ("pjsip.conf", "extensions.conf", "ari.conf", "http.conf", "modules.conf")
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def template_dir() -> Path:
    """`deploy/asterisk` in a source checkout (the kit is not part of the wheel)."""
    return Path(str(resources.files("shefa"))).parents[1] / "deploy" / "asterisk"


def render_asterisk_config(
    env: Mapping[str, str], templates: Path | None = None
) -> dict[str, str]:
    """Map output file name -> text. Raises ValueError naming every missing variable."""
    missing = [name for name in REQUIRED if not env.get(name)]
    if missing:
        raise ValueError("Missing environment variables: " + ", ".join(missing))
    cfg = settings.telephony.asterisk
    public_ip = env.get("PUBLIC_IP", "")
    values = {
        **{name: env[name] for name in REQUIRED},
        "SIP_TRUNK_PORT": env.get("SIP_TRUNK_PORT") or "5060",
        "ARI_USER": cfg.ari_user,
        "AUDIOSOCKET_ADDRESS": f"{cfg.audiosocket_host}:{cfg.audiosocket_port}",
        "EXTERNAL_ADDRESS": (
            f"external_media_address={public_ip}\nexternal_signaling_address={public_ip}"
            if public_ip
            else ""
        ),
    }
    source = templates or template_dir()
    rendered: dict[str, str] = {}
    for name in TEMPLATES:
        path = source / f"{name}.tmpl"
        if not path.exists():
            path = source / name
        text = path.read_text(encoding="utf-8")
        rendered[name] = _PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), text)
    return rendered
