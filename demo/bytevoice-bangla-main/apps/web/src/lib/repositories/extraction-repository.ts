import type { SupabaseClient } from "@supabase/supabase-js";
import { parseRow, RepositoryError } from "@/lib/repositories/parse";
import { callExtractionRowSchema } from "@/schemas/database";
import type { CallExtractionRow } from "@/types/database";

export async function getCallExtraction(client: SupabaseClient, callId: string): Promise<CallExtractionRow | null> {
  const { data, error } = await client.from("call_extractions").select("*").eq("call_id", callId).maybeSingle();
  if (error) {
    throw new RepositoryError("getCallExtraction", error.message);
  }
  return parseRow(callExtractionRowSchema, data, "getCallExtraction");
}
