export const LIVEKIT_TOKEN_ENDPOINT = "/api/livekit/token";
export const DEFAULT_AGENT_NAME = "bytevoice-bn";

export const ROOM_NAME_PREFIX = "call-";
export const VISITOR_IDENTITY_PREFIX = "visitor-";
export const TOKEN_TIME_TO_LIVE = "10m";

export const TOKEN_RATE_LIMIT_MAX_REQUESTS = 5;
export const TOKEN_RATE_LIMIT_WINDOW_MILLISECONDS = 60_000;

export const MAX_CALL_SECONDS = 300;
export const CALL_CAP_TOLERANCE_SECONDS = 12;
export const AGENT_JOIN_TIMEOUT_MILLISECONDS = 20_000;

export const DATA_TOPIC_TOOL = "bytevoice.tool";
export const DATA_TOPIC_CALL = "bytevoice.call";
export const TRANSCRIPTION_TOPIC = "lk.transcription";

export const MAX_TOOL_CHIPS = 4;
export const TOOL_CHIP_LIFETIME_MILLISECONDS = 9_000;

export const VISITOR_KEY_TEST_ENDPOINT = "/api/visitor-key/test";
export const VISITOR_KEY_STORAGE_KEY = "bytevoice.visitor-gemini-key";
export const VISITOR_KEY_DERIVATION_LABEL = "bytevoice-visitor-key-v1";
export const VISITOR_KEY_PATTERN = /^[A-Za-z0-9_-]{30,80}$/;
export const VISITOR_KEY_TEST_CACHE_MILLISECONDS = 10 * 60_000;
export const VISITOR_KEY_TEST_TIMEOUT_MILLISECONDS = 8_000;
export const VISITOR_KEY_TEST_RATE_LIMIT_MAX_REQUESTS = 6;
export const GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta";
export const GEMINI_VOICE_MODEL = "gemini-3.8-live";
export const GEMINI_TEXT_MODEL = "gemini-2.5-flash";
