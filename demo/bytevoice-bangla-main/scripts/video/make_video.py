"""Render the submission video: Nila narrates every feature in Bangla (Gemini TTS, the same Kore voice as the live
agent) over automated recordings of the web app.

Run from apps/agent (it reuses the agent's Google key and accent instructions):

    uv run --with playwright --with imageio-ffmpeg python ../../scripts/video/make_video.py \
        --base-url http://localhost:3100 --output ../../docs/video/bytevoice-nila.mp4

Set PORTAL_EMAIL and PORTAL_PASSWORD to include the portal scenes; they need a portal with real calls in it.
"""

import argparse
import asyncio
import hashlib
import logging
import os
import subprocess
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path

import imageio_ffmpeg
from dotenv import load_dotenv
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from playwright.async_api import Browser, Page, async_playwright
from playwright.async_api import Error as PlaywrightError
from pydantic import BaseModel

load_dotenv(".env.local")
logger = logging.getLogger("bytevoice.video")

VIEWPORT = {"width": 1600, "height": 900}
TTS_MODELS = ("gemini-3.8-flash-tts", "gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts")
QUOTA_EXHAUSTED_STATUS = 429
TTS_VOICE = "Kore"
SAMPLE_RATE = 24000
TAIL_SECONDS = 0.6
MAX_VIDEO_SECONDS = 180
MAX_TTS_ATTEMPTS = 6
BANGLA_CHARACTERS_PER_SECOND = 13.0
MAX_LENGTH_RATIO = 1.45
MAX_TRANSCRIPT_RATIO = 1.35
VERIFY_MODEL = "gemini-3.8-flash"
SILENCE_THRESHOLD = "-42dB"
MAX_PAUSE_SECONDS = 0.45
KEPT_PAUSE_SECONDS = 0.3
CALL_BUTTON = "button:has-text('বাংলা কলারের সাথে কথা বলুন')"


@dataclass
class Action:
    kind: str
    target: str = ""


@dataclass
class Scene:
    key: str
    path: str
    narration_bn: str
    start_at: str = ""
    actions: list[Action] = field(default_factory=list)
    needs_login: bool = False
    settled: bool = False
    fresh_session: bool = False


LANDING_SCENES = [
    Scene(
        "hero",
        "/",
        "আসসালামু আলাইকুম! আমি নীলা, ByteVoice Bangla-র AI রিসেপশনিস্ট। ক্লিনিকের ফোন চব্বিশ ঘণ্টা বাংলায় ধরি। "
        "এই থ্রি-ডি অর্বটাই কলের স্ক্রিন, আর পুরো সাইট বাংলা-ইংরেজি দুই ভাষাতেই।",
        actions=[Action("click", "header button[aria-label]"), Action("click", "header button[aria-label]")],
    ),
    Scene(
        "persona",
        "/",
        "রোগী কল করলে আমি নাম নিই, নম্বরের প্রতিটা সংখ্যা পড়ে শোনাই, ‘আগামী রবিবার সন্ধ্যা’ থেকে সঠিক তারিখ বের করি, "
        "ডাক্তারের খালি সময় দেখি, আর রোগী হ্যাঁ বললে তবেই বুক করি।",
        start_at="#meet-nila",
    ),
    Scene(
        "features",
        "/",
        "বাংলা-ইংরেজি মেশানো কথা বুঝি, মাঝে থামালে থেমে শুনি। ওষুধের পরামর্শ দিই না, জরুরি হলে নাইন নাইন নাইনে কল করতে বলি। "
        "ডাক্তারের ব্যক্তিগত তথ্য বা অন্য রোগীর তথ্য কখনো দিই না, আর অপ্রাসঙ্গিক প্রশ্নে ভদ্রভাবে কাজে ফিরি।",
        start_at="#features",
        actions=[Action("scroll", "#use-cases")],
    ),
    Scene(
        "call",
        "/",
        "এই বোতামে চাপলেই ব্রাউজারে কল; লাইভ ক্যাপশন আর আমার কাজের চিপ দেখা যায়। চাইলে নিজের Gemini key দিয়েও কল করা যায়, key আগে টেস্ট হয়, পাস করলেই গ্রহণ। মাইকের অনুমতি না পেলে কী করতে হবে, সেটাও বলি।",
        actions=[
            Action("hover", CALL_BUTTON),
            Action("click", "summary:has-text('Gemini API key')"),
            Action("click", CALL_BUTTON),
        ],
    ),
]

PORTAL_SCENES = [
    Scene(
        "login",
        "/login",
        "কল শেষ হলে ক্লিনিকের স্টাফ পোর্টালে লগইন করেন।",
        actions=[
            Action("fill", "input[name=email]|$PORTAL_EMAIL"),
            Action("fill", "input[name=password]|$PORTAL_PASSWORD"),
            Action("click", "button[type=submit]"),
        ],
        fresh_session=True,
    ),
    Scene(
        "portal_overview",
        "/portal",
        "শুরুতেই আজ আর সাত দিনের কল, বুকিংয়ের হার, অফিস টাইমের বাইরের কল, গড় সময় আর খোলা কলব্যাক।",
        needs_login=True,
    ),
    Scene(
        "portal_calls",
        "/portal/calls",
        "কলের তালিকায় তারিখ, রোগী, নম্বর, সময়কাল আর ফলাফল। নাম বা নম্বরে খোঁজা যায়, আর চলমান কল লাইভ দেখায়।",
        actions=[Action("fill", "input[name=q]|তাহমিনা"), Action("press", "input[name=q]|Enter")],
        needs_login=True,
    ),
    Scene(
        "portal_detail",
        "/portal/calls",
        "প্রতিটা কলে যাচাই করা নাম, নম্বর আর পছন্দের সময়; সময়সহ পুরো কথোপকথন আর এক ক্লিকে ইংরেজি অনুবাদ। "
        "প্রতিটা টুল, latency, গোপনীয়তার লগ, সারাংশ, বুকিং আর কলব্যাক এখানেই, আর Reprocess চাপলে আবার বিশ্লেষণ হয়।",
        actions=[
            Action("open_first_call"),
            Action("click", "button:has-text('English')"),
            Action("wheel"),
            Action("wheel"),
            Action("wheel"),
        ],
        needs_login=True,
    ),
    Scene(
        "portal_memory",
        "/portal/calls",
        "একই রোগী আবার কল করলে, নাম আর নম্বর মিলিয়ে আমি আগের কথা মনে রাখি; সময় বদলানো বা বাতিলও করতে পারি।",
        actions=[Action("open_call", "1"), Action("wheel")],
        needs_login=True,
    ),
    Scene(
        "portal_appointments",
        "/portal/appointments",
        "সব appointment ডাক্তার আর দিন অনুযায়ী সাজানো। একই সময়ে দুইজনের বুকিং ডাটাবেসেই আটকানো।",
        needs_login=True,
    ),
    Scene(
        "portal_callbacks",
        "/portal/callbacks",
        "আর যেসব রোগী ডাক্তার বা স্টাফের কল চেয়েছেন, তাদের তালিকা; কাজ শেষ হলে স্টাফ চিহ্ন দেন।",
        needs_login=True,
    ),
    Scene(
        "portal_data_model",
        "/portal/data-model",
        "ডেটার গঠন এখানে: কোন টেবিল কী রাখে, কল থেকে ডাটাবেসে তথ্য কীভাবে যায়; সিঙ্গাপুরের Postgres, row level security দিয়ে সুরক্ষিত।",
        actions=[Action("wheel"), Action("wheel")],
        needs_login=True,
    ),
    Scene(
        "logout",
        "/portal",
        "কাজ শেষে এক ক্লিকে লগআউট।",
        actions=[Action("click", "button:has-text('Sign out') >> visible=true")],
        needs_login=True,
    ),
]

CLOSING_SCENE = Scene(
    "closing",
    "/",
    "নব্বইটারও বেশি টেস্ট আর এগারোটা কথোপকথন পরীক্ষায় পাশ। ByteVoice Bangla, আপনার ক্লিনিকের ফোন, চব্বিশ ঘণ্টা বাংলায়। ধন্যবাদ!",
    start_at="#meet-nila",
    settled=True,
)


def _audio_path(work_dir: Path, scene: Scene) -> Path:
    digest = hashlib.sha1(f"{TTS_MODELS[0]}|{TTS_VOICE}|{scene.narration_bn}".encode()).hexdigest()[:10]
    return work_dir / "audio" / f"{scene.key}-{digest}.wav"


def _wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as audio:
        return audio.getnframes() / audio.getframerate()


def _expected_seconds(text: str) -> float:
    return len(text) / BANGLA_CHARACTERS_PER_SECOND


_exhausted_models: set[str] = set()


def _request_speech(client: genai.Client, text: str, destination: Path) -> None:
    speech_config = types.SpeechConfig(
        voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE))
    )
    response = None
    for model in TTS_MODELS:
        if model in _exhausted_models:
            continue
        try:
            response = client.models.generate_content(
                model=model,
                contents=text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"], speech_config=speech_config
                ),
            )
            break
        except genai_errors.ClientError as error:
            if error.code != QUOTA_EXHAUSTED_STATUS:
                raise
            logger.warning("daily quota reached for %s, switching TTS model", model)
            _exhausted_models.add(model)
    if response is None:
        raise SystemExit("Every TTS model has hit its daily quota")
    audio = response.candidates[0].content.parts[0].inline_data.data
    if audio[:4] == b"RIFF":
        destination.write_bytes(audio)
        return
    with wave.open(str(destination), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(audio)


def _trim_silence(ffmpeg: str, source: Path, destination: Path) -> None:
    edge = f"silenceremove=start_periods=1:start_threshold={SILENCE_THRESHOLD}"
    pauses = (
        f"silenceremove=stop_periods=-1:stop_duration={MAX_PAUSE_SECONDS}"
        f":stop_threshold={SILENCE_THRESHOLD}:stop_silence={KEPT_PAUSE_SECONDS}"
    )
    audio_filter = f"{edge},areverse,{edge},areverse,{pauses}"
    subprocess.run(
        [
            ffmpeg, "-y", "-loglevel", "error", "-i", str(source),
            "-af", audio_filter,
            "-ar", str(SAMPLE_RATE), "-ac", "1", str(destination),
        ],
        check=True,
    )  # fmt: skip


class NarrationCheck(BaseModel):
    transcript: str
    spoken_once: bool
    extra_speech: bool


def _verify_speech(client: genai.Client, text: str, clip: Path) -> bool:
    """Listen to the clip and confirm it says the line exactly once, with nothing added."""
    response = client.models.generate_content(
        model=VERIFY_MODEL,
        contents=[
            types.Part.from_bytes(data=clip.read_bytes(), mime_type="audio/wav"),
            (
                "Transcribe this Bangla audio. Then compare it with the expected line below. spoken_once is true only if "
                "the line is spoken one time (not repeated, fully or partly). extra_speech is true if anything else is "
                f"said, such as instructions or a second reading.\n\nExpected line: {text}"
            ),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json", response_schema=NarrationCheck, temperature=0
        ),
    )
    check = response.parsed if isinstance(response.parsed, NarrationCheck) else None
    if check is None:
        check = NarrationCheck.model_validate_json(response.text or "{}")
    transcript_ratio = len(check.transcript) / max(len(text), 1)
    return check.spoken_once and not check.extra_speech and transcript_ratio <= MAX_TRANSCRIPT_RATIO


def synthesise(client: genai.Client, ffmpeg: str, text: str, destination: Path) -> float:
    """Generate narration, trim silences and retry when the model repeats itself or pads the clip."""
    if destination.exists():
        return _wav_seconds(destination)
    raw = destination.with_suffix(".raw.wav")
    for attempt in range(1, MAX_TTS_ATTEMPTS + 1):
        _request_speech(client, text, raw)
        _trim_silence(ffmpeg, raw, destination)
        seconds = _wav_seconds(destination)
        too_long = seconds > _expected_seconds(text) * MAX_LENGTH_RATIO
        if not too_long and _verify_speech(client, text, destination):
            break
        logger.warning(
            "narration rejected (attempt %d, %.1fs for %d chars), regenerating", attempt, seconds, len(text)
        )
        destination.unlink()
    else:
        raise SystemExit(f"Could not get a clean narration for: {text}")
    raw.unlink(missing_ok=True)
    return _wav_seconds(destination)


async def _perform(page: Page, action: Action, base_url: str) -> None:
    try:
        if action.kind == "scroll":
            await page.evaluate(
                "(selector) => document.querySelector(selector)?.scrollIntoView({behavior: 'smooth', block: 'start'})",
                action.target,
            )
        elif action.kind in ("fill", "press"):
            selector, value = action.target.split("|", 1)
            if value.startswith("$"):
                value = os.environ.get(value[1:], "")
            field = page.locator(selector).first
            if action.kind == "fill":
                await field.click(timeout=4000)
                await field.press_sequentially(value, delay=45)
            else:
                await field.press(value)
                await page.wait_for_load_state("networkidle")
        elif action.kind == "open_call":
            call_link = page.locator("a[href^='/portal/calls/']").nth(int(action.target))
            if await call_link.count():
                await call_link.click()
                await page.wait_for_url("**/portal/calls/*", timeout=15000)
                await page.wait_for_load_state("networkidle")
        elif action.kind == "click":
            await page.locator(action.target).first.click(timeout=4000)
        elif action.kind == "hover":
            await page.locator(action.target).first.hover(timeout=4000)
        elif action.kind == "goto":
            await page.goto(f"{base_url}{action.target}", wait_until="load")
        elif action.kind == "wheel":
            await page.mouse.move(VIEWPORT["width"] / 2, VIEWPORT["height"] / 2)
            await page.mouse.wheel(0, 420)
        elif action.kind == "open_first_call":
            first_call = page.locator("a[href^='/portal/calls/']").first
            if await first_call.count():
                await first_call.click()
                await page.wait_for_url("**/portal/calls/*", timeout=15000)
                await page.wait_for_load_state("networkidle")
    except PlaywrightError:
        logger.warning("scene action skipped: %s %s", action.kind, action.target)


async def _login(page: Page, base_url: str) -> None:
    await page.goto(f"{base_url}/login", wait_until="load")
    await page.fill("input[type=email]", os.environ["PORTAL_EMAIL"])
    await page.fill("input[type=password]", os.environ["PORTAL_PASSWORD"])
    await page.click("button[type=submit]")
    await page.wait_for_url("**/portal**", timeout=20000)


async def record_scene(
    browser: Browser, scene: Scene, base_url: str, seconds: float, work_dir: Path
) -> tuple[Path, float]:
    storage = work_dir / "portal-session.json"
    context = await browser.new_context(
        viewport=VIEWPORT,
        record_video_dir=str(work_dir / "raw"),
        record_video_size=VIEWPORT,
        storage_state=str(storage)
        if scene.needs_login and not scene.fresh_session and storage.exists()
        else None,
        reduced_motion="reduce" if scene.settled else "no-preference",
    )
    await context.add_init_script("localStorage.setItem('bytevoice.language', 'bn')")
    page = await context.new_page()
    opened_at = time.monotonic()
    await page.goto(f"{base_url}{scene.path}", wait_until="load")
    if scene.start_at:
        await page.evaluate(
            "(selector) => document.querySelector(selector)?.scrollIntoView({block: 'start'})", scene.start_at
        )
    await page.wait_for_timeout(1500)
    ready_offset = time.monotonic() - opened_at

    actions = scene.actions
    pause_ms = int(seconds * 1000 / (len(actions) + 1))
    for action in actions:
        quick = action.kind in ("open_first_call", "open_call", "fill", "press")
        await page.wait_for_timeout(600 if quick else pause_ms)
        await _perform(page, action, base_url)
    remaining_ms = int((seconds + TAIL_SECONDS) * 1000 - (time.monotonic() - opened_at - ready_offset) * 1000)
    await page.wait_for_timeout(max(remaining_ms, 0) + 400)
    video_path = Path(await page.video.path())
    await context.close()
    return video_path, ready_offset


def mux(ffmpeg: str, video: Path, audio: Path, start: float, seconds: float, output: Path) -> None:
    subprocess.run(
        [
            ffmpeg, "-y", "-loglevel", "error",
            "-ss", f"{start:.2f}", "-i", str(video),
            "-i", str(audio),
            "-filter_complex", f"[1:a]aresample=48000,apad=pad_dur={TAIL_SECONDS}[voice]",
            "-map", "0:v", "-map", "[voice]",
            "-t", f"{seconds + TAIL_SECONDS:.2f}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-ac", "2",
            str(output),
        ],
        check=True,
    )  # fmt: skip


def concatenate(ffmpeg: str, clips: list[Path], output: Path) -> None:
    listing = output.with_suffix(".txt")
    listing.write_text("".join(f"file '{clip}'\n" for clip in clips))
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(listing),
            "-c",
            "copy",
            str(output),
        ],
        check=True,
    )
    listing.unlink()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:3100")
    parser.add_argument("--output", type=Path, default=Path("../../docs/video/bytevoice-nila.mp4"))
    parser.add_argument("--work-dir", type=Path, default=Path("../../.video-build"))
    arguments = parser.parse_args()

    work_dir = arguments.work_dir.resolve()
    for folder in ("audio", "clips", "raw"):
        (work_dir / folder).mkdir(parents=True, exist_ok=True)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    include_portal = bool(os.environ.get("PORTAL_EMAIL") and os.environ.get("PORTAL_PASSWORD"))
    scenes = LANDING_SCENES + (PORTAL_SCENES if include_portal else []) + [CLOSING_SCENE]

    client = genai.Client()
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    durations: dict[str, float] = {}
    for scene in scenes:
        durations[scene.key] = synthesise(client, ffmpeg, scene.narration_bn, _audio_path(work_dir, scene))
        logger.warning("narration ready: %s (%.1fs)", scene.key, durations[scene.key])
    total = sum(durations.values()) + TAIL_SECONDS * len(scenes)
    logger.warning("planned length: %.0fs", total)
    if total > MAX_VIDEO_SECONDS:
        raise SystemExit(
            f"Planned video is {total:.0f}s, over the {MAX_VIDEO_SECONDS}s limit; shorten the narration"
        )

    clips: list[Path] = []
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            channel="chromium", args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
        )
        if include_portal:
            login_context = await browser.new_context(viewport=VIEWPORT)
            await _login(await login_context.new_page(), arguments.base_url)
            await login_context.storage_state(path=str(work_dir / "portal-session.json"))
            await login_context.close()
        for scene in scenes:
            raw_video, ready_offset = await record_scene(
                browser, scene, arguments.base_url, durations[scene.key], work_dir
            )
            clip = work_dir / "clips" / f"{len(clips):02d}-{scene.key}.mp4"
            mux(ffmpeg, raw_video, _audio_path(work_dir, scene), ready_offset, durations[scene.key], clip)
            clips.append(clip)
            logger.warning("scene recorded: %s", scene.key)
        await browser.close()

    concatenate(ffmpeg, clips, arguments.output.resolve())
    logger.warning("video written: %s (%.0fs)", arguments.output.resolve(), total)


if __name__ == "__main__":
    asyncio.run(main())
