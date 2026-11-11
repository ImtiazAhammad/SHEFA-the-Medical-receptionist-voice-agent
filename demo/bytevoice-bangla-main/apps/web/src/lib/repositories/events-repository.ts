import type { SupabaseClient } from "@supabase/supabase-js";
import { parseRows, RepositoryError } from "@/lib/repositories/parse";
import { callEventRowSchema } from "@/schemas/database";
import type { CallEventRow } from "@/types/database";

export async function listCallEvents(client: SupabaseClient, callId: string): Promise<CallEventRow[]> {
  const { data, error } = await client
    .from("call_events")
    .select("id, call_id, occurred_at, event_type, payload")
    .eq("call_id", callId)
    .order("occurred_at", { ascending: true })
    .order("id", { ascending: true });
  if (error) {
    throw new RepositoryError("listCallEvents", error.message);
  }
  return parseRows(callEventRowSchema, data, "listCallEvents");
}
