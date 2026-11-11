import type { Metadata } from "next";
import Link from "next/link";
import { CallsTable } from "@/components/portal/calls-table";
import { PageHeader } from "@/components/portal/page-header";
import { RealtimeRefresh } from "@/components/portal/realtime-refresh";
import { EmptyState, ErrorState } from "@/components/portal/states";
import { SupabaseMissing } from "@/components/portal/supabase-missing";
import { CALL_OUTCOME_LABELS, CALL_OUTCOMES, CALL_STATUS_LABELS, CALL_STATUSES } from "@/constants/portal";
import { createLogger } from "@/lib/logger";
import { listCalls } from "@/lib/repositories/calls-repository";
import { requirePortalContext } from "@/lib/supabase/server";
import { callListQuerySchema } from "@/schemas/requests";
import type { CallOverviewRow } from "@/types/database";
import type { CallListFilters, PagedResult } from "@/types/portal";

export const metadata: Metadata = { title: "Calls" };

const logger = createLogger("portal.calls");

const fieldClass =
  "h-10 rounded-lg border border-line bg-white px-3 text-sm text-ink focus:border-teal focus:outline-none focus:ring-2 focus:ring-teal/25";

function firstValue(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

function toFilters(searchParameters: Record<string, string | string[] | undefined>): CallListFilters {
  const parsed = callListQuerySchema.parse({
    q: firstValue(searchParameters.q),
    status: firstValue(searchParameters.status) || undefined,
    outcome: firstValue(searchParameters.outcome) || undefined,
    from: firstValue(searchParameters.from) || undefined,
    to: firstValue(searchParameters.to) || undefined,
    page: firstValue(searchParameters.page),
  });
  return {
    search: parsed.q?.trim() ?? "",
    status: parsed.status ?? null,
    outcome: parsed.outcome ?? null,
    dateFrom: parsed.from ?? null,
    dateTo: parsed.to ?? null,
    page: parsed.page ?? 1,
  };
}

function pageHref(filters: CallListFilters, page: number): string {
  const parameters = new URLSearchParams();
  if (filters.search) parameters.set("q", filters.search);
  if (filters.status) parameters.set("status", filters.status);
  if (filters.outcome) parameters.set("outcome", filters.outcome);
  if (filters.dateFrom) parameters.set("from", filters.dateFrom);
  if (filters.dateTo) parameters.set("to", filters.dateTo);
  if (page > 1) parameters.set("page", String(page));
  const query = parameters.toString();
  return query ? `/portal/calls?${query}` : "/portal/calls";
}

export default async function CallsPage({ searchParams }: PageProps<"/portal/calls">) {
  const access = await requirePortalContext();
  if (access === "unconfigured") {
    return <SupabaseMissing />;
  }
  const filters = toFilters(await searchParams);
  let result: PagedResult<CallOverviewRow> | null = null;
  try {
    result = await listCalls(access.client, filters);
  } catch (error) {
    logger.error("Calls failed to load", { error });
  }

  const hasFilters = Boolean(filters.search || filters.status || filters.outcome || filters.dateFrom || filters.dateTo);
  const pageCount = result ? Math.max(1, Math.ceil(result.total / result.pageSize)) : 1;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Calls"
        description="Every call Nila handled, newest first. Live calls update automatically."
        actions={<RealtimeRefresh channelName="calls-list" subscriptions={[{ table: "calls" }]} />}
      />

      <form method="get" className="grid gap-3 rounded-2xl border border-line bg-paper p-4 sm:grid-cols-2 lg:grid-cols-[2fr_1fr_1fr_1fr_1fr_auto]">
        <label className="flex flex-col gap-1 text-xs font-medium text-slate">
          Search name or phone
          <input name="q" defaultValue={filters.search} placeholder="তাহমিনা, Tahmina or 01755…" className={fieldClass} />
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-slate">
          Status
          <select name="status" defaultValue={filters.status ?? ""} className={fieldClass}>
            <option value="">Any status</option>
            {CALL_STATUSES.map((status) => (
              <option key={status} value={status}>
                {status === "in_progress" ? "In progress" : CALL_STATUS_LABELS[status].label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-slate">
          Outcome
          <select name="outcome" defaultValue={filters.outcome ?? ""} className={fieldClass}>
            <option value="">Any outcome</option>
            {CALL_OUTCOMES.map((outcome) => (
              <option key={outcome} value={outcome}>
                {CALL_OUTCOME_LABELS[outcome].label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-slate">
          From
          <input type="date" name="from" defaultValue={filters.dateFrom ?? ""} className={fieldClass} />
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-slate">
          To
          <input type="date" name="to" defaultValue={filters.dateTo ?? ""} className={fieldClass} />
        </label>
        <div className="flex items-end gap-2">
          <button type="submit" className="h-10 rounded-lg bg-ink px-4 text-sm font-semibold text-white hover:bg-teal-deep">
            Apply
          </button>
          {hasFilters ? (
            <Link href="/portal/calls" className="inline-flex h-10 items-center rounded-lg px-3 text-sm text-ink-soft hover:text-ink">
              Clear
            </Link>
          ) : null}
        </div>
      </form>

      {!result ? (
        <ErrorState title="Could not load calls" body="Refresh the page to try again." />
      ) : result.rows.length === 0 ? (
        <EmptyState
          title={hasFilters ? "No calls match these filters" : "No calls yet"}
          body={hasFilters ? "Try a wider date range or clear the filters." : "Place a call from the landing page and it will appear here within seconds."}
        />
      ) : (
        <>
          <CallsTable calls={result.rows} />
          <nav aria-label="Pagination" className="flex items-center justify-between text-sm text-ink-soft">
            <span>
              {result.total} call{result.total === 1 ? "" : "s"} · page {result.page} of {pageCount}
            </span>
            <span className="flex gap-2">
              {result.page > 1 ? (
                <Link href={pageHref(filters, result.page - 1)} className="rounded-lg border border-line bg-paper px-3 py-1.5 hover:border-teal">
                  Previous
                </Link>
              ) : null}
              {result.page < pageCount ? (
                <Link href={pageHref(filters, result.page + 1)} className="rounded-lg border border-line bg-paper px-3 py-1.5 hover:border-teal">
                  Next
                </Link>
              ) : null}
            </span>
          </nav>
        </>
      )}
    </div>
  );
}
