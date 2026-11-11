import { ErrorState } from "@/components/portal/states";

export function SupabaseMissing() {
  return (
    <ErrorState
      title="Supabase is not configured"
      body="Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY, then sign in to see portal data."
    />
  );
}
