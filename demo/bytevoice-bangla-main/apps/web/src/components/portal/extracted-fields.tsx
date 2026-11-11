import { Badge } from "@/components/portal/badge";
import { INTENT_LABELS } from "@/constants/portal";
import { formatDhakaDate, formatPhone } from "@/lib/format";
import type { CallExtractionRow } from "@/types/database";

const CONFIDENCE_THRESHOLD = 0.7;

interface ConfidenceReading {
  score: number | null;
  note: string | null;
}

interface FieldRow {
  key: string;
  label: string;
  value: string | null;
  detail?: string | null;
  isValid: boolean;
  confidenceKeys: string[];
}

function normalizeScore(value: number): number {
  return value > 1 ? value / 100 : value;
}

function readConfidence(confidence: Record<string, unknown>, keys: string[]): ConfidenceReading {
  for (const key of keys) {
    const entry = confidence[key];
    if (typeof entry === "number") {
      return { score: normalizeScore(entry), note: null };
    }
    if (typeof entry === "string") {
      return { score: null, note: entry };
    }
    if (entry && typeof entry === "object") {
      const record = entry as Record<string, unknown>;
      const rawScore = record.score ?? record.value ?? record.confidence;
      const rawNote = record.note ?? record.reason ?? record.flag ?? record.message;
      return {
        score: typeof rawScore === "number" ? normalizeScore(rawScore) : null,
        note: typeof rawNote === "string" ? rawNote : null,
      };
    }
  }
  return { score: null, note: null };
}

function buildRows(extraction: CallExtractionRow): FieldRow[] {
  const nameValue = extraction.patient_name_bn ?? extraction.patient_name_en;
  return [
    {
      key: "name",
      label: "Patient name",
      value: nameValue,
      detail: extraction.patient_name_bn && extraction.patient_name_en ? extraction.patient_name_en : null,
      isValid: Boolean(nameValue) && extraction.name_confirmed !== false,
      confidenceKeys: ["patient_name", "patient_name_bn", "name"],
    },
    {
      key: "phone",
      label: "Phone",
      value: extraction.phone_e164 ? formatPhone(extraction.phone_e164) : null,
      detail: extraction.phone_spoken_raw ? `Heard as “${extraction.phone_spoken_raw}”` : null,
      isValid: extraction.phone_valid === true,
      confidenceKeys: ["phone", "phone_e164"],
    },
    {
      key: "reason",
      label: "Reason for visit",
      value: extraction.reason_for_visit,
      detail: extraction.service_code ? `Service: ${extraction.service_code.replace(/_/g, " ")}` : null,
      isValid: Boolean(extraction.reason_for_visit),
      confidenceKeys: ["reason_for_visit", "reason", "service_code"],
    },
    {
      key: "date",
      label: "Preferred date",
      value: extraction.preferred_date ? formatDhakaDate(`${extraction.preferred_date}T06:00:00Z`) : null,
      isValid: Boolean(extraction.preferred_date),
      confidenceKeys: ["preferred_date", "date"],
    },
    {
      key: "time",
      label: "Preferred time",
      value: extraction.preferred_time_window,
      isValid: Boolean(extraction.preferred_time_window),
      confidenceKeys: ["preferred_time_window", "time"],
    },
    {
      key: "intent",
      label: "Intent",
      value: extraction.intent ? (INTENT_LABELS[extraction.intent] ?? extraction.intent) : null,
      isValid: Boolean(extraction.intent),
      confidenceKeys: ["intent"],
    },
  ];
}

export function ExtractedFields({ extraction }: { extraction: CallExtractionRow }) {
  const rows = buildRows(extraction);
  const usedKeys = new Set(rows.flatMap((row) => row.confidenceKeys));
  const otherNotes = Object.entries(extraction.confidence).filter(([key]) => !usedKeys.has(key));

  return (
    <div>
      <dl className="divide-y divide-line">
        {rows.map((row) => {
          const confidence = readConfidence(extraction.confidence, row.confidenceKeys);
          const isConfident = confidence.score === null || confidence.score >= CONFIDENCE_THRESHOLD;
          const passes = row.isValid && isConfident;
          return (
            <div key={row.key} className="flex items-start justify-between gap-4 py-3 first:pt-0">
              <div className="min-w-0">
                <dt className="text-xs text-slate">{row.label}</dt>
                <dd className="mt-0.5 break-words font-medium text-ink">{row.value ?? <span className="text-slate">Not captured</span>}</dd>
                {row.detail ? <dd className="mt-0.5 text-xs text-slate">{row.detail}</dd> : null}
                {confidence.note ? <dd className="mt-1 text-xs text-marigold-deep">{confidence.note}</dd> : null}
              </div>
              <dd className="flex shrink-0 flex-col items-end gap-1">
                {row.value === null ? (
                  <Badge tone="slate">Missing</Badge>
                ) : passes ? (
                  <Badge tone="teal">✓ Valid</Badge>
                ) : (
                  <Badge tone="marigold">⚠ Check</Badge>
                )}
                {confidence.score !== null ? (
                  <span className="text-xs tabular-nums text-slate">{Math.round(confidence.score * 100)}% confidence</span>
                ) : null}
              </dd>
            </div>
          );
        })}
      </dl>
      {otherNotes.length ? (
        <details className="mt-3 rounded-lg bg-enamel px-3 py-2 text-xs text-ink-soft">
          <summary className="cursor-pointer font-medium">Validator notes</summary>
          <ul className="mt-2 flex flex-col gap-1">
            {otherNotes.map(([key, value]) => (
              <li key={key}>
                <span className="font-semibold">{key}:</span> {typeof value === "string" ? value : JSON.stringify(value)}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      <p className="mt-4 text-xs text-slate">
        Extracted {extraction.extractor_model ? `by ${extraction.extractor_model} ` : ""}and re-checked by the phone, date and name validators.
      </p>
    </div>
  );
}
