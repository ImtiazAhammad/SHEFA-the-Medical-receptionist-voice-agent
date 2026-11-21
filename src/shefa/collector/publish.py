"""Put the contributor page on the internet, or take it off, from the admin page.

The public link is Tailscale Funnel (`https://<machine>.<tailnet>.ts.net`). Publishing points it at
the PUBLIC port only; the staff port is never published, and a link found pointing anywhere else
is reported so it can be switched off. tailscaled keeps the setting across reboots, so an
unpublished link stays unpublished until someone publishes it again.

Needs `sudo tailscale set --operator=$USER` once, so this user may change Funnel without sudo.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from typing import Any

Runner = Callable[[list[str]], tuple[int, str]]
TIMEOUT_S = 25


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        done = subprocess.run(  # noqa: S603 (fixed arguments, no shell)
            cmd, capture_output=True, text=True, timeout=TIMEOUT_S, stdin=subprocess.DEVNULL
        )
    except subprocess.TimeoutExpired:
        return 124, "tailscale did not answer in time"
    except OSError as e:
        return 127, str(e)
    return done.returncode, (done.stdout or "") + (done.stderr or "")


class Publisher:
    def __init__(self, public_port: int, runner: Runner | None = None, binary: str | None = None):
        self.port = public_port
        self.binary = (shutil.which("tailscale") or "") if binary is None else binary
        self.run = runner or _run

    def status(self) -> dict[str, Any]:
        """{available, published, url, target, wrong_target, error}"""
        out: dict[str, Any] = {
            "available": bool(self.binary),
            "published": False,
            "url": "",
            "target": "",
            "wrong_target": False,
            "error": "",
        }
        if not self.binary:
            out["error"] = "tailscale is not installed"
            return out
        code, text = self.run([self.binary, "funnel", "status", "--json"])
        if code != 0:
            out["error"] = _short(text)
            return out
        try:
            data = json.loads(text) if text.strip() else {}
        except ValueError:
            out["error"] = "could not read tailscale's answer"
            return out
        allowed = {k for k, v in (data.get("AllowFunnel") or {}).items() if v}
        for hostport, web in (data.get("Web") or {}).items():
            if hostport not in allowed:
                continue
            host = hostport.rsplit(":", 1)[0]
            target = ((web.get("Handlers") or {}).get("/") or {}).get("Proxy", "")
            out.update(published=True, url=f"https://{host}", target=target)
            out["wrong_target"] = not _is_port(target, self.port)
            break
        return out

    def set(self, on: bool) -> dict[str, Any]:
        """Publish (on) or unpublish (off); returns the status afterwards, with any error."""
        if not self.binary:
            return self.status()
        if on:
            cmd = [self.binary, "funnel", "--bg", str(self.port)]
        else:
            cmd = [self.binary, "funnel", "--https=443", "off"]
        code, text = self.run(cmd)
        after = self.status()
        if code != 0 and not after["error"]:
            after["error"] = _explain(text)
        return after


def _is_port(target: str, port: int) -> bool:
    t = target.rstrip("/")
    return t in (f"http://127.0.0.1:{port}", f"http://localhost:{port}")


def _short(text: str) -> str:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return (lines[0] if lines else "tailscale failed")[:200]


def _explain(text: str) -> str:
    if "Access denied" in text:
        return "this user may not change Funnel: run `sudo tailscale set --operator=$USER` once"
    if "not enabled on your tailnet" in text:
        return "Funnel is not enabled on the tailnet: open the link `tailscale funnel 8100` prints"
    return _short(text)
