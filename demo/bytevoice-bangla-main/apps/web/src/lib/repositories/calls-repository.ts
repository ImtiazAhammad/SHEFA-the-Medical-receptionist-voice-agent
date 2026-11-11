import type { SupabaseClient } from "@supabase/supabase-js";
import { CALLS_PAGE_SIZE } from "@/constants/portal";
import { dhakaDayKeyToUtcStart } from "@/lib/format";
import { parseRow, parseRows, RepositoryError } from "@/lib/repositories/parse";
import { callMetricRowSchema, callOverviewRowSchema } from "@/schemas/database";
import type { CallMetricRow, CallOverviewRow } from "@/types/database";
import type { CallListFilters, PagedResult } from "@/types/portal";

const BANGLA_DIGIT_PATTERN = /[০-৯]/g;
const DAY_MILLISECONDS = 86_400_000;

function toAsciiDigits(value: string): string {
  return value.replace(BANGLA_DIGIT_PATTERN, (digit) => String(digit.charCodeAt(0) - 0x09e6));
}

function buildSearchFilter(search: string): string | null {
  const cleaned = search.replace(/[,()*%\\:"]/g, " ").trim();
  if (!cleaned) {
    return null;
  }
  const clauses = [`caller_name_bn.ilike.*${cleaned}*`, `caller_name_en.ilike.*${cleaned}*`];
  const digits = toAsciiDigits(cleaned).replace(/\D/g, "");
  if (digits.length >= 3) {
    clauses.push(`caller_phone.ilike.*${digits.replace(/^(880|0)/, "")}*`);
  }
  return clauses.join(",");
}

export async function listCalls(client: SupabaseClient, filters: CallListFilters): Promise<PagedResult<CallOverviewRow>> {
  const from = (filters.page - 1) * CALLS_PAGE_SIZE;
  let query = client
    .from("call_overview")
    .select("*", { count: "exact" })
    .order("started_at", { ascending: false })
    .range(from, from + CALLS_PAGE_SIZE - 1);

  const searchFilter = buildSearchFilter(filters.search);
  if (searchFilter) {
    query = query.or(searchFilter);
  }
  if (filters.status) {
    query = query.eq("status", filters.status);
  }
  if (filters.outcome) {
    query = query.eq("outcome", filters.outcome);
  }
  const dateFrom = filters.dateFrom ? dhakaDayKeyToUtcStart(filters.dateFrom) : null;
  if (dateFrom) {
    query = query.gte("started_at", dateFrom.toISOString());
  }
  const dateTo = filters.dateTo ? dhakaDayKeyToUtcStart(filters.dateTo) : null;
  if (dateTo) {
    query = query.lt("started_at", new Date(dateTo.getTime() + DAY_MILLISECONDS).toISOString());
  }

  const { data, error, count } = await query;
  if (error) {
    throw new RepositoryError("listCalls", error.message);
  }
  return {
    rows: parseRows(callOverviewRowSchema, data, "listCalls"),
    total: count ?? 0,
    page: filters.page,
    pageSize: CALLS_PAGE_SIZE,
  };
}

export async function getCallOverview(client: SupabaseClient, callId: string): Promise<CallOverviewRow | null> {
  const { data, error } = await client.from("call_overview").select("*").eq("id", callId).maybeSingle();
  if (error) {
    throw new RepositoryError("getCallOverview", error.message);
  }
  return parseRow(callOverviewRowSchema, data, "getCallOverview");
}

export async function listRecentCalls(client: SupabaseClient, limit: number): Promise<CallOverviewRow[]> {
  const { data, error } = await client
    .from("call_overview")
    .select("*")
    .order("started_at", { ascending: false })
    .limit(limit);
  if (error) {
    throw new RepositoryError("listRecentCalls", error.message);
  }
  return parseRows(callOverviewRowSchema, data, "listRecentCalls");
}

export async function listCallMetricsSince(client: SupabaseClient, since: Date): Promise<CallMetricRow[]> {
  const { data, error } = await client
    .from("calls")
    .select("id, started_at, duration_s, status, outcome, after_hours")
    .gte("started_at", since.toISOString())
    .order("started_at", { ascending: true })
    .limit(5000);
  if (error) {
    throw new RepositoryError("listCallMetricsSince", error.message);
  }
  return parseRows(callMetricRowSchema, data, "listCallMetricsSince");
}
