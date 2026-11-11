import type { Metadata } from "next";
import Link from "next/link";
import { Badge } from "@/components/portal/badge";
import { PageHeader } from "@/components/portal/page-header";
import { ResolveCallbackButton } from "@/components/portal/resolve-callback-button";
import { EmptyState, ErrorState } from "@/components/portal/states";
import { SupabaseMissing } from "@/components/portal/supabase-missing";
import { CALLBACK_PRIORITY_LABELS, CALLBACK_STATUS_LABELS } from "@/constants/portal";
import { formatDhakaDateTime, formatPhone } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { listCallbackRequests } from "@/lib/repositories/callbacks-repository";
import { requirePortalContext } from "@/lib/supabase/server";
import type { CallbackRequestRow } from "@/types/database";

export const metadata: Metadata = { title: "Callbacks" };

const logger = createLogger("portal.callbacks");

function sortQueue(callbacks: CallbackRequestRow[]): CallbackRequestRow[] {
  return [...callbacks].sort((first, second) => {
    const firstDone = first.status === "done" ? 1 : 0;
    const secondDone = second.status === "done" ? 1 : 0;
    if (firstDone !== secondDone) return firstDone - secondDone;
    if (!firstDone && first.priority !== second.priority) return first.priority - second.priority;
    return second.created_at.localeCompare(first.created_at);
  });
}

export default async function CallbacksPage() {
  const access = await requirePortalContext();
  if (access === "unconfigured") {
    return <SupabaseMissing />;
  }
  let callbacks: CallbackRequestRow[] | null = null;
  try {
    callbacks = sortQueue(await listCallbackRequests(access.client));
  } catch (error) {
    logger.error("Callbacks failed to load", { error });
  }
  const openCount = callbacks?.filter((callback) => callback.status !== "done").length ?? 0;

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Callback queue"
        description={`Requests Nila handed to a human: medical questions, out-of-scope requests and anything she could not answer. ${openCount} open.`}
      />
      {!callbacks ? (
        <ErrorState title="Could not load callbacks" body="Refresh the page to try again." />
      ) : callbacks.length === 0 ? (
        <EmptyState title="The queue is empty" body="When a caller needs a doctor or staff member, the request lands here." />
      ) : (
        <ul className="flex flex-col divide-y divide-line overflow-hidden rounded-2xl border border-line bg-paper">
          {callbacks.map((callback) => {
            const priority = CALLBACK_PRIORITY_LABELS[callback.priority] ?? CALLBACK_PRIORITY_LABELS[2];
            const status = CALLBACK_STATUS_LABELS[callback.status];
            return (
              <li
                key={callback.id}
                className={`grid gap-3 px-5 py-4 md:grid-cols-[1fr_auto] md:items-center ${callback.status === "done" ? "opacity-60" : ""}`}
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-ink" lang="bn">
                      {callback.patients?.full_name_bn ?? callback.patients?.full_name_en ?? "Unknown caller"}
                    </span>
                    <span className="text-sm tabular-nums text-ink-soft">{formatPhone(callback.patients?.phone_e164)}</span>
                    <Badge tone={priority.tone}>{priority.label}</Badge>
                    <Badge tone={status.tone}>{status.label}</Badge>
                  </div>
                  <p className="mt-1 text-ink" lang="bn">
                    {callback.reason}
                  </p>
                  <p className="mt-1 text-xs text-slate">
                    Requested {formatDhakaDateTime(callback.created_at)}
                    {callback.resolved_at ? `, resolved ${formatDhakaDateTime(callback.resolved_at)}` : ""}
                    {" · "}
                    <Link href={`/portal/calls/${callback.call_id}`} className="text-teal-deep hover:underline">
                      View call
                    </Link>
                  </p>
                </div>
                {callback.status !== "done" ? <ResolveCallbackButton callbackId={callback.id} /> : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
