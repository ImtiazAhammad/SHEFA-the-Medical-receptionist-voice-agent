"""Guards for the web pages that the Python tests cannot drive: the static-shell rules, CORS, and the
reviewer page's mode logic (run in Node when it is installed)."""
# ruff: noqa: E501

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shefa.collector.api import create_public_app
from shefa.collector.config import CollectorConfig

STATIC = Path(__file__).resolve().parents[2] / "src" / "shefa" / "collector" / "static"


def test_the_public_page_never_hard_codes_the_server_address():
    """On a static host a path such as "/q/..." would point at the static host, not at the API."""
    bad = []
    for path in (STATIC / "public").rglob("*.js"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"""(fetch|Audio)\(\s*["'`]/""", line) or re.search(
                r"""\bsrc:\s*["']/""", line
            ):
                bad.append(f"{path.name}:{number}: {line.strip()[:80]}")
    assert not bad, "bypasses window.SHEFA_API: " + "; ".join(bad)


def test_the_pages_carry_no_inline_script_and_no_external_assets():
    for path in list((STATIC / "public").glob("*.html")) + list(
        (STATIC / "private").glob("*.html")
    ):
        html = path.read_text(encoding="utf-8")
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", html), (
            f"inline script in {path.name}"
        )
        assert not re.search(r"""(src|href)=["']https?://""", html), (
            f"external asset in {path.name}"
        )
        assert "http-equiv" not in html.lower(), f"meta CSP in {path.name} would block the shell"


def test_only_a_listed_origin_may_call_the_api_from_a_static_page(config, ctx):
    on = CollectorConfig(
        **{**config.model_dump(), "allowed_origins": ["https://shefa.example.pages.dev"]}
    )
    app = TestClient(create_public_app(on, ctx))
    ask = {
        "access-control-request-method": "PUT",
        "access-control-request-headers": "x-cid,x-secret",
    }
    good = app.options(
        "/api/c/clip/" + "a" * 32, headers={"origin": "https://shefa.example.pages.dev", **ask}
    )
    assert good.headers.get("access-control-allow-origin") == "https://shefa.example.pages.dev"
    other = app.options(
        "/api/c/clip/" + "a" * 32, headers={"origin": "https://evil.example", **ask}
    )
    assert "access-control-allow-origin" not in other.headers


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_verify_mode_puts_the_expected_words_in_an_editable_box():
    """One tap must not store a bare name or number as the whole transcript."""
    module = (STATIC / "private" / "js" / "review-model.js").as_uri()
    script = (
        f"import {{ viewFor }} from '{module}';"
        "const out = {"
        " verify: viewFor({mode:'verify', expected:'01712345678'}),"
        " blind: viewFor({mode:'blind', draft:'secret draft'}),"
        " seed: viewFor({mode:'seed', draft:'secret draft'}),"
        " adjudicate: viewFor({mode:'adjudicate', draft:'secret draft', candidates:[{text:'a',flags:[]}]}),"
        " draft: viewFor({mode:'draft', draft:'machine text'}) };"
        "console.log(JSON.stringify(out));"
    )
    run = subprocess.run(
        ["node", "--input-type=module", "-e", script], capture_output=True, text=True, check=True
    )
    views = json.loads(run.stdout)
    assert views["verify"]["ui"] == "type" and views["verify"]["prefill"] == "01712345678"
    assert views["verify"]["verifyNote"] is True
    assert (
        views["blind"] == views["seed"]
    )  # a reviewer must not be able to tell a seed from a real clip
    # every clip shows its draft now (founder's decision 2026-11-16); an adjudicator does not
    assert views["blind"]["prefill"] == "secret draft" and views["adjudicate"]["prefill"] == ""
    assert views["draft"]["prefill"] == "machine text"
