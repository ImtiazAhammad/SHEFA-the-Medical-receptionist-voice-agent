import type { LatencySummary } from "@/types/portal";

export function LatencyStats({ summaries }: { summaries: LatencySummary[] }) {
  if (summaries.length === 0) {
    return <p className="text-sm text-slate">No latency measurements were recorded for this call.</p>;
  }
  return (
    <table className="w-full text-sm">
      <thead className="text-xs text-slate">
        <tr>
          <th scope="col" className="pb-2 text-left font-semibold">Metric</th>
          <th scope="col" className="pb-2 text-right font-semibold">Turns</th>
          <th scope="col" className="pb-2 text-right font-semibold">Median</th>
          <th scope="col" className="pb-2 text-right font-semibold">Average</th>
          <th scope="col" className="pb-2 text-right font-semibold">Worst</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-line">
        {summaries.map((summary) => (
          <tr key={summary.metric}>
            <th scope="row" className="py-2 text-left font-medium text-ink first-letter:uppercase">{summary.metric.replace(/_/g, " ")}</th>
            <td className="py-2 text-right tabular-nums text-ink-soft">{summary.count}</td>
            <td className="py-2 text-right font-semibold tabular-nums text-ink">{(summary.p50Milliseconds / 1000).toFixed(2)} s</td>
            <td className="py-2 text-right tabular-nums text-ink-soft">{(summary.averageMilliseconds / 1000).toFixed(2)} s</td>
            <td className="py-2 text-right tabular-nums text-ink-soft">{(summary.maxMilliseconds / 1000).toFixed(2)} s</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
