import Link from "next/link";
import { CallsTable } from "@/components/portal/calls-table";
import { DailyCallsChart } from "@/components/portal/daily-calls-chart";
import { PageHeader } from "@/components/portal/page-header";
import { RealtimeRefresh } from "@/components/portal/realtime-refresh";
import { EmptyState, ErrorState, Panel } from "@/components/portal/states";
import { SupabaseMissing } from "@/components/portal/supabase-missing";
import { OVERVIEW_WINDOW_DAYS } from "@/constants/portal";
import { formatDuration, startOfDhakaDay } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { computeOverviewMetrics } from "@/lib/metrics";
import { listCallMetricsSince, listRecentCalls } from "@/lib/repositories/calls-repository";
import { countOpenCallbackRequests } from "@/lib/repositories/callbacks-repository";
import { requirePortalContext, type AuthenticatedContext } from "@/lib/supabase/server";
import type { CallOverviewRow } from "@/types/database";
import type { OverviewMetrics } from "@/types/portal";

const logger = createLogger("portal.overview");
const DAY_MILLISECONDS = 86_400_000;
const RECENT_CALLS_LIMIT = 6;

interface OverviewData {
  metrics: OverviewMetrics;
  recentCalls: CallOverviewRow[];
}

async function loadOverview(authenticated: AuthenticatedContext): Promise<OverviewData | "error"> {
  try {
    const now = new Date();
    const since = new Date(startOfDhakaDay(now).getTime() - (OVERVIEW_WINDOW_DAYS - 1) * DAY_MILLISECONDS);
    const [calls, openCallbacks, recentCalls] = await Promise.all([
      listCallMetricsSince(authenticated.client, since),
      countOpenCallbackRequests(authenticated.client),
      listRecentCalls(authenticated.client, RECENT_CALLS_LIMIT),
    ]);
    return { metrics: computeOverviewMetrics(calls, openCallbacks, now, OVERVIEW_WINDOW_DAYS), recentCalls };
  } catch (error) {
    logger.error("Overview failed to load", { error });
    return "error";
  }
}

function Metric({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className="bg-paper px-5 py-4">
      <dt className="text-sm text-slate">{label}</dt>
      <dd className="mt-1 text-[1.75rem] font-bold tabular-nums leading-tight text-ink">{value}</dd>
      {detail ? <dd className="mt-0.5 text-xs text-slate">{detail}</dd> : null}
    </div>
  );
}

export default async function OverviewPage() {
  const access = await requirePortalContext();
  const data = access === "unconfigured" ? "unconfigured" : await loadOverview(access);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Overview"
        description={`How Nila handled calls over the last ${OVERVIEW_WINDOW_DAYS} days.`}
        actions={<RealtimeRefresh channelName="overview-calls" subscriptions={[{ table: "calls" }]} />}
      />
      {data === "unconfigured" ? <SupabaseMissing /> : null}
      {data === "error" ? <ErrorState title="Could not load the overview" body="Refresh the page to try again." /> : null}
      {typeof data === "object" ? (
        <>
          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-2xl border border-line bg-line md:grid-cols-3 xl:grid-cols-6">
            <Metric label="Calls today" value={String(data.metrics.callsToday)} detail={data.metrics.liveCalls ? `${data.metrics.liveCalls} live now` : undefined} />
            <Metric label={`Calls, ${OVERVIEW_WINDOW_DAYS} days`} value={String(data.metrics.callsInWindow)} />
            <Metric label="Booked" value={data.metrics.bookedPercent === null ? "—" : `${data.metrics.bookedPercent}%`} detail="of finished calls" />
            <Metric label="After hours" value={data.metrics.afterHoursPercent === null ? "—" : `${data.metrics.afterHoursPercent}%`} detail="outside 10:00–21:00 or Friday" />
            <Metric label="Average duration" value={formatDuration(data.metrics.averageDurationSeconds)} detail="minutes:seconds" />
            <Metric label="Open callbacks" value={String(data.metrics.openCallbacks)} detail="waiting for staff" />
          </dl>
          <div className="grid gap-6 xl:grid-cols-[1fr_1.6fr]">
            <Panel title="Calls per day">
              <DailyCallsChart days={data.metrics.daily} />
            </Panel>
            <Panel
              title="Latest calls"
              actions={
                <Link href="/portal/calls" className="text-sm font-medium text-teal-deep hover:underline">
                  All calls
                </Link>
              }
            >
              {data.recentCalls.length ? (
                <div className="-m-5">
                  <CallsTable calls={data.recentCalls} compact />
                </div>
              ) : (
                <EmptyState title="No calls yet" body="Place a call from the landing page and it will appear here within seconds." />
              )}
            </Panel>
          </div>
        </>
      ) : null}
    </div>
  );
}
