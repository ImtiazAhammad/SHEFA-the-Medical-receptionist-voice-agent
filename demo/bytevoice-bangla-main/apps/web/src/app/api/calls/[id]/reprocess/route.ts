import { NextResponse } from "next/server";
import { apiError } from "@/lib/api-response";
import { getAgentApiConfig } from "@/lib/env";
import { createLogger } from "@/lib/logger";
import { getAuthenticatedContext } from "@/lib/supabase/server";
import { callIdParamSchema } from "@/schemas/requests";
import type { ReprocessResponse } from "@/types/api";

const logger = createLogger("api.calls.reprocess");
const AGENT_REQUEST_TIMEOUT_MILLISECONDS = 60_000;

export async function POST(_request: Request, context: RouteContext<"/api/calls/[id]/reprocess">): Promise<NextResponse> {
  try {
    const { id } = await context.params;
    const parsedId = callIdParamSchema.safeParse(id);
    if (!parsedId.success) {
      return apiError(400, "invalid_request", "Call id must be a UUID.");
    }

    const authenticated = await getAuthenticatedContext();
    if (!authenticated) {
      return apiError(401, "unauthorized", "Sign in to reprocess calls.");
    }

    const agentApi = getAgentApiConfig();
    if (!agentApi) {
      logger.error("Agent API environment is not configured");
      return apiError(503, "agent_api_not_configured", "The processing service is not configured.");
    }

    const upstream = await fetch(`${agentApi.baseUrl}/calls/${parsedId.data}/reprocess`, {
      method: "POST",
      headers: { Authorization: `Bearer ${agentApi.internalToken}`, "Content-Type": "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(AGENT_REQUEST_TIMEOUT_MILLISECONDS),
    });

    if (!upstream.ok) {
      const detail = (await upstream.text()).slice(0, 300);
      logger.warn("Agent reprocess request failed", { callId: parsedId.data, status: upstream.status, detail });
      return apiError(502, "agent_api_failed", `The processing service answered with status ${upstream.status}.`);
    }

    logger.info("Reprocess requested", { callId: parsedId.data, userId: authenticated.user.id });
    return NextResponse.json<ReprocessResponse>({ status: upstream.status === 202 ? "queued" : "completed" });
  } catch (error) {
    logger.error("Reprocess request errored", { error });
    return apiError(502, "agent_api_failed", "Could not reach the processing service.");
  }
}
