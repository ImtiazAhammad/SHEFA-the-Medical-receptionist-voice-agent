import Link from "next/link";
import { CallStatusBadges } from "@/components/portal/call-badges";
import { formatDhakaDate, formatDhakaTime, formatDuration, formatPhone } from "@/lib/format";
import type { CallOverviewRow } from "@/types/database";

export function CallsTable({ calls, compact = false }: { calls: CallOverviewRow[]; compact?: boolean }) {
  return (
    <div className={compact ? "overflow-x-auto" : "overflow-x-auto rounded-2xl border border-line bg-paper"}>
      <table className="w-full min-w-[720px] text-left text-sm">
        <thead className="border-b border-line bg-enamel/60 text-xs text-slate">
          <tr>
            <th scope="col" className="px-4 py-3 font-semibold">Date</th>
            <th scope="col" className="px-4 py-3 font-semibold">Time</th>
            <th scope="col" className="px-4 py-3 font-semibold">Caller</th>
            <th scope="col" className="px-4 py-3 font-semibold">Phone</th>
            <th scope="col" className="px-4 py-3 text-right font-semibold">Duration</th>
            <th scope="col" className="px-4 py-3 font-semibold">Status</th>
            {compact ? null : <th scope="col" className="px-4 py-3 font-semibold">Reason</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {calls.map((call) => {
            const name = call.caller_name_bn ?? call.caller_name_en;
            return (
              <tr key={call.id} className="group relative transition hover:bg-enamel/70">
                <td className="whitespace-nowrap px-4 py-3 text-ink-soft">{formatDhakaDate(call.started_at)}</td>
                <td className="whitespace-nowrap px-4 py-3 tabular-nums text-ink-soft">{formatDhakaTime(call.started_at)}</td>
                <td className="px-4 py-3">
                  <Link href={`/portal/calls/${call.id}`} className="font-medium text-ink after:absolute after:inset-0 group-hover:text-teal-deep">
                    {name ?? <span className="text-slate">Unknown caller</span>}
                  </Link>
                  {call.caller_name_bn && call.caller_name_en ? (
                    <span className="block text-xs text-slate">{call.caller_name_en}</span>
                  ) : null}
                </td>
                <td className="whitespace-nowrap px-4 py-3 tabular-nums text-ink-soft">{formatPhone(call.caller_phone)}</td>
                <td className="whitespace-nowrap px-4 py-3 text-right tabular-nums text-ink-soft">
                  {call.status === "in_progress" ? "—" : formatDuration(call.duration_s)}
                </td>
                <td className="px-4 py-3">
                  <CallStatusBadges status={call.status} outcome={call.outcome} />
                </td>
                {compact ? null : (
                  <td className="max-w-[16rem] truncate px-4 py-3 text-ink-soft" title={call.reason_for_visit ?? undefined}>
                    {call.reason_for_visit ?? "—"}
                  </td>
                )}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
