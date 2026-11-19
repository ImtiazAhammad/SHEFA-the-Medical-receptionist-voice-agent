"""Settings for the collection app. Defaults are safe; `configs/collector.yaml` overrides them."""
# ruff: noqa: E501, N812, TC001, TC003

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

CONSENT_VERSION = "2026-11-v2"
CONSENT_V1 = "2026-11-v1"  # hospital calls only, for SHEFA only

CONSENT_BN = (
    "আমি ১৮ বছরের বেশি বয়সী। আমি জানি আমার কণ্ঠ রেকর্ড করা হবে এবং SHEFA নামের একটি বাণিজ্যিক পণ্যের "
    "বাংলা কথা বোঝার সক্ষমতা শেখাতে ব্যবহার করা হবে। আমি আসল নাম, ফোন নম্বর বা ব্যক্তিগত তথ্য বলব না। "
    "আমার রেকর্ডিং প্রকাশ করা হবে না। যেকোনো সময় ডিলিট কোড দিয়ে আমি রেকর্ডিং মুছে ফেলতে পারব। "
    "তবে যে মডেল একবার শেখানো হয়ে গেছে, তা থেকে আমার কণ্ঠ আলাদা করা যাবে না।"
)
CONSENT_EN = (
    "I am over 18. I know my voice will be recorded and used to teach a commercial product called "
    "SHEFA to understand Bangla. I will not say my real name, phone number or personal details. "
    "My recordings will not be published. I can delete my recordings at any time with my delete "
    "code, but a model that has already been trained cannot un-learn my voice."
)


# Version 2 (2026-11-19): broader purpose (several call topics, any Bangla voice assistant this
# project builds) plus a SEPARATE optional tick for sharing or licensing. DRAFT wording: have a
# lawyer read it before relying on it commercially.
CONSENT_V2_BN = (
    "আমি ১৮ বছরের বেশি বয়সী। আমি জানি আমার কণ্ঠ রেকর্ড করা হবে এবং এই প্রকল্পের বানানো বাংলা ভয়েস "
    "সহকারীদের (যেমন হাসপাতালের SHEFA, এবং ইন্টারনেট বা অন্য সেবার কাস্টমার কেয়ার) বাংলা কথা বোঝার সক্ষমতা "
    "শেখাতে ব্যবহার করা হবে। এগুলো বাণিজ্যিক পণ্য। আমি আসল নাম, ফোন নম্বর বা ব্যক্তিগত তথ্য বলব না। "
    "আমার রেকর্ডিং জনসমক্ষে প্রকাশ করা হবে না। যেকোনো সময় ডিলিট কোড দিয়ে আমি রেকর্ডিং মুছে ফেলতে পারব, "
    "তবে যে মডেল একবার শেখানো হয়ে গেছে তা থেকে আমার কণ্ঠ আলাদা করা যাবে না।"
)
CONSENT_V2_EN = (
    "I am over 18. I know my voice will be recorded and used to teach this project's Bangla voice "
    "assistants (such as SHEFA for hospitals, and customer care for internet or other services) to "
    "understand Bangla. These are commercial products. I will not say my real name, phone number or "
    "personal details. My recordings will not be published. I can delete my recordings at any time with "
    "my delete code, but a model that has already been trained cannot un-learn my voice."
)
SHARE_BN = (
    "ঐচ্ছিক: আমি রাজি যে আমার রেকর্ডিং ও তার লেখা অন্য প্রতিষ্ঠানের সাথে শেয়ার বা তাদের কাছে লাইসেন্স "
    "(বিক্রি) করা যাবে, তাদের নিজেদের বাংলা ভয়েস প্রযুক্তি বানাতে। আমার নাম বা যোগাযোগের তথ্য দেওয়া হবে না।"
)
SHARE_EN = (
    "Optional: I agree that my recordings and their transcripts may be shared with or licensed (sold) "
    "to other organisations to build their own Bangla voice technology. My name or contact details "
    "will not be given."
)


class CollectorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_dir: Path = Path("data/collector")
    host: str = "127.0.0.1"
    port: int = 8100
    private_port: int = 8101  # admin and review, never put on the public tunnel
    consent_version: str = CONSENT_VERSION
    max_clip_bytes: int = 700_000
    min_clip_s: float = 0.6
    max_clip_s: float = 21.0  # open turns allow 20 s; each node carries its own cap
    min_speech_ratio: float = 0.08
    max_clip_fraction: float = 0.2  # more than this many clipped samples is unusable
    clips_per_contributor_per_day: int = 400
    clips_per_ip_per_hour: int = 1500  # mobile carriers share addresses, so this is generous
    starts_per_ip_per_hour: int = 120
    min_free_disk_mb: int = 1500  # below this the app stops taking uploads
    group_goal_minutes: int = 600
    trust_forwarded_for: bool = True  # behind a tunnel the real address is in a header
    allowed_origins: list[str] = Field(default_factory=list)  # a static shell on another host
    turnstile_site_key: str = ""
    turnstile_secret_env: str = "SHEFA_TURNSTILE_SECRET"
    reviewers_on_public: bool = False  # `serve --with-review` turns this on for a review session
    audio_url_ttl_s: int = 600
    human_voice_share: float = (
        0.5  # share of calls that use a recorded human desk voice, when one exists
    )
    nudge_after_clips: int = 40  # suggest passing the phone on after this many clips by one person
    free_talk_share: float = 0.25  # share of calls with no hint per turn (people talk freely)
    noisy_goal_minutes: int = 120  # group goal for recordings made with background noise
    auto_draft: bool = True  # `serve` drafts every new clip in the background
    draft_device: str = ""  # "" = the speech model's own setting (GPU, CPU fallback); or "cpu"
    session_hours: int = 12  # a staff sign-in lasts this long
    password_iterations: int = 600_000  # PBKDF2 rounds; tests lower it
    test_fraction: float = 0.10
    dev_fraction: float = 0.05
    seed_fraction: float = 0.05  # known-answer clips mixed into a reviewer's queue
    speaker_clip_cap_share: float = 0.05  # one speaker may be at most this share of a release

    @property
    def db_path(self) -> Path:
        return self.data_dir / "collector.db"

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def prompts_dir(self) -> Path:
        return self.data_dir / "prompts"


def load_config(path: str | Path = "configs/collector.yaml") -> CollectorConfig:
    file = Path(path)
    raw = yaml.safe_load(file.read_text(encoding="utf-8")) if file.exists() else {}
    return CollectorConfig(**(raw or {}))
