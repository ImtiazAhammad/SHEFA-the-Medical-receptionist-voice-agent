import type { SupabaseClient } from "@supabase/supabase-js";
import { CALLBACKS_LIMIT } from "@/constants/portal";
import { parseRows, RepositoryError } from "@/lib/repositories/parse";
import { callbackRequestRowSchema } from "@/schemas/database";
import type { CallbackRequestRow } from "@/types/database";

const CALLBACK_SELECT =
  "id, call_id, reason, priority, status, created_at, resolved_at, patients(full_name_bn, full_name_en, phone_e164)";

export async function listCallbackRequests(client: SupabaseClient): Promise<CallbackRequestRow[]> {
  const { data, error } = await client
    .from("callback_requests")
    .select(CALLBACK_SELECT)
    .order("created_at", { ascending: false })
    .limit(CALLBACKS_LIMIT);
  if (error) {
    throw new RepositoryError("listCallbackRequests", error.message);
  }
  return parseRows(callbackRequestRowSchema, data, "listCallbackRequests");
}

export async function listCallbackRequestsForCall(client: SupabaseClient, callId: string): Promise<CallbackRequestRow[]> {
  const { data, error } = await client
    .from("callback_requests")
    .select(CALLBACK_SELECT)
    .eq("call_id", callId)
    .order("created_at", { ascending: true });
  if (error) {
    throw new RepositoryError("listCallbackRequestsForCall", error.message);
  }
  return parseRows(callbackRequestRowSchema, data, "listCallbackRequestsForCall");
}

export async function countOpenCallbackRequests(client: SupabaseClient): Promise<number> {
  const { count, error } = await client
    .from("callback_requests")
    .select("id", { count: "exact", head: true })
    .neq("status", "done");
  if (error) {
    throw new RepositoryError("countOpenCallbackRequests", error.message);
  }
  return count ?? 0;
}

export async function markCallbackRequestDone(client: SupabaseClient, callbackId: string, resolvedAt: Date): Promise<void> {
  const { error } = await client
    .from("callback_requests")
    .update({ status: "done", resolved_at: resolvedAt.toISOString() })
    .eq("id", callbackId);
  if (error) {
    throw new RepositoryError("markCallbackRequestDone", error.message);
  }
}
