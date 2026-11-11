import { randomUUID } from "node:crypto";
import { AccessToken, RoomAgentDispatch, RoomConfiguration } from "livekit-server-sdk";
import { NextResponse } from "next/server";
import {
  ROOM_NAME_PREFIX,
  TOKEN_RATE_LIMIT_MAX_REQUESTS,
  TOKEN_RATE_LIMIT_WINDOW_MILLISECONDS,
  TOKEN_TIME_TO_LIVE,
  VISITOR_IDENTITY_PREFIX,
} from "@/constants/call";
import { apiError, readOptionalJson } from "@/lib/api-response";
import { getLiveKitServerConfig, getVisitorKeySecret } from "@/lib/env";
import { createLogger } from "@/lib/logger";
import { clientAddressFromHeaders, createSlidingWindowRateLimiter } from "@/lib/rate-limit";
import { sealVisitorKey, testVisitorKey } from "@/lib/visitor-key";
import { tokenRequestSchema } from "@/schemas/requests";
import type { TokenResponse } from "@/types/api";

const logger = createLogger("api.livekit.token");
const rateLimiter = createSlidingWindowRateLimiter(TOKEN_RATE_LIMIT_MAX_REQUESTS, TOKEN_RATE_LIMIT_WINDOW_MILLISECONDS);

export async function POST(request: Request): Promise<NextResponse> {
  try {
    const clientAddress = clientAddressFromHeaders(request.headers);
    const decision = rateLimiter.consume(clientAddress);
    if (!decision.allowed) {
      logger.warn("Token request rate-limited", { clientAddress });
      return apiError(429, "rate_limited", "Too many call attempts. Please wait a minute and try again.", {
        "Retry-After": String(decision.retryAfterSeconds),
      });
    }

    let body: unknown;
    try {
      body = await readOptionalJson(request);
    } catch {
      return apiError(400, "invalid_request", "Request body must be valid JSON.");
    }
    const parsed = tokenRequestSchema.safeParse(body);
    if (!parsed.success) {
      return apiError(400, "invalid_request", "Unsupported request fields.");
    }

    const config = getLiveKitServerConfig();
    if (!config) {
      logger.error("LiveKit environment is not configured");
      return apiError(503, "livekit_not_configured", "The voice service is not configured right now.");
    }

    const dispatchMetadata: Record<string, string> = { language: parsed.data.language ?? "bn" };
    const visitorKey = parsed.data.geminiApiKey;
    if (visitorKey) {
      const secret = getVisitorKeySecret();
      if (!secret) {
        logger.error("Visitor key sealing secret is not configured");
        return apiError(503, "visitor_key_unavailable", "Own-key calls are not available right now.");
      }
      const keyTest = await testVisitorKey(visitorKey);
      if (!keyTest.ok) {
        logger.info("Call refused: visitor key failed its test", { reason: keyTest.reason });
        return apiError(400, keyTest.reason, "The Gemini API key did not pass its test.");
      }
      dispatchMetadata.sealed_api_key = sealVisitorKey(visitorKey, secret);
    }

    const roomName = `${ROOM_NAME_PREFIX}${randomUUID()}`;
    const identity = `${VISITOR_IDENTITY_PREFIX}${randomUUID()}`;
    const language = dispatchMetadata.language;

    const accessToken = new AccessToken(config.apiKey, config.apiSecret, {
      identity,
      name: "Web visitor",
      ttl: TOKEN_TIME_TO_LIVE,
      attributes: { language },
    });
    accessToken.addGrant({
      room: roomName,
      roomJoin: true,
      canPublish: true,
      canSubscribe: true,
      canPublishData: true,
    });
    accessToken.roomConfig = new RoomConfiguration({
      agents: [new RoomAgentDispatch({ agentName: config.agentName, metadata: JSON.stringify(dispatchMetadata) })],
    });

    const participantToken = await accessToken.toJwt();
    logger.info("Issued call token", { roomName, visitorKey: Boolean(visitorKey) });

    return NextResponse.json<TokenResponse>(
      { serverUrl: config.serverUrl, participantToken, roomName },
      { headers: { "Cache-Control": "no-store" } },
    );
  } catch (error) {
    logger.error("Token generation failed", { error });
    return apiError(500, "token_generation_failed", "Could not start the call. Please try again.");
  }
}
