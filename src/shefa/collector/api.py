"""HTTP surface of the collection app.

Two apps share this module. The PUBLIC app is what the tunnel exposes: the contributor page, the
upload endpoint and a few aggregate numbers. The PRIVATE app (localhost only) adds the reviewer
and admin pages. `shefa collect serve --with-review` mounts the review routes on the public app
for a review session, never the admin ones.
"""
# ruff: noqa: E501, N812, TC001, TC003

from __future__ import annotations

import hashlib
import hmac
import os
import random
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from shefa.booking import RateLimiter
from shefa.collector import audio as A
from shefa.collector import prompts as P
from shefa.collector import scripts as S
from shefa.collector.config import (
    CONSENT_V1,
    CONSENT_V2_BN,
    CONSENT_V2_EN,
    SHARE_BN,
    SHARE_EN,
    CollectorConfig,
)
from shefa.collector.store import CLIP_ID, CollectorStore, StoreError

STATIC = Path(__file__).parent / "static"
SETTING_IDS = {s["id"] for s in P.settings_choices()}
AGE_BANDS = {"18-24", "25-34", "35-49", "50-64", "65+"}
GENDERS = {"female", "male", "other", "skip"}
DIVISIONS = {
    "dhaka",
    "chattogram",
    "rajshahi",
    "khulna",
    "barishal",
    "sylhet",
    "rangpur",
    "mymensingh",
    "abroad",
    "skip",
}
AUDIO_TYPES = {".wav": "audio/wav", ".webm": "audio/webm", ".ogg": "audio/ogg", ".mp4": "audio/mp4"}
KIND_WEIGHTS = {"booking": 0.65, "info": 0.25, "digits": 0.10, "support": 1.0}
DOMAIN_WEIGHTS = {"hospital": 0.6, "isp": 0.4}  # when a person has not picked a topic
DIALECTS = {
    "standard",
    "dhaka",
    "chattogram",
    "sylhet",
    "noakhali",
    "cumilla",
    "barishal",
    "khulna",
    "rajshahi",
    "rangpur",
    "mymensingh",
    "other",
    "skip",
}
NAME16 = re.compile(r"^[a-f0-9]{16}$")

REJECTION_BN = {
    "too_short": "খুব ছোট রেকর্ডিং, আবার বলুন।",
    "too_long": "রেকর্ডিং বেশি লম্বা, ছোট করে আবার বলুন।",
    "silent": "কথা শোনা যায়নি, ফোনের কাছে এসে আবার বলুন।",
    "clipped": "আওয়াজ ফেটে গেছে, একটু আস্তে বা দূরে থেকে বলুন।",
    "unreadable": "রেকর্ডিং পড়া যায়নি, আবার চেষ্টা করুন।",
    "duplicate": "এই রেকর্ডিং আগেই এসেছে।",
}


def err(code: str, message: str, status: int = 400, **extra: Any) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, **extra}}, status_code=status)


def _step_meta(card: dict[str, Any] | None, request: Request) -> dict[str, Any] | None:
    """What this clip answers, read from the card on the server (the phone only sends ids)."""
    if not card:
        return None
    wanted = request.headers.get("x-step", "")
    if card.get("v") != 2:  # a first-version card: a plain list of steps
        return next((s for s in card.get("steps", []) if s["id"] == wanted), None)
    node = card["nodes"].get(wanted)
    if not node or not node["choices"]:
        return None
    choice_id = request.headers.get("x-choice", "")
    choice = next((c for c in node["choices"] if c["id"] == choice_id), node["choices"][0])
    persona_id = request.headers.get("x-persona", "")
    persona = next((p for p in card.get("personas", []) if p["id"] == persona_id), None)
    facts = dict(choice["facts"]) | {"choice": choice["id"]}
    if persona:
        facts |= {
            "persona": persona["id"],
            "relation": persona["label_bn"],
            "gender": persona["gender"],
        }
    return {
        "id": f"{node['id']}#{choice['id']}",
        "slot": node["slot"],
        "question_bn": node["line_bn"],
        "expected_text": S.resolve(choice["expected"], persona),
        "facts": facts,
    }


def _room_node(card: dict[str, Any] | None, clips: list[dict[str, Any]]) -> str:
    """Where a two-person call has got to in its script: the node the front desk speaks next (or
    the one the caller is answering). The caller's choices move the call on; the front desk only
    answers, so it never decides where the call goes. "" = the script has ended."""
    if not card or card.get("v") != 2:
        return ""
    node = card["start"]
    for clip in sorted(
        (c for c in clips if c["role"] == "caller"),
        key=lambda c: (int(c["turn"] or 0), c["created_at"]),
    ):
        nid, _, cid = (clip.get("step_id") or "").partition("#")
        current = card["nodes"].get(nid)
        if not current or nid != node:
            continue  # an answer to an earlier line (a retry): it does not move the call
        choice = next((c for c in current["choices"] if c["id"] == cid), None)
        if choice is None:
            continue
        node = choice["next"] or ""
        if not node:
            break
    return node


def _sheet_for(card: dict[str, Any] | None) -> dict[str, Any]:
    if (card or {}).get("domain") == "isp":
        from shefa.collector import scripts_isp

        return scripts_isp.sheet()
    return S.clinic_sheet() if (card or {}).get("v") == 2 else P.CLINIC_SHEET


def _ext_for(data: bytes) -> str:
    head = data[:16]
    if head.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return ".wav"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return ".webm"
    if head.startswith(b"OggS"):
        return ".ogg"
    if data[4:8] == b"ftyp":
        return ".mp4"
    return ".bin"


VOICE_NOTE_TYPES = {
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".webm": "audio/webm",
}


def _voice_note_path(cfg: CollectorConfig) -> Path | None:
    """The founder's welcome note. m4a/mp3 first: iPhones cannot play Ogg."""
    for ext in VOICE_NOTE_TYPES:
        path = cfg.data_dir / f"voice_note{ext}"
        if path.exists():
            return path
    return None


class Ctx:
    """What the routes share: the store, the card bank, the limiters and the signing key."""

    def __init__(self, config: CollectorConfig, store: CollectorStore | None = None):
        self.config = config
        self.store = store or CollectorStore(config)
        self.limiter = RateLimiter()
        self.private_limiter = RateLimiter()  # a flood on the public address must not block staff
        self.drafter: Any = None  # set by `serve` when background drafting is on
        # Version 2 scripts are what people get now. The first version's cards stay known by id,
        # so a clip that waited on a phone, or an old two-person room, still finds its card.
        self.cards = S.load_bank(config.prompts_dir / "cards2.json")
        legacy = P.load_bank(config.prompts_dir / "cards.json")
        self.cards_by_id = {c["id"]: c for c in legacy} | {c["id"]: c for c in self.cards}
        self.pack_lines = S.pack_lines(self.cards)
        self.line_text = S.all_lines(self.cards)
        key = self.store.get_setting("audio_key")
        if not key:
            key = os.urandom(32).hex()
            self.store.set_setting("audio_key", key)
        self.key = bytes.fromhex(key)

    def address(self, request: Request) -> str:
        if self.config.trust_forwarded_for:
            for header in ("cf-connecting-ip", "x-forwarded-for"):
                value = request.headers.get(header, "")
                if value:
                    return value.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def sign(self, clip_id: str, ttl: int | None = None) -> str:
        exp = int(time.time()) + (ttl or self.config.audio_url_ttl_s)
        sig = hmac.new(self.key, f"{clip_id}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
        return f"exp={exp}&sig={sig}"

    def verify(self, clip_id: str, exp: int, sig: str) -> bool:
        if exp < time.time():
            return False
        good = hmac.new(self.key, f"{clip_id}.{exp}".encode(), hashlib.sha256).hexdigest()[:32]
        return hmac.compare_digest(good, sig or "")

    def maintenance(self) -> str:
        if self.store.get_setting("kill_switch") == "1":
            return "paused"
        if self.store.audio.free_mb() < self.config.min_free_disk_mb:
            return "disk_low"
        return ""

    def cards_for(
        self,
        seen: set[str],
        n: int,
        kinds: list[str] | None = None,
        domains: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        rng = random.Random()
        domains = domains or ["hospital"]

        def fits(c: dict[str, Any]) -> bool:
            return (not kinds or c["kind"] in kinds) and c.get("domain", "hospital") in domains

        pool = [c for c in self.cards if c["id"] not in seen and fits(c)]
        if not pool:
            pool = [c for c in self.cards if fits(c)]
        out: list[dict[str, Any]] = []
        while pool and len(out) < n:
            present = sorted({c.get("domain", "hospital") for c in pool})
            domain = rng.choices(present, weights=[DOMAIN_WEIGHTS.get(d, 0.3) for d in present])[0]
            in_domain = [c for c in pool if c.get("domain", "hospital") == domain]
            kind = rng.choices(list(KIND_WEIGHTS), weights=list(KIND_WEIGHTS.values()))[0]
            choices = [c for c in in_domain if c["kind"] == kind] or in_domain
            pick = rng.choice(choices)
            out.append(pick)
            pool.remove(pick)
        # A share of calls are "free talk": the page shows only the facts (patient, phone...) and
        # no hint per turn, so people answer in their own way instead of following a wording.
        return [
            self.with_voice(card, rng)
            | (
                {"free": True}
                if card.get("v") == 2
                and card.get("kind") != "digits"
                and rng.random() < self.config.free_talk_share
                else {}
            )
            for card in out
        ]

    def with_voice(self, card: dict[str, Any], rng: random.Random | None = None) -> dict[str, Any]:
        """Sometimes the desk speaks in a recorded human voice: one voice for the whole call, used
        only when that person recorded this call's opening line."""
        rng = rng or random.Random()
        try:
            share = float(
                self.store.get_setting("human_voice_share", str(self.config.human_voice_share))
            )
        except ValueError:
            share = self.config.human_voice_share
        if card.get("v") != 2 or rng.random() >= share:
            return card
        opening = card["nodes"][card["start"]]["audio_name"]
        packs = [p for p in self.store.playable_packs() if opening in p["names"]]
        if not packs:
            return card
        pack = rng.choice(packs)
        names = sorted({n["audio_name"] for n in card["nodes"].values()} & pack["names"])
        return card | {"voice": {"pack": pack["public_id"], "names": names}}


# --------------------------------------------------------------------------- public routes
class StartBody(BaseModel):
    consent: bool
    consent_version: str
    share_ok: bool = False
    campaign: str = Field(default="", max_length=20)
    from_name: str = Field(default="", max_length=40)
    device: str = Field(default="", max_length=120)
    turnstile: str = Field(default="", max_length=2000)


class ConsentBody(BaseModel):
    consent_version: str
    share_ok: bool = False


class SpeakerBody(BaseModel):
    share_ok: bool = False


class ProfileBody(BaseModel):
    dialect: str = ""
    age_band: str = ""
    gender: str = ""
    division: str = ""
    nickname: str = Field(default="", max_length=30)
    credit_ok: bool = False


class DeleteBody(BaseModel):
    delete_code: str = Field(max_length=40)


class RoomBody(BaseModel):
    card_id: str = ""
    code: str = ""


async def _verify_turnstile(ctx: Ctx, token: str, ip: str) -> bool:
    if not ctx.config.turnstile_site_key:
        return True
    secret = os.environ.get(ctx.config.turnstile_secret_env, "")
    if not secret or not token:
        return False
    import httpx

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            reply = await client.post(
                "https://challenges.cloudflare.com/turnstile/v0/siteverify",
                data={"secret": secret, "response": token, "remoteip": ip},
            )
        return bool(reply.json().get("success"))
    except Exception:  # noqa: BLE001 - a failed check is a failed check
        return False


def public_router(ctx: Ctx) -> APIRouter:
    r = APIRouter()
    store, cfg = ctx.store, ctx.config

    def who(request: Request) -> tuple[str, dict[str, Any]] | JSONResponse:
        cid = request.headers.get("x-cid", "")
        if not store.check_contributor(cid, request.headers.get("x-secret", "")):
            return err("not_signed_in", "please start again", 401)
        speaker = store.speaker(request.headers.get("x-speaker", ""), cid)
        if not speaker:
            return err("no_speaker", "please start again", 401)
        return cid, speaker

    @r.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "maintenance": ctx.maintenance()}

    @r.get("/api/c/config")
    async def config(c: str = "") -> dict[str, Any]:
        camp = store.campaign(c)
        return {
            "consent_version": cfg.consent_version,
            "consent_bn": CONSENT_V2_BN,
            "consent_en": CONSENT_V2_EN,
            "share_bn": SHARE_BN,
            "share_en": SHARE_EN,
            "dialects": sorted(DIALECTS),
            "topics": ["hospital", "isp"],
            "turnstile_site_key": cfg.turnstile_site_key,
            "min_clip_s": cfg.min_clip_s,
            "max_clip_s": cfg.max_clip_s,
            "clinic_bn": S.CLINIC,
            "nudge_after_clips": cfg.nudge_after_clips,
            "settings": P.settings_choices(),
            "from_name": (camp or {}).get("from_name", ""),
            "campaign": (camp or {}).get("code", ""),
            "maintenance": ctx.maintenance(),
            "progress": store.progress(),
            "age_bands": sorted(AGE_BANDS),
            "divisions": sorted(DIVISIONS),
            "voice_note": _voice_note_path(cfg) is not None,
            "impact_note": store.get_setting("impact_note"),
        }

    @r.post("/api/c/start")
    async def start(body: StartBody, request: Request):
        ip = ctx.address(request)
        if not ctx.limiter.allow(f"start:{ip}", cfg.starts_per_ip_per_hour, 3600):
            return err("slow_down", "too many new visitors from here, try again later", 429)
        if not body.consent or body.consent_version != cfg.consent_version:
            return err("consent", "please read and accept the consent", 400)
        if not await _verify_turnstile(ctx, body.turnstile, ip):
            return err("challenge", "the human check failed, reload and retry", 403)
        made = store.start_contributor(
            campaign=body.campaign,
            from_name=body.from_name,
            ip=ip,
            device=body.device,
            share_ok=body.share_ok,
        )
        return {**made, "maintenance": ctx.maintenance()}

    @r.post("/api/c/speaker")
    async def speaker(request: Request, body: SpeakerBody | None = None):
        got = who(request)
        if isinstance(got, JSONResponse):
            return got
        return store.new_speaker(got[0], share_ok=bool(body and body.share_ok))

    @r.post("/api/c/consent")
    async def consent(body: ConsentBody, request: Request):
        """Agree to the current consent without becoming a new person."""
        got = who(request)
        if isinstance(got, JSONResponse):
            return got
        if body.consent_version != cfg.consent_version:
            return err("consent", "please read and accept the consent", 400)
        store.reconsent(got[0], got[1]["id"], body.share_ok)
        return {"ok": True, "consent_version": cfg.consent_version}

    @r.get("/api/c/cards")
    async def cards(request: Request, n: int = 3, seen: str = "", kinds: str = "", topic: str = ""):
        got = who(request)
        if isinstance(got, JSONResponse):
            return got
        # Someone who agreed only to the first consent (hospital calls for SHEFA) gets hospital
        # calls until they agree to the current one.
        allowed = (
            ["hospital"] if got[1].get("consent_version") == CONSENT_V1 else ["hospital", "isp"]
        )
        domains = [topic] if topic in allowed else allowed
        picked = ctx.cards_for(
            {s for s in seen.split(",") if s},
            max(1, min(n, 8)),
            [k for k in kinds.split(",") if k] or None,
            domains,
        )
        return {"cards": picked}

    @r.put("/api/c/clip/{clip_id}")
    async def upload(clip_id: str, request: Request):
        if not CLIP_ID.match(clip_id):
            return err("bad_id", "bad clip id")
        got = who(request)
        if isinstance(got, JSONResponse):
            return got
        cid, speaker_row = got
        if reason := ctx.maintenance():
            return err(
                "paused",
                "the collection is paused right now, your clip stays on your phone",
                503,
                reason=reason,
            )
        ip = ctx.address(request)
        if not ctx.limiter.allow(f"clip:{ip}", cfg.clips_per_ip_per_hour, 3600):
            return err("slow_down", "too many recordings from here, try again later", 429)
        if store.clips_today(cid) >= cfg.clips_per_contributor_per_day:
            return err("daily_cap", "that is plenty for today, thank you!", 429)
        declared = int(request.headers.get("content-length") or 0)
        if declared > cfg.max_clip_bytes:
            return err("too_big", "recording is too large", 413)
        data = b""
        async for chunk in request.stream():
            data += chunk
            if len(data) > cfg.max_clip_bytes:
                return err("too_big", "recording is too large", 413)
        sha = hashlib.sha256(data).hexdigest()
        claimed = request.headers.get("x-sha256", "")
        if claimed and claimed != sha:
            return err(
                "corrupt", "the recording was damaged on the way, it will be sent again", 422
            )
        if _ext_for(data) == ".bin":  # only the containers a browser recorder makes are decoded
            return err("unreadable", REJECTION_BN["unreadable"], 422, reason="unreadable")
        try:
            samples, codec = await run_in_threadpool(A.decode, data)
        except A.AudioError:
            return err("unreadable", REJECTION_BN["unreadable"], 422, reason="unreadable")
        quality = A.measure(samples, codec)
        reason = (
            "too_short"
            if quality.duration_s < cfg.min_clip_s
            else "too_long"
            if quality.duration_s > cfg.max_clip_s
            else "silent"
            if quality.speech_ratio < cfg.min_speech_ratio
            else "clipped"
            if quality.clip_fraction > cfg.max_clip_fraction
            else ""
        )
        if reason:
            return err("rejected", REJECTION_BN[reason], 422, reason=reason)
        card = ctx.cards_by_id.get(request.headers.get("x-card", ""))
        if (card or {}).get("domain", "hospital") != "hospital" and speaker_row.get(
            "consent_version"
        ) == CONSENT_V1:
            return err("consent", "please agree to the new consent first", 403)
        step = _step_meta(card, request)
        setting = request.headers.get("x-setting", "")
        room_code, role = request.headers.get("x-room", "")[:8].upper(), ""
        if room_code:  # a two-person clip counts only if the uploader really is in that room
            room_row = store.get_room(room_code)
            if not room_row or cid not in (room_row["caller_cid"], room_row["desk_cid"]):
                return err("no_room", "you are not in that room", 403)
            role = (
                "caller" if room_row["caller_cid"] == cid else "desk"
            )  # the server decides the role
            card = ctx.cards_by_id.get(room_row["card_id"])  # and the card: the room's own
            step = _step_meta(card, request)
        meta = {
            "card_id": card["id"] if card else "",
            "step_id": step["id"] if step else "",
            "slot": step["slot"] if step else request.headers.get("x-slot", "")[:20],
            "kind": card["kind"] if card else request.headers.get("x-kind", "")[:20],
            "question_bn": step["question_bn"] if step else "",
            "expected_text": step["expected_text"] if step else None,
            "facts": (step["facts"] if step else {})
            | ({"auto_stopped": True} if request.headers.get("x-autostop") == "1" else {})
            | ({"free_talk": True} if request.headers.get("x-free") == "1" else {}),
            "setting": setting if setting in SETTING_IDS else "",
            "room": room_code,
            "role": role,
            "turn": request.headers.get("x-turn", "0")[:3],
        }
        if role == "desk":
            # The front desk was guided to say this node's line in their own words: the clip is
            # front-desk speech (kept out of the caller training set by default), not a caller answer.
            node = ((card or {}).get("nodes") or {}).get(request.headers.get("x-step", ""))
            meta |= {
                "step_id": node["id"] if node else "",
                "slot": "desk",
                "question_bn": node["line_bn"] if node else "",
                "expected_text": None,
                "facts": {"guided_line": bool(node)}
                | ({"auto_stopped": True} if request.headers.get("x-autostop") == "1" else {}),
            }
        try:
            if store._one(
                "SELECT 1 FROM clips WHERE sha256=? AND id!=? AND deleted_at IS NULL",
                (sha, clip_id),
            ):
                return err("duplicate", REJECTION_BN["duplicate"], 409, reason="duplicate")
            out = await run_in_threadpool(
                lambda: store.add_clip(
                    clip_id=clip_id,
                    speaker=speaker_row,
                    cid=cid,
                    meta=meta,
                    quality=quality,
                    data=data,
                    ext=_ext_for(data),
                    ua=request.headers.get("user-agent", ""),
                )
            )
        except StoreError as e:
            return err(e.code, e.message, e.status)
        return {
            "ok": True,
            **out,
            "duration_s": round(quality.duration_s, 1),
            "snr_db": round(quality.snr_db, 1),
        }

    @r.post("/api/c/profile")
    async def profile(body: ProfileBody, request: Request):
        got = who(request)
        if isinstance(got, JSONResponse):
            return got
        store.set_profile(
            got[1]["id"],
            age_band=body.age_band if body.age_band in AGE_BANDS else "",
            gender=body.gender if body.gender in GENDERS else "",
            division=body.division if body.division in DIVISIONS else "",
            dialect=body.dialect if body.dialect in DIALECTS else "",
            nickname=re.sub(r"[^\w\u0980-\u09ff .\-]", "", body.nickname),
            credit_ok=body.credit_ok,
        )
        return {"ok": True}

    @r.post("/api/c/delete")
    async def delete(body: DeleteBody, request: Request):
        ip = ctx.address(request)
        if not ctx.limiter.allow(f"del:{ip}", 12, 3600):
            return err("slow_down", "too many tries", 429)
        try:
            count = store.delete_by_code(body.delete_code)
        except StoreError as e:
            return err(e.code, e.message, e.status)
        return {"ok": True, "deleted": count}

    @r.get("/api/c/progress")
    async def progress() -> dict[str, Any]:
        return store.progress()

    @r.get("/api/c/thanks")
    async def thanks() -> dict[str, Any]:
        return {"names": store.thanks()}

    # ---- call a friend: two phones, one code, turns kept in step ----------------------
    @r.post("/api/c/room")
    async def room_create(body: RoomBody, request: Request):
        got = who(request)
        if isinstance(got, JSONResponse):
            return got
        card = ctx.cards_by_id.get(body.card_id) or ctx.cards_for(set(), 1, ["booking"])[0]
        return {"code": store.create_room(got[0], card["id"]), "card": card, "role": "caller"}

    @r.post("/api/c/room/join")
    async def room_join(body: RoomBody, request: Request):
        got = who(request)
        if isinstance(got, JSONResponse):
            return got
        if not ctx.limiter.allow(f"join:{ctx.address(request)}", 30, 600):
            return err("slow_down", "too many tries, wait a few minutes", 429)
        try:
            room = store.join_room(body.code, got[0])
        except StoreError as e:
            return err(e.code, e.message, e.status)
        role = "caller" if room["caller_cid"] == got[0] else "desk"
        return {
            "code": room["code"],
            "role": role,
            "card": ctx.cards_by_id.get(room["card_id"]),
            "state": room["state"],
            "sheet": _sheet_for(ctx.cards_by_id.get(room["card_id"])) if role == "desk" else None,
        }

    @r.get("/api/c/room/{code}")
    async def room_state(code: str, request: Request):
        got = who(request)
        if isinstance(got, JSONResponse):
            return got
        room = store.get_room(code)
        if not room or got[0] not in (room["caller_cid"], room["desk_cid"]):
            return err("no_room", "no such room", 404)
        role = "caller" if room["caller_cid"] == got[0] else "desk"
        return {
            "state": room["state"],
            "role": role,
            "clips": store.room_clips(room["code"]),
            "node": _room_node(
                ctx.cards_by_id.get(room["card_id"]), store.room_clips(room["code"])
            ),
            "partner_here": bool(room["desk_cid"]),
            "card": ctx.cards_by_id.get(room["card_id"]),
            "sheet": _sheet_for(ctx.cards_by_id.get(room["card_id"])) if role == "desk" else None,
        }

    @r.get("/api/c/room/{code}/clip/{clip_id}")
    async def room_clip(code: str, clip_id: str, request: Request):
        got = who(request)
        if isinstance(got, JSONResponse):
            return got
        room = store.get_room(code)
        clip = store.get_clip(clip_id) if CLIP_ID.match(clip_id) else None
        if (
            not room
            or not clip
            or clip["room"] != room["code"]
            or got[0] not in (room["caller_cid"], room["desk_cid"])
        ):
            return err("no_clip", "not found", 404)
        path = Path(clip["path"])
        return Response(
            path.read_bytes(),
            media_type=AUDIO_TYPES.get(path.suffix, "application/octet-stream"),
            headers={"Cache-Control": "private, max-age=600"},
        )

    @r.get("/q2/{name}.m4a")
    async def line_audio(name: str):
        path = cfg.prompts_dir / "q2" / f"{name}.m4a"
        if not NAME16.match(name) or not path.exists():
            return err("not_found", "not found", 404)
        return FileResponse(
            path, media_type="audio/mp4", headers={"Cache-Control": "public, max-age=86400"}
        )

    @r.get("/hv/{pack}/{name}.m4a")
    async def human_line(pack: str, name: str):
        """A desk line in a staff member's recorded voice. Served only while the admin keeps that
        pack switched on; the address carries a random id, never who the person is."""
        row = store.pack_by_public_id(pack) if re.fullmatch(r"[a-f0-9]{32}", pack) else None
        path = store.voice_line_path(row["staff_id"], name) if row and NAME16.match(name) else None
        if path is None:
            return err("not_found", "not found", 404)
        return FileResponse(path, media_type="audio/mp4", headers={"Cache-Control": "no-store"})

    @r.get("/q/{name}.wav")
    async def question_audio(name: str):
        if not re.fullmatch(r"[a-f0-9]{16}", name):
            return err("not_found", "not found", 404)
        path = cfg.prompts_dir / "q" / f"{name}.wav"
        if not path.exists():
            return err("not_found", "not found", 404)
        return FileResponse(
            path, media_type="audio/wav", headers={"Cache-Control": "public, max-age=86400"}
        )

    @r.get("/voice-note")
    async def voice_note():
        path = _voice_note_path(cfg)
        if path is None:
            return err("not_found", "not found", 404)
        return FileResponse(path, media_type=VOICE_NOTE_TYPES[path.suffix])

    return r


# --------------------------------------------------------------------------- staff routes
def _bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    return header[7:] if header.lower().startswith("bearer ") else ""


def _staff(
    ctx: Ctx, request: Request, roles: set[str], *, allow_must_change: bool = False
) -> dict[str, Any] | JSONResponse:
    staff = ctx.store.staff_for(_bearer(request))
    if not staff:
        # Session tokens are 256-bit random, so guessing is hopeless; this only stops hammering.
        if not ctx.limiter.allow(f"badtoken:{ctx.address(request)}", 60, 600):
            return err("slow_down", "too many tries, wait a few minutes", 429)
        return err("unauthorized", "please sign in", 401)
    if staff["role"] not in roles:
        return err("forbidden", "this account cannot do that here", 403)
    if staff.get("must_change") and not allow_must_change:
        return err("must_change", "choose your own password first", 403)
    return staff


class LoginBody(BaseModel):
    username: str = Field(max_length=60)
    password: str = Field(max_length=200)


class PasswordBody(BaseModel):
    old: str = Field(max_length=200)
    new: str = Field(max_length=200)


def account_router(ctx: Ctx, *, public: bool) -> APIRouter:
    """Sign in, sign out, change your own password. On the public address an admin account is
    refused even with the right password: the admin works on the clinic computer only."""
    r = APIRouter()
    roles = {"reviewer", "adjudicator"} if public else {"reviewer", "adjudicator", "admin"}

    @r.post("/api/staff/login")
    async def login(body: LoginBody, request: Request):
        ip = ctx.address(request)
        limiter = ctx.limiter if public else ctx.private_limiter
        if not limiter.allow(f"login:{ip}", 30, 600):
            return err("slow_down", "too many tries from here, wait a few minutes", 429)
        try:
            out = await run_in_threadpool(
                ctx.store.sign_in, body.username, body.password, ip, roles
            )
        except StoreError as e:
            return err(e.code, e.message, e.status)
        out.pop("id", None)
        return out

    @r.post("/api/staff/logout")
    async def logout(request: Request):
        ctx.store.sign_out(_bearer(request))
        return {"ok": True}

    @r.post("/api/staff/password")
    async def password(body: PasswordBody, request: Request):
        staff = _staff(ctx, request, roles, allow_must_change=True)
        if isinstance(staff, JSONResponse):
            return staff
        if not ctx.limiter.allow(f"pw:{staff['id']}", 10, 600):
            return err("slow_down", "too many tries, wait a few minutes", 429)
        try:
            token = await run_in_threadpool(ctx.store.change_password, staff, body.old, body.new)
        except StoreError as e:
            return err(e.code, e.message, e.status)
        return {"ok": True, "token": token}

    return r


class ReviewBody(BaseModel):
    clip_id: str
    text: str = Field(default="", max_length=600)
    flags: list[str] = Field(default_factory=list, max_length=8)
    seconds: float | None = None


def review_router(ctx: Ctx, *, public: bool) -> APIRouter:
    r = APIRouter()
    roles = {"reviewer", "adjudicator"} if public else {"reviewer", "adjudicator", "admin"}

    @r.get("/api/review/me")
    async def me(request: Request):
        staff = _staff(ctx, request, roles, allow_must_change=True)
        if isinstance(staff, JSONResponse):
            return staff
        mine = ctx.store._one(
            "SELECT COUNT(*) n FROM reviews WHERE staff_id=? AND kind!='seed'", (staff["id"],)
        )
        return {
            "name": staff["name"],
            "username": staff.get("username") or "",
            "role": staff["role"],
            "reviewed": mine["n"],
            "must_change": bool(staff.get("must_change")),
        }

    @r.get("/api/review/next")
    async def nxt(request: Request):
        staff = _staff(ctx, request, roles)
        if isinstance(staff, JSONResponse):
            return staff
        item = ctx.store.next_for_review(staff)
        if not item:
            return {"item": None}
        item["audio_url"] = f"/api/review/audio/{item['clip_id']}?{ctx.sign(item['clip_id'])}"
        return {"item": item}

    @r.post("/api/review/submit")
    async def submit(body: ReviewBody, request: Request):
        staff = _staff(ctx, request, roles)
        if isinstance(staff, JSONResponse):
            return staff
        if not ctx.limiter.allow(f"rv:{staff['id']}", 600, 3600):
            return err("slow_down", "slow down a little", 429)
        try:
            out = await run_in_threadpool(
                ctx.store.submit_review, staff, body.clip_id, body.text, body.flags, body.seconds
            )
        except StoreError as e:
            return err(e.code, e.message, e.status)
        return out

    # ---- record the desk's lines in your own voice (played to contributors) ------------------
    @r.get("/api/voice/lines")
    async def voice_lines(request: Request):
        staff = _staff(ctx, request, roles)
        if isinstance(staff, JSONResponse):
            return staff
        pack = ctx.store.voice_pack(staff["id"])
        have = ctx.store.voice_names(staff["id"])
        return {
            "consented": bool(pack["consent_at"]),
            "enabled": bool(pack["enabled"]),
            "lines": [line | {"recorded": line["name"] in have} for line in ctx.pack_lines],
        }

    @r.post("/api/voice/consent")
    async def voice_consent(request: Request):
        staff = _staff(ctx, request, roles)
        if isinstance(staff, JSONResponse):
            return staff
        ctx.store.voice_consent(staff["id"])
        return {"ok": True}

    @r.put("/api/voice/line/{name}")
    async def voice_put(name: str, request: Request):
        staff = _staff(ctx, request, roles)
        if isinstance(staff, JSONResponse):
            return staff
        if name not in {line["name"] for line in ctx.pack_lines}:
            return err("not_found", "no such line", 404)
        data = b""
        async for chunk in request.stream():
            data += chunk
            if len(data) > 1_500_000:
                return err("too_big", "recording is too large", 413)
        if _ext_for(data) == ".bin":
            return err("unreadable", REJECTION_BN["unreadable"], 422, reason="unreadable")
        try:
            samples, codec = await run_in_threadpool(A.decode, data)
        except A.AudioError:
            return err("unreadable", REJECTION_BN["unreadable"], 422, reason="unreadable")
        quality = A.measure(samples, codec)
        reason = (
            "too_short"
            if quality.duration_s < 1.0
            else "too_long"
            if quality.duration_s > 30
            else "silent"
            if quality.speech_ratio < ctx.config.min_speech_ratio
            else "clipped"
            if quality.clip_fraction > ctx.config.max_clip_fraction
            else ""
        )
        if reason:
            return err("rejected", REJECTION_BN[reason], 422, reason=reason)
        encoded = await run_in_threadpool(lambda: A.encode_m4a(samples, normalise=True))
        try:
            ctx.store.save_voice_line(staff["id"], name, encoded, quality.duration_s)
        except StoreError as e:
            return err(e.code, e.message, e.status)
        return {"ok": True, "duration_s": round(quality.duration_s, 1)}

    @r.get("/api/voice/line/{name}")
    async def voice_get(name: str, request: Request):
        staff = _staff(ctx, request, roles)
        if isinstance(staff, JSONResponse):
            return staff
        path = ctx.store.voice_line_path(staff["id"], name)
        if path is None:
            return err("not_found", "not found", 404)
        return Response(
            path.read_bytes(), media_type="audio/mp4", headers={"Cache-Control": "no-store"}
        )

    @r.delete("/api/voice/line/{name}")
    async def voice_delete(name: str, request: Request):
        staff = _staff(ctx, request, roles)
        if isinstance(staff, JSONResponse):
            return staff
        return {"ok": True, "deleted": ctx.store.delete_voice_lines(staff["id"], name)}

    @r.delete("/api/voice")
    async def voice_delete_all(request: Request):
        staff = _staff(ctx, request, roles)
        if isinstance(staff, JSONResponse):
            return staff
        return {"ok": True, "deleted": ctx.store.delete_voice_lines(staff["id"])}

    @r.get("/api/review/audio/{clip_id}")
    async def audio(clip_id: str, exp: int = 0, sig: str = ""):
        if not CLIP_ID.match(clip_id) or not ctx.verify(clip_id, exp, sig):
            return err("expired", "this link has expired, reload", 403)
        clip = ctx.store.get_clip(clip_id)
        if not clip or not clip["path"]:
            return err("not_found", "not found", 404)
        path = Path(clip["path"])
        return Response(
            path.read_bytes(),
            media_type=AUDIO_TYPES.get(path.suffix, "application/octet-stream"),
            headers={"Cache-Control": "private, no-store"},
        )

    return r


class CampaignBody(BaseModel):
    name: str = Field(max_length=80)
    from_name: str = Field(default="", max_length=60)
    note: str = Field(default="", max_length=200)


class StaffBody(BaseModel):
    name: str = Field(max_length=60)
    role: str
    username: str = Field(default="", max_length=30)


class VoicePackBody(BaseModel):
    enabled: bool


class SettingBody(BaseModel):
    kill_switch: bool | None = None
    human_voice_share: float | None = Field(default=None, ge=0, le=1)
    goal_minutes: int | None = Field(default=None, ge=1, le=100000)
    impact_note: str | None = Field(
        default=None, max_length=300
    )  # shown to contributors: what their clips achieved


class RemoveBody(BaseModel):
    reason: str = Field(default="removed by admin", max_length=120)


def admin_router(ctx: Ctx) -> APIRouter:
    r = APIRouter()
    store = ctx.store

    def gate(request: Request):
        return _staff(ctx, request, {"admin"})

    @r.get("/api/admin/stats")
    async def stats(request: Request):
        s = gate(request)
        if isinstance(s, JSONResponse):
            return s
        return {
            **store.stats(),
            "impact_note": store.get_setting("impact_note"),
            "drafts": {
                "waiting": store._one(
                    "SELECT COUNT(*) n FROM clips WHERE draft_text IS NULL AND deleted_at IS NULL AND status!='rejected'"
                )["n"],
                "running": bool(getattr(ctx, "drafter", None))
                and not getattr(ctx.drafter, "error", ""),
                "error": getattr(getattr(ctx, "drafter", None), "error", ""),
            },
            "human_voice_share": float(
                store.get_setting("human_voice_share", str(ctx.config.human_voice_share))
            ),
            "reviewers": store.reviewer_report(),
            "backlog": {
                "to_review": store._one(
                    "SELECT COUNT(*) n FROM clips WHERE deleted_at IS NULL AND status='pending'"
                )["n"],
                "disputed": store._one(
                    "SELECT COUNT(*) n FROM clips WHERE deleted_at IS NULL AND status='disputed'"
                )["n"],
            },
        }

    @r.get("/api/admin/campaigns")
    async def campaigns(request: Request):
        s = gate(request)
        return s if isinstance(s, JSONResponse) else {"campaigns": store.list_campaigns()}

    @r.post("/api/admin/campaigns")
    async def new_campaign(body: CampaignBody, request: Request):
        s = gate(request)
        if isinstance(s, JSONResponse):
            return s
        code = store.create_campaign(body.name, body.from_name, body.note)
        store.audit(s["name"], "campaign_created", body.name)
        return {"code": code, "path": f"/?c={code}"}

    @r.get("/api/admin/staff")
    async def staff(request: Request):
        s = gate(request)
        return s if isinstance(s, JSONResponse) else {"staff": store.list_staff()}

    @r.post("/api/admin/staff")
    async def new_staff(body: StaffBody, request: Request):
        s = gate(request)
        if isinstance(s, JSONResponse):
            return s
        try:
            made = await run_in_threadpool(
                store.create_staff, body.name, body.role, body.username or None
            )
        except StoreError as e:
            return err(e.code, e.message, e.status)
        store.audit(s["name"], "staff_added", made["username"])
        return {
            "username": made["username"],
            "password": made["password"],
            "note": "shown once; the person must change it at first sign-in",
        }

    @r.post("/api/admin/staff/{staff_id}/reset")
    async def reset_staff(staff_id: int, request: Request):
        s = gate(request)
        if isinstance(s, JSONResponse):
            return s
        try:
            secret = await run_in_threadpool(store.set_password, staff_id)
        except StoreError as e:
            return err(e.code, e.message, e.status)
        store.audit(s["name"], "password_reset", str(staff_id))
        row = next((p for p in store.list_staff() if p["id"] == staff_id), {})
        return {"username": row.get("username"), "password": secret}

    @r.delete("/api/admin/staff/{staff_id}")
    async def drop_staff(staff_id: int, request: Request):
        s = gate(request)
        if isinstance(s, JSONResponse):
            return s
        try:
            store.deactivate_staff(staff_id)
        except StoreError as e:
            return err(e.code, e.message, e.status)
        store.audit(s["name"], "staff_deactivated", str(staff_id))
        return {"ok": True}

    @r.get("/api/admin/clips")
    async def clips(
        request: Request, status: str = "", limit: int = 100, offset: int = 0, sort: str = "new"
    ):
        s = gate(request)
        if isinstance(s, JSONResponse):
            return s
        rows = store.clip_rows(status, min(limit, 500), offset, sort)
        for row in rows:
            row["audio_url"] = f"/api/review/audio/{row['id']}?{ctx.sign(row['id'])}"
        return {"clips": rows}

    @r.post("/api/admin/clips/{clip_id}/remove")
    async def remove(clip_id: str, body: RemoveBody, request: Request):
        s = gate(request)
        if isinstance(s, JSONResponse):
            return s
        return {"ok": store.remove_clip(clip_id, s["name"], body.reason)}

    @r.get("/api/admin/voices")
    async def voices(request: Request):
        s = gate(request)
        if isinstance(s, JSONResponse):
            return s
        share = store.get_setting("human_voice_share", str(ctx.config.human_voice_share))
        packs = [
            {k: p[k] for k in ("staff_id", "name", "lines", "active")}
            | {
                "enabled": bool(p["enabled"]),
                "consented": bool(p["consent_at"]),
                "recorded": sorted(store.voice_names(p["staff_id"])),
            }
            for p in store.voice_packs()
        ]
        return {
            "packs": packs,
            "share": float(share),
            "total_lines": len(ctx.pack_lines),
            "lines": ctx.pack_lines,
        }

    @r.post("/api/admin/voices/{staff_id}")
    async def voice_enable(staff_id: int, body: VoicePackBody, request: Request):
        s = gate(request)
        if isinstance(s, JSONResponse):
            return s
        try:
            store.set_pack_enabled(staff_id, body.enabled, s["name"])
        except StoreError as e:
            return err(e.code, e.message, e.status)
        return {"ok": True}

    @r.get("/api/admin/voices/{staff_id}/{name}")
    async def voice_listen(staff_id: int, name: str, request: Request):
        s = gate(request)
        if isinstance(s, JSONResponse):
            return s
        path = store.voice_line_path(staff_id, name)
        if path is None:
            return err("not_found", "not found", 404)
        return Response(
            path.read_bytes(), media_type="audio/mp4", headers={"Cache-Control": "no-store"}
        )

    @r.post("/api/admin/clips/{clip_id}/restore")
    async def restore(clip_id: str, request: Request):
        s = gate(request)
        if isinstance(s, JSONResponse):
            return s
        return {"ok": store.restore_clip(clip_id, s["name"])}

    @r.post("/api/admin/settings")
    async def settings(body: SettingBody, request: Request):
        s = gate(request)
        if isinstance(s, JSONResponse):
            return s
        if body.kill_switch is not None:
            store.set_setting("kill_switch", "1" if body.kill_switch else "0")
            store.audit(s["name"], "kill_switch", str(body.kill_switch))
        if body.goal_minutes is not None:
            store.set_setting("goal_minutes", str(body.goal_minutes))
        if body.human_voice_share is not None:
            store.set_setting("human_voice_share", str(body.human_voice_share))
        if body.impact_note is not None:
            store.set_setting("impact_note", body.impact_note.strip())
            store.audit(s["name"], "impact_note", body.impact_note.strip()[:120])
        return {"ok": True}

    @r.get("/api/admin/audit")
    async def audit(request: Request, limit: int = 100):
        s = gate(request)
        if isinstance(s, JSONResponse):
            return s
        return {
            "events": [
                dict(row)
                for row in store._q(
                    "SELECT * FROM audit ORDER BY id DESC LIMIT ?", (min(limit, 500),)
                )
            ]
        }

    return r


# --------------------------------------------------------------------------- apps
HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "microphone=(self), camera=(), geolocation=()",
    "Cache-Control": "no-cache",
}


def _wrap(app: FastAPI, cfg: CollectorConfig, *, public: bool) -> None:
    turnstile = " https://challenges.cloudflare.com" if cfg.turnstile_site_key else ""
    csp = (
        f"default-src 'self'; script-src 'self'{turnstile}; style-src 'self' 'unsafe-inline'; "
        f"img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'{turnstile}; "
        f"frame-src{turnstile or ' ' + chr(39) + 'none' + chr(39)}; base-uri 'none'; form-action 'self'"
    )

    @app.middleware("http")
    async def secure(request: Request, call_next):
        response = await call_next(request)
        for key, value in HEADERS.items():
            response.headers.setdefault(key, value)
        if response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Content-Security-Policy"] = csp
        if public is False:
            response.headers["Cache-Control"] = "no-store"
        return response

    if cfg.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cfg.allowed_origins,
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=["*"],
            max_age=600,
        )


class _ApiGzip:
    """Compress JSON from /api/ only. Audio is already compressed, and a gzipped partial (206)
    response breaks the audio player on iPhones, which asks for byte ranges."""

    def __init__(self, app: Any):
        self.app = app
        self.gzip = GZipMiddleware(app, minimum_size=4000)

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] == "http" and scope["path"].startswith("/api/"):
            await self.gzip(scope, receive, send)
        else:
            await self.app(scope, receive, send)


def create_public_app(config: CollectorConfig, ctx: Ctx | None = None) -> FastAPI:
    ctx = ctx or Ctx(config)
    app = FastAPI(title="SHEFA Voice Commons", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.ctx = ctx
    _wrap(app, config, public=True)
    app.add_middleware(_ApiGzip)  # a script is ~15 KB of JSON; audio is never compressed
    app.include_router(public_router(ctx))
    if config.reviewers_on_public:
        app.include_router(account_router(ctx, public=True))
        app.include_router(review_router(ctx, public=True))
        if (STATIC / "private").exists():
            app.mount(
                "/review", StaticFiles(directory=STATIC / "private", html=True), name="review"
            )
    if (STATIC / "public").exists():
        app.mount("/", StaticFiles(directory=STATIC / "public", html=True), name="public")
    return app


def create_private_app(config: CollectorConfig, ctx: Ctx | None = None) -> FastAPI:
    ctx = ctx or Ctx(config)
    app = FastAPI(
        title="SHEFA Voice Commons (staff)", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.ctx = ctx
    _wrap(app, config, public=False)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        # The staff app answers only when addressed as this computer. A web page elsewhere that
        # points a made-up name at 127.0.0.1 (DNS rebinding) is refused.
        host = request.headers.get("host", "").rsplit(":", 1)[0].strip("[]")
        if host not in ("127.0.0.1", "localhost", "::1", "testserver"):
            return err("forbidden", "open this page as http://127.0.0.1", 403)
        return await call_next(request)

    app.include_router(account_router(ctx, public=False))
    app.include_router(review_router(ctx, public=False))
    app.include_router(admin_router(ctx))

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True}

    if (STATIC / "private").exists():
        app.mount("/", StaticFiles(directory=STATIC / "private", html=True), name="private")
    return app
