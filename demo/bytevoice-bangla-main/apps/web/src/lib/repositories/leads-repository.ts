import type { SupabaseClient } from "@supabase/supabase-js";
import { RepositoryError } from "@/lib/repositories/parse";
import type { LeadInsert } from "@/types/database";

export async function insertLead(client: SupabaseClient, lead: LeadInsert): Promise<void> {
  const { error } = await client.from("leads").insert(lead);
  if (error) {
    throw new RepositoryError("insertLead", error.message);
  }
}
