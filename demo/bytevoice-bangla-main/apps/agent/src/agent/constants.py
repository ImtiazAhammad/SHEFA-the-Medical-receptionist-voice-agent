from enum import StrEnum
from zoneinfo import ZoneInfo

CLINIC_TIMEZONE = ZoneInfo("Asia/Dhaka")
LOGGER_NAME = "bytevoice.agent"
AGENT_DISPLAY_NAME = "Nila"

BANGLADESH_LANGUAGE_CODE = "bn-BD"
RECOGNITION_LANGUAGE_CODES = ["bn-BD", "en-US"]

FADE_OUT_SECONDS = 0.025
TRAILING_SILENCE_SECONDS = 0.15


class VoiceEngine(StrEnum):
    GEMINI_LIVE = "gemini_live"
    GEMINI_PIPELINE = "gemini_pipeline"


BANGLADESHI_ACCENT_INSTRUCTIONS = (
    "Speak as a warm, polite young female receptionist from Dhaka, Bangladesh. Use natural everyday "
    "Bangladeshi Bangla with a standard Dhaka accent, never a Kolkata or West Bengal accent. "
    "Calm, friendly, clear, at a natural phone-call pace. Pronounce English loanwords the way Bangladeshi "
    "people do. Read phone digits slowly, one by one."
)

SPEECH_PHRASE_HINTS = [
    "ওয়ান স্মাইল ডেন্টাল",
    "One Smile",
    "মুশফিকুর রুহান",
    "রাকিব হাসান",
    "নুসরাত জাহান",
    "appointment",
    "scaling",
    "root canal",
    "filling",
    "braces",
    "X-ray",
    "উত্তরা",
    "whitening",
]


BANGLA_WEEKDAY_NAMES = ("সোমবার", "মঙ্গলবার", "বুধবার", "বৃহস্পতিবার", "শুক্রবার", "শনিবার", "রবিবার")
BANGLA_DIGIT_TRANSLATION = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")

ACTIVE_APPOINTMENT_STATUSES = ("booked", "rescheduled")
SLOT_STEP_MINUTES = 30
MINIMUM_BOOKING_LEAD_MINUTES = 30
MAX_SLOT_OPTIONS = 3
AVAILABILITY_SEARCH_DAYS = 14

TOOL_DATA_TOPIC = "bytevoice.tool"
CALL_DATA_TOPIC = "bytevoice.call"

TOOL_CHIP_LABELS: dict[str, tuple[str, str, str, str]] = {
    "check_phone_number": ("নম্বর যাচাই করছি…", "Checking the number…", "নম্বর ঠিক আছে ✓", "Number verified ✓"),
    "get_clinic_info": ("তথ্য দেখছি…", "Looking up clinic info…", "তথ্য পাওয়া গেছে ✓", "Info found ✓"),
    "check_availability": (
        "ডাক্তারের সময় দেখছি…",
        "Checking the doctor's schedule…",
        "খালি সময় পাওয়া গেছে ✓",
        "Free slots found ✓",
    ),
    "book_appointment": (
        "অ্যাপয়েন্টমেন্ট বুক করছি…",
        "Booking the appointment…",
        "অ্যাপয়েন্টমেন্ট বুক হয়েছে ✓",
        "Appointment booked ✓",
    ),
    "find_appointments": (
        "অ্যাপয়েন্টমেন্ট খুঁজছি…",
        "Finding your appointments…",
        "অ্যাপয়েন্টমেন্ট পাওয়া গেছে ✓",
        "Appointments found ✓",
    ),
    "reschedule_appointment": ("সময় বদলাচ্ছি…", "Rescheduling…", "সময় বদলানো হয়েছে ✓", "Rescheduled ✓"),
    "cancel_appointment": ("বাতিল করছি…", "Cancelling…", "অ্যাপয়েন্টমেন্ট বাতিল ✓", "Cancelled ✓"),
    "recall_caller_history": (
        "আগের কলের তথ্য দেখছি…",
        "Checking previous calls…",
        "আগের তথ্য পাওয়া গেছে ✓",
        "History found ✓",
    ),
    "request_human_callback": (
        "কলব্যাক নিচ্ছি…",
        "Requesting a callback…",
        "কলব্যাক রিকোয়েস্ট নেওয়া হয়েছে ✓",
        "Callback requested ✓",
    ),
}
TOOL_CHIP_ERROR_LABELS = ("আবার চেষ্টা করছি…", "Needs another try…")

SILENCE_REPROMPT_INSTRUCTION = "রোগী কিছুক্ষণ ধরে চুপ। নরমভাবে জিজ্ঞেস করো: 'হ্যালো, আপনি কি আমাকে শুনতে পাচ্ছেন?'"
SILENCE_GOODBYE_INSTRUCTION = (
    "রোগী এখনো চুপ। ভদ্রভাবে বলো লাইনে কাউকে পাওয়া যাচ্ছে না, প্রয়োজন হলে আবার কল করতে বলো, ধন্যবাদ দিয়ে বিদায় নাও।"
)
CALL_LIMIT_INSTRUCTION = (
    "কলের নির্ধারিত সময় শেষ। এ পর্যন্ত যা ঠিক হয়েছে এক বাক্যে বলো, প্রয়োজনে আবার কল করতে বলো এবং বিদায় নাও।"
)
SYSTEM_UNAVAILABLE_MESSAGE = (
    "এই মুহূর্তে বুকিং সিস্টেমে সমস্যা হচ্ছে। রোগীর কাছে দুঃখ প্রকাশ করো, কিছু বানিয়ে বলবে না, "
    "এবং নাম ও নম্বর নিয়ে স্টাফের কলব্যাক অফার করো বা পরে কল করতে বলো।"
)

CALLER_HISTORY_CALL_LIMIT = 3

ENGLISH_REPLY_HINT = "The caller is speaking English. Reply in English only."

VISITOR_KEY_DERIVATION_LABEL = "bytevoice-visitor-key-v1"
