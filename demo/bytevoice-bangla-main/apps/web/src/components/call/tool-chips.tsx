"use client";

import type { ToolChip } from "@/types/call";
import type { Language } from "@/types/i18n";

const PHASE_STYLES: Record<ToolChip["phase"], string> = {
  start: "border-mint/30 bg-mint/10 text-mint",
  success: "border-teal/50 bg-teal/15 text-enamel",
  error: "border-rose/50 bg-rose/15 text-enamel",
};

function PhaseIcon({ phase }: { phase: ToolChip["phase"] }) {
  if (phase === "start") {
    return <span aria-hidden className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-mint/30 border-t-mint" />;
  }
  if (phase === "success") {
    return (
      <svg aria-hidden viewBox="0 0 16 16" className="h-3.5 w-3.5 text-teal">
        <path d="M3 8.5 6.5 12 13 4.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  return (
    <svg aria-hidden viewBox="0 0 16 16" className="h-3.5 w-3.5 text-rose">
      <path d="M4 4l8 8M12 4l-8 8" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function ToolChips({ chips, language }: { chips: ToolChip[]; language: Language }) {
  if (chips.length === 0) {
    return <div className="min-h-9" aria-hidden />;
  }
  return (
    <ul aria-live="polite" className="flex min-h-9 flex-wrap justify-center gap-2">
      {chips.map((chip) => (
        <li
          key={chip.id}
          className={`chip-in inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm ${PHASE_STYLES[chip.phase]}`}
        >
          <PhaseIcon phase={chip.phase} />
          {language === "bn" ? chip.label_bn : chip.label_en}
        </li>
      ))}
    </ul>
  );
}
