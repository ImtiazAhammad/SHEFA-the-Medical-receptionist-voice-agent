import { Badge } from "@/components/portal/badge";
import { GUARDRAIL_LABELS, type BadgeTone } from "@/constants/portal";
import { formatOffset } from "@/lib/format";
import type { CallEventRow } from "@/types/database";

const EVENT_TONES: Record<CallEventRow["event_type"], BadgeTone> = {
  state: "slate",
  tool_call: "sky",
  tool_result: "teal",
  latency: "violet",
  error: "rose",
};

const EVENT_LABELS: Record<CallEventRow["event_type"], string> = {
  state: "State",
  tool_call: "Tool call",
  tool_result: "Tool result",
  latency: "Latency",
  error: "Error",
};

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function guardrailOf(event: CallEventRow): string | null {
  return text(event.payload.guardrail);
}

function describe(event: CallEventRow): string {
  const payload = event.payload;
  const guardrail = guardrailOf(event);
  if (guardrail) {
    return GUARDRAIL_LABELS[guardrail] ?? guardrail.replace(/_/g, " ");
  }
  if (event.event_type === "latency") {
    const metric = text(payload.metric) ?? "latency";
    return typeof payload.value_ms === "number" ? `${metric.replace(/_/g, " ")}: ${Math.round(payload.value_ms)} ms` : metric;
  }
  const tool = text(payload.tool) ?? text(payload.name) ?? text(payload.tool_name);
  const state = text(payload.state) ?? text(payload.status) ?? text(payload.phase);
  const message = text(payload.message) ?? text(payload.error) ?? text(payload.detail);
  return [tool, state, message].filter(Boolean).join(" · ") || "—";
}

export function EventsTimeline({ events, startedAt }: { events: CallEventRow[]; startedAt: string }) {
  const start = new Date(startedAt).getTime();
  const visible = events.filter((event) => event.event_type !== "latency");
  if (visible.length === 0) {
    return <p className="text-sm text-slate">No tool calls or state changes were logged.</p>;
  }
  return (
    <ol className="relative flex flex-col gap-4 border-l border-line pl-5">
      {visible.map((event) => (
        <li key={event.id} className="relative">
          <span
            aria-hidden
            className={`absolute -left-[1.6rem] top-1.5 h-2.5 w-2.5 rounded-full ring-4 ring-paper ${
              event.event_type === "error" ? "bg-rose" : event.event_type === "tool_result" ? "bg-teal" : "bg-slate/50"
            }`}
          />
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs tabular-nums text-slate">{formatOffset(Math.max(0, new Date(event.occurred_at).getTime() - start))}</span>
            {guardrailOf(event) ? (
              <Badge tone="marigold">Guardrail</Badge>
            ) : (
              <Badge tone={EVENT_TONES[event.event_type]}>{EVENT_LABELS[event.event_type]}</Badge>
            )}
          </div>
          <p className="mt-1 text-sm text-ink">{describe(event)}</p>
          {Object.keys(event.payload).length ? (
            <details className="mt-1">
              <summary className="cursor-pointer text-xs text-slate hover:text-ink">Payload</summary>
              <pre className="mt-1 max-h-56 overflow-auto rounded-lg bg-enamel p-3 text-xs leading-relaxed text-ink-soft">
                {JSON.stringify(event.payload, null, 2)}
              </pre>
            </details>
          ) : null}
        </li>
      ))}
    </ol>
  );
}
