"""The admin switch that puts the public link on the internet or takes it off (Tailscale Funnel),
with a fake tailscale so nothing real changes."""
# ruff: noqa: F811

import json

from shefa.collector.publish import Publisher
from tests.collector.test_review import bearer, staff  # noqa: F401 (staff is a fixture)

HOST = "shefa-voice.example.ts.net"


class FakeTailscale:
    def __init__(self, target="http://127.0.0.1:8100", on=True, deny=False):
        self.target, self.on, self.deny, self.calls = target, on, deny, []

    def __call__(self, cmd):
        self.calls.append(cmd[1:])
        if cmd[1:3] == ["funnel", "status"]:
            if not self.on:
                return 0, "{}"
            return 0, json.dumps(
                {
                    "Web": {f"{HOST}:443": {"Handlers": {"/": {"Proxy": self.target}}}},
                    "AllowFunnel": {f"{HOST}:443": True},
                }
            )
        if self.deny:
            return 1, "sending serve config: Access denied: serve config denied"
        if cmd[-1] == "off":
            self.on = False
        else:
            self.on, self.target = True, f"http://127.0.0.1:{cmd[-1]}"
        return 0, ""


def test_status_reads_the_link():
    p = Publisher(8100, runner=FakeTailscale(), binary="tailscale")
    got = p.status()
    assert got["published"] and got["url"] == f"https://{HOST}" and not got["wrong_target"]


def test_publishing_only_ever_points_at_the_public_port():
    fake = FakeTailscale(on=False)
    p = Publisher(8100, runner=fake, binary="tailscale")
    assert p.set(True)["published"]
    assert ["funnel", "--bg", "8100"] in fake.calls
    assert not any("8101" in " ".join(c) for c in fake.calls)


def test_a_link_pointing_at_the_staff_page_is_flagged():
    p = Publisher(8100, runner=FakeTailscale(target="http://127.0.0.1:8101"), binary="tailscale")
    assert p.status()["wrong_target"]


def test_unpublish_turns_it_off():
    fake = FakeTailscale()
    after = Publisher(8100, runner=fake, binary="tailscale").set(False)
    assert not after["published"] and ["funnel", "--https=443", "off"] in fake.calls


def test_missing_rights_are_explained():
    after = Publisher(8100, runner=FakeTailscale(on=False, deny=True), binary="tailscale").set(True)
    assert not after["published"] and "operator" in after["error"]


def test_no_tailscale_says_so():
    got = Publisher(8100, runner=FakeTailscale(), binary="").status()
    assert not got["available"] and got["error"]


def test_admin_route_switches_and_audits(priv, ctx, staff):
    fake = FakeTailscale()
    ctx.publisher = Publisher(ctx.config.port, runner=fake, binary="tailscale")
    h = bearer(staff["admin"])
    assert priv.get("/api/admin/publish", headers=h).json()["published"]
    off = priv.post("/api/admin/publish", json={"published": False}, headers=h).json()
    assert off["published"] is False
    on = priv.post("/api/admin/publish", json={"published": True}, headers=h).json()
    assert on["published"] is True
    events = [r["action"] for r in ctx.store._q("SELECT action FROM audit")]
    assert events.count("publish") == 2


def test_only_admins_may_switch_the_link(priv, pub, ctx, staff):
    ctx.publisher = Publisher(ctx.config.port, runner=FakeTailscale(), binary="tailscale")
    assert priv.post("/api/admin/publish", json={"published": False}).status_code in (401, 403)
    if "reviewer" in staff:
        r = priv.post(
            "/api/admin/publish", json={"published": False}, headers=bearer(staff["reviewer"])
        )
        assert r.status_code in (401, 403)
    assert pub.get("/api/admin/publish").status_code == 404  # never on the public site
