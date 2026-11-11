import type { Metadata } from "next";
import { MermaidDiagram } from "@/components/portal/mermaid-diagram";
import { PageHeader } from "@/components/portal/page-header";
import { Panel } from "@/components/portal/states";
import {
  CALL_FLOW_DIAGRAM,
  ENTITY_RELATIONSHIP_DIAGRAM,
  STORAGE_FACTS,
  TABLE_EXPLANATIONS,
  VALIDATION_RULES,
} from "@/constants/data-model";

export const metadata: Metadata = { title: "Data model" };

const FLOW_STEPS = [
  "The caller presses the hero button. The token route rate-limits by IP, creates room call-<uuid> and returns a 10-minute token that dispatches the bytevoice-bn agent.",
  "The browser joins the room and publishes the microphone; the agent joins on dispatch and inserts a calls row (in_progress, engine, after_hours in Asia/Dhaka).",
  "Every final caller or agent utterance becomes a transcript_turns row with its offset. The portal is subscribed through Realtime, so the call shows up live.",
  "Tool calls go through validators before writing patients, appointments and callback_requests. Each call, result and per-turn latency is logged to call_events.",
  "On hang-up, the end_call tool or the 5-minute cap, the agent sets ended_at and calls finalize: Gemini produces call_extractions, bilingual summaries, English turns and the outcome, re-checked by the validators.",
  "If finalize fails, the call stays completed with outcome incomplete and an error event; staff press Reprocess on the call page to run it again.",
];

export default function DataModelPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="How the data is organised"
        description="The schema, how each table is used, how a live call reaches storage, and where the data lives."
      />

      <Panel title="Entity relationship diagram">
        <MermaidDiagram definition={ENTITY_RELATIONSHIP_DIAGRAM} label="Entity relationship diagram of the ByteVoice schema" />
      </Panel>

      <Panel title="Tables">
        <div className="-m-5 overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="border-b border-line text-xs text-slate">
              <tr>
                <th scope="col" className="px-5 py-3 font-semibold">Table</th>
                <th scope="col" className="px-5 py-3 font-semibold">One row per</th>
                <th scope="col" className="px-5 py-3 font-semibold">Written by</th>
                <th scope="col" className="px-5 py-3 font-semibold">Why it exists</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {TABLE_EXPLANATIONS.map((table) => (
                <tr key={table.name} className="align-top">
                  <th scope="row" className="px-5 py-3 font-mono text-xs font-semibold text-ink">{table.name}</th>
                  <td className="px-5 py-3 text-ink-soft">{table.grain}</td>
                  <td className="px-5 py-3 text-ink-soft">{table.writer}</td>
                  <td className="px-5 py-3 text-ink">{table.purpose}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <Panel title="From a live call to storage">
        <MermaidDiagram definition={CALL_FLOW_DIAGRAM} label="Flow of data from the browser call to Supabase and the portal" />
        <ol className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {FLOW_STEPS.map((step, index) => (
            <li key={step} className="flex gap-3">
              <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-teal/12 text-sm font-bold text-teal-deep">
                {index + 1}
              </span>
              <p className="text-sm leading-relaxed text-ink">{step}</p>
            </li>
          ))}
        </ol>
      </Panel>

      <div className="grid gap-6 xl:grid-cols-[1fr_1.3fr]">
        <Panel title="Where the data is stored">
          <dl className="flex flex-col divide-y divide-line">
            {STORAGE_FACTS.map((fact) => (
              <div key={fact.label} className="py-3 first:pt-0 last:pb-0">
                <dt className="text-xs font-semibold text-slate">{fact.label}</dt>
                <dd className="mt-0.5 text-ink">{fact.value}</dd>
              </div>
            ))}
          </dl>
        </Panel>
        <Panel title="How fields are validated">
          <div className="-m-5 overflow-x-auto">
            <table className="w-full min-w-[520px] text-left text-sm">
              <thead className="border-b border-line text-xs text-slate">
                <tr>
                  <th scope="col" className="px-5 py-3 font-semibold">Field</th>
                  <th scope="col" className="px-5 py-3 font-semibold">Rule</th>
                  <th scope="col" className="px-5 py-3 font-semibold">Enforced in</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {VALIDATION_RULES.map((rule) => (
                  <tr key={rule.field} className="align-top">
                    <th scope="row" className="px-5 py-3 font-semibold text-ink">{rule.field}</th>
                    <td className="px-5 py-3 text-ink">{rule.rule}</td>
                    <td className="px-5 py-3 text-ink-soft">{rule.enforcedIn}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </div>
  );
}
