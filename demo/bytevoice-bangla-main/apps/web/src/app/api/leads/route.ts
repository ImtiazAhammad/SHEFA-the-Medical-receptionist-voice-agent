import { NextResponse } from "next/server";
import { apiError } from "@/lib/api-response";
import { createLogger } from "@/lib/logger";
import { clientAddressFromHeaders, createSlidingWindowRateLimiter } from "@/lib/rate-limit";
import { insertLead } from "@/lib/repositories/leads-repository";
import { createSupabaseAnonymousClient } from "@/lib/supabase/anonymous";
import { leadRequestSchema } from "@/schemas/requests";
import type { LeadResponse } from "@/types/api";

const logger = createLogger("api.leads");
const LEAD_RATE_LIMIT_MAX_REQUESTS = 5;
const LEAD_RATE_LIMIT_WINDOW_MILLISECONDS = 10 * 60_000;
const rateLimiter = createSlidingWindowRateLimiter(LEAD_RATE_LIMIT_MAX_REQUESTS, LEAD_RATE_LIMIT_WINDOW_MILLISECONDS);

function emptyToNull(value: string): string | null {
  return value.trim() ? value.trim() : null;
}

export async function POST(request: Request): Promise<NextResponse> {
  try {
    const decision = rateLimiter.consume(clientAddressFromHeaders(request.headers));
    if (!decision.allowed) {
      return apiError(429, "rate_limited", "Too many requests. Please try again later.", {
        "Retry-After": String(decision.retryAfterSeconds),
      });
    }

    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return apiError(400, "invalid_request", "Request body must be valid JSON.");
    }
    const parsed = leadRequestSchema.safeParse(body);
    if (!parsed.success) {
      return apiError(400, "invalid_request", "Please check the form fields.");
    }
    if (!parsed.data.phone && !parsed.data.email) {
      return apiError(400, "invalid_request", "Add a phone number or an email address.");
    }

    const client = createSupabaseAnonymousClient();
    if (!client) {
      return apiError(503, "supabase_not_configured", "The form is not connected right now.");
    }

    await insertLead(client, {
      contact_name: parsed.data.contactName,
      organisation: emptyToNull(parsed.data.organisation),
      phone: emptyToNull(parsed.data.phone),
      email: emptyToNull(parsed.data.email),
      message: emptyToNull(parsed.data.message),
    });
    return NextResponse.json<LeadResponse>({ status: "received" }, { status: 201 });
  } catch (error) {
    logger.error("Lead insert failed", { error });
    return apiError(500, "lead_insert_failed", "Could not save your request. Please try again.");
  }
}
