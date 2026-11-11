import type { SupabaseClient } from "@supabase/supabase-js";
import { parseRows, RepositoryError } from "@/lib/repositories/parse";
import { transcriptTurnRowSchema } from "@/schemas/database";
import type { TranscriptTurnRow } from "@/types/database";

export async function listTranscriptTurns(client: SupabaseClient, callId: string): Promise<TranscriptTurnRow[]> {
  const { data, error } = await client
    .from("transcript_turns")
    .select("id, call_id, seq, speaker, text_bn, text_en, offset_ms, interrupted, created_at")
    .eq("call_id", callId)
    .order("seq", { ascending: true });
  if (error) {
    throw new RepositoryError("listTranscriptTurns", error.message);
  }
  return parseRows(transcriptTurnRowSchema, data, "listTranscriptTurns");
}
