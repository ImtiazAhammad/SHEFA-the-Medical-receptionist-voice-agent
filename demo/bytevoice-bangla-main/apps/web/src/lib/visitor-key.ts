import { createCipheriv, createHash, randomBytes } from "node:crypto";
import {
  GEMINI_API_BASE_URL,
  GEMINI_TEXT_MODEL,
  GEMINI_VOICE_MODEL,
  VISITOR_KEY_DERIVATION_LABEL,
  VISITOR_KEY_TEST_CACHE_MILLISECONDS,
  VISITOR_KEY_TEST_TIMEOUT_MILLISECONDS,
} from "@/constants/call";
import { createLogger } from "@/lib/logger";
import type { VisitorKeyTestFailure, VisitorKeyTestResult } from "@/types/api";

const logger = createLogger("visitor-key");
const NONCE_LENGTH = 12;
const testedKeys = new Map<string, { result: VisitorKeyTestResult; expiresAt: number }>();

function fingerprint(apiKey: string): string {
  return createHash("sha256").update(apiKey).digest("hex");
}

function failureFromStatus(status: number): VisitorKeyTestFailure {
  if (status === 429) {
    return "api_key_quota_exhausted";
  }
  if (status === 404) {
    return "api_key_model_unavailable";
  }
  if (status === 400 || status === 401 || status === 403) {
    return "invalid_api_key";
  }
  return "api_key_test_failed";
}

async function callGemini(path: string, apiKey: string, init: RequestInit = {}): Promise<number> {
  const response = await fetch(`${GEMINI_API_BASE_URL}/${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", "x-goog-api-key": apiKey, ...init.headers },
    signal: AbortSignal.timeout(VISITOR_KEY_TEST_TIMEOUT_MILLISECONDS),
    cache: "no-store",
  });
  return response.status;
}

async function runKeyTest(apiKey: string): Promise<VisitorKeyTestResult> {
  const voiceModelStatus = await callGemini(`models/${GEMINI_VOICE_MODEL}`, apiKey);
  if (voiceModelStatus !== 200) {
    return { ok: false, reason: failureFromStatus(voiceModelStatus) };
  }
  const generationStatus = await callGemini(`models/${GEMINI_TEXT_MODEL}:generateContent`, apiKey, {
    method: "POST",
    body: JSON.stringify({
      contents: [{ parts: [{ text: "Reply with the single word: ok" }] }],
      generationConfig: { maxOutputTokens: 1, temperature: 0 },
    }),
  });
  return generationStatus === 200 ? { ok: true } : { ok: false, reason: failureFromStatus(generationStatus) };
}

/** Proves the key can reach Nila's voice model and generate text before any call uses it. */
export async function testVisitorKey(apiKey: string): Promise<VisitorKeyTestResult> {
  const cacheKey = fingerprint(apiKey);
  const cached = testedKeys.get(cacheKey);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.result;
  }
  try {
    const result = await runKeyTest(apiKey);
    testedKeys.set(cacheKey, { result, expiresAt: Date.now() + VISITOR_KEY_TEST_CACHE_MILLISECONDS });
    return result;
  } catch (error) {
    logger.warn("Visitor key test could not reach Gemini", { error: error instanceof Error ? error.name : "unknown" });
    return { ok: false, reason: "api_key_test_failed" };
  }
}

export function sealVisitorKey(apiKey: string, secret: string): string {
  const sealingKey = createHash("sha256").update(`${VISITOR_KEY_DERIVATION_LABEL}:${secret}`).digest();
  const nonce = randomBytes(NONCE_LENGTH);
  const cipher = createCipheriv("aes-256-gcm", sealingKey, nonce);
  const ciphertext = Buffer.concat([cipher.update(apiKey, "utf8"), cipher.final()]);
  return Buffer.concat([nonce, ciphertext, cipher.getAuthTag()]).toString("base64url");
}
