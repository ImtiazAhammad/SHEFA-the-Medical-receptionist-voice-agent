export type ApiErrorCode =
  | "invalid_request"
  | "rate_limited"
  | "livekit_not_configured"
  | "token_generation_failed"
  | "unauthorized"
  | "agent_api_not_configured"
  | "agent_api_failed"
  | "supabase_not_configured"
  | "lead_insert_failed"
  | "invalid_api_key"
  | "api_key_model_unavailable"
  | "api_key_quota_exhausted"
  | "api_key_test_failed"
  | "visitor_key_unavailable";

export interface ApiErrorResponse {
  error: {
    code: ApiErrorCode;
    message: string;
  };
}

export interface TokenResponse {
  serverUrl: string;
  participantToken: string;
  roomName: string;
}

export interface ReprocessResponse {
  status: "queued" | "completed";
  detail?: string;
}

export interface LeadResponse {
  status: "received";
}

export type FormStatus = "idle" | "submitting" | "success" | "error";

export type VisitorKeyTestFailure = "invalid_api_key" | "api_key_model_unavailable" | "api_key_quota_exhausted" | "api_key_test_failed";

export type VisitorKeyTestResult = { ok: true } | { ok: false; reason: VisitorKeyTestFailure };

export interface VisitorKeyTestResponse {
  status: "valid";
}
