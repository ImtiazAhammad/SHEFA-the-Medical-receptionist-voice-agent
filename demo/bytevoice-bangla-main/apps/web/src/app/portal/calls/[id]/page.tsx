import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { AppointmentLine } from "@/components/portal/appointment-line";
import { Badge } from "@/components/portal/badge";
import { CallStatusBadges } from "@/components/portal/call-badges";
import { EventsTimeline } from "@/components/portal/events-timeline";
import { ExtractedFields } from "@/components/portal/extracted-fields";
import { LatencyStats } from "@/components/portal/latency-stats";
import { RealtimeRefresh } from "@/components/portal/realtime-refresh";
import { ReprocessButton } from "@/components/portal/reprocess-button";
import { ResolveCallbackButton } from "@/components/portal/resolve-callback-button";
import { ErrorState, Panel } from "@/components/portal/states";
import { SupabaseMissing } from "@/components/portal/supabase-missing";
import { TranscriptView } from "@/components/portal/transcript-view";
import { CALLBACK_PRIORITY_LABELS, CALLBACK_STATUS_LABELS } from "@/constants/portal";
import { formatDhakaDateTime, formatDuration, formatPhone } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { summarizeLatency } from "@/lib/metrics";
import { listAppointmentsForCall } from "@/lib/repositories/appointments-repository";
import { listCallbackRequestsForCall } from "@/lib/repositories/callbacks-repository";
import { getCallOverview } from "@/lib/repositories/calls-repository";
import { listCallEvents } from "@/lib/repositories/events-repository";
import { getCallExtraction } from "@/lib/repositories/extraction-repository";
import { listTranscriptTurns } from "@/lib/repositories/transcript-repository";
import { requirePortalContext, type AuthenticatedContext } from "@/lib/supabase/server";
import { callIdParamSchema } from "@/schemas/requests";

export const metadata: Metadata = { title: "Call detail" };

const logger = createLogger("portal.call-detail");

async function loadCall(access: AuthenticatedContext, callId: string) {
  const [overview, turns, extraction, events, appointments, callbacks] = await Promise.all([
    getCallOverview(access.client, callId),
    listTranscriptTurns(access.client, callId),
    getCallExtraction(access.client, callId),
    listCallEvents(access.client, callId),
    listAppointmentsForCall(access.client, callId),
    listCallbackRequestsForCall(access.client, callId),
  ]);
  return { overview, turns, extraction, events, appointments, callbacks };
}

export default async function CallDetailPage({ params }: PageProps<"/portal/calls/[id]">) {
  const { id } = await params;
  const parsedId = callIdParamSchema.safeParse(id);
  if (!parsedId.success) {
    notFound();
  }
  const access = await requirePortalContext();
  if (access === "unconfigured") {
    return <SupabaseMissing />;
  }

  let data: Awaited<ReturnType<typeof loadCall>> | null = null;
  try {
    data = await loadCall(access, parsedId.data);
  } catch (error) {
    logger.error("Call detail failed to load", { error, callId: parsedId.data });
  }
  if (!data) {
    return <ErrorState title="Could not load this call" body="Refresh the page to try again." />;
  }
  if (!data.overview) {
    notFound();
  }

  const { overview, turns, extraction, events, appointments, callbacks } = data;
  const isLive = overview.status === "in_progress";
  const callerName = overview.caller_name_bn ?? overview.caller_name_en;
  const latency = summarizeLatency(events);

  return (
    <div className="flex flex-col gap-6">
      <Link href="/portal/calls" className="text-sm font-medium text-teal-deep hover:underline">
        ← All calls
      </Link>

      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-line pb-5">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="text-2xl font-bold tracking-tight text-ink sm:text-[1.75rem]" lang="bn">
              {callerName ?? "Unknown caller"}
            </h1>
            <CallStatusBadges status={overview.status} outcome={overview.outcome} />
            {overview.after_hours ? <Badge tone="violet">After hours</Badge> : null}
          </div>
          <dl className="mt-2 flex flex-wrap gap-x-6 gap-y-1 text-sm text-ink-soft">
            <div className="flex gap-1.5">
              <dt className="text-slate">Phone</dt>
              <dd className="tabular-nums">{formatPhone(overview.caller_phone)}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="text-slate">Started</dt>
              <dd>{formatDhakaDateTime(overview.started_at)}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="text-slate">Duration</dt>
              <dd className="tabular-nums">{isLive ? "In progress" : formatDuration(overview.duration_s)}</dd>
            </div>
            <div className="flex gap-1.5">
              <dt className="text-slate">Engine</dt>
              <dd>{overview.engine}</dd>
            </div>
          </dl>
        </div>
        <div className="flex items-start gap-4">
          <RealtimeRefresh
            channelName={`call-${overview.id}`}
            subscriptions={[
              { table: "calls", filter: `id=eq.${overview.id}` },
              { table: "transcript_turns", filter: `call_id=eq.${overview.id}` },
              { table: "call_events", filter: `call_id=eq.${overview.id}` },
            ]}
          />
          <ReprocessButton callId={overview.id} disabled={isLive} />
        </div>
      </header>

      <div className="grid gap-6 xl:grid-cols-[1.45fr_1fr]">
        <div className="flex flex-col gap-6">
          {overview.summary_bn || overview.summary_en ? (
            <Panel title="Summary">
              <div className="grid gap-4 md:grid-cols-2">
                {overview.summary_bn ? (
                  <p lang="bn" className="leading-relaxed text-ink">
                    {overview.summary_bn}
                  </p>
                ) : null}
                {overview.summary_en ? <p className="leading-relaxed text-ink-soft">{overview.summary_en}</p> : null}
              </div>
            </Panel>
          ) : null}
          <Panel title={`Transcript (${turns.length} turns)`}>
            <TranscriptView turns={turns} isLive={isLive} />
          </Panel>
        </div>

        <div className="flex flex-col gap-6">
          <Panel title="Extracted fields">
            {extraction ? (
              <ExtractedFields extraction={extraction} />
            ) : (
              <p className="text-sm text-slate">
                {isLive
                  ? "Fields are extracted when the call ends."
                  : "No extraction yet. It usually arrives within a minute of the call ending; use Reprocess if it does not."}
              </p>
            )}
          </Panel>

          <Panel title="Appointment">
            {appointments.length ? (
              <ul className="flex flex-col gap-4 divide-y divide-line">
                {appointments.map((appointment) => (
                  <li key={appointment.id} className="pt-4 first:pt-0">
                    <AppointmentLine appointment={appointment} />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-slate">No appointment was booked on this call.</p>
            )}
          </Panel>

          <Panel title="Callback requests">
            {callbacks.length ? (
              <ul className="flex flex-col gap-4 divide-y divide-line">
                {callbacks.map((callback) => (
                  <li key={callback.id} className="flex items-start justify-between gap-4 pt-4 first:pt-0">
                    <div>
                      <p className="text-ink" lang="bn">
                        {callback.reason}
                      </p>
                      <div className="mt-1.5 flex gap-1.5">
                        <Badge tone={(CALLBACK_PRIORITY_LABELS[callback.priority] ?? CALLBACK_PRIORITY_LABELS[2]).tone}>
                          {(CALLBACK_PRIORITY_LABELS[callback.priority] ?? CALLBACK_PRIORITY_LABELS[2]).label}
                        </Badge>
                        <Badge tone={CALLBACK_STATUS_LABELS[callback.status].tone}>{CALLBACK_STATUS_LABELS[callback.status].label}</Badge>
                      </div>
                    </div>
                    {callback.status !== "done" ? <ResolveCallbackButton callbackId={callback.id} /> : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-slate">No human callback was requested.</p>
            )}
          </Panel>

          <Panel title="Response latency">
            <LatencyStats summaries={latency} />
            <p className="mt-3 text-xs text-slate">Measured per turn, from the end of the caller&apos;s speech to Nila&apos;s first audio.</p>
          </Panel>

          <Panel title="Tool and event timeline">
            <EventsTimeline events={events} startedAt={overview.started_at} />
          </Panel>
        </div>
      </div>

      <p className="text-xs text-slate">
        Room <span className="font-mono">{overview.room_name}</span> · Call id <span className="font-mono">{overview.id}</span>
      </p>
    </div>
  );
}
