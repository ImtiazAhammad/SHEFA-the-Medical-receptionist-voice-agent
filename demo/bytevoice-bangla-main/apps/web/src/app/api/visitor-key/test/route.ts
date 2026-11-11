import { NextResponse } from "next/server";
import { TOKEN_RATE_LIMIT_WINDOW_MILLISECONDS, VISITOR_KEY_TEST_RATE_LIMIT_MAX_REQUESTS } from "@/constants/call";
import { apiError, readOptionalJson } from "@/lib/api-response";
import { createLogger } from "@/lib/logger";
import { clientAddressFromHeaders, createSlidingWindowRateLimiter } from "@/lib/rate-limit";
import { testVisitorKey } from "@/lib/visitor-key";
import { visitorKeyTestSchema } from "@/schemas/requests";
import type { VisitorKeyTestResponse } from "@/types/api";

const logger = createLogger("api.visitor-key.test");
const rateLimiter = createSlidingWindowRateLimiter(
  VISITOR_KEY_TEST_RATE_LIMIT_MAX_REQUESTS,
  TOKEN_RATE_LIMIT_WINDOW_MILLISECONDS,
);

const FAILURE_MESSAGES = {
  invalid_api_key: "Google rejected this key. Check it was copied in full from Google AI Studio.",
  api_key_model_unavailable: "This key cannot use Nila's voice model (gemini-3.8-live).",
  api_key_quota_exhausted: "This key has run out of quota. Try again later or use another key.",
  api_key_test_failed: "The key could not be tested right now. Please try again.",
} as const;

export async function POST(request: Request): Promise<NextResponse> {
  try {
    const decision = rateLimiter.consume(clientAddressFromHeaders(request.headers));
    if (!decision.allowed) {
      return apiError(429, "rate_limited", "Too many key tests. Please wait a minute.", {
        "Retry-After": String(decision.retryAfterSeconds),
      });
    }
    let body: unknown;
    try {
      body = await readOptionalJson(request);
    } catch {
      return apiError(400, "invalid_request", "Request body must be valid JSON.");
    }
    const parsed = visitorKeyTestSchema.safeParse(body);
    if (!parsed.success) {
      return apiError(400, "invalid_api_key", "That does not look like a Gemini API key.");
    }
    const result = await testVisitorKey(parsed.data.apiKey);
    if (!result.ok) {
      logger.info("Visitor key failed its test", { reason: result.reason });
      return apiError(result.reason === "api_key_test_failed" ? 502 : 400, result.reason, FAILURE_MESSAGES[result.reason]);
    }
    return NextResponse.json<VisitorKeyTestResponse>({ status: "valid" }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    logger.error("Visitor key test failed", { error: error instanceof Error ? error.name : "unknown" });
    return apiError(500, "api_key_test_failed", FAILURE_MESSAGES.api_key_test_failed);
  }
}
