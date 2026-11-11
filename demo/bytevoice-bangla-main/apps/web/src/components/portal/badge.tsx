import type { ReactNode } from "react";
import type { BadgeTone } from "@/constants/portal";

const TONE_CLASSES: Record<BadgeTone, string> = {
  teal: "bg-teal/12 text-teal-deep ring-teal/25",
  marigold: "bg-marigold/15 text-marigold-deep ring-marigold/30",
  rose: "bg-rose/10 text-rose ring-rose/25",
  slate: "bg-slate/10 text-ink-soft ring-slate/20",
  sky: "bg-sky/10 text-sky ring-sky/25",
  violet: "bg-violet/10 text-violet ring-violet/25",
};

export function Badge({ tone, children }: { tone: BadgeTone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${TONE_CLASSES[tone]}`}>
      {children}
    </span>
  );
}

export function LivePill() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-rose px-2.5 py-0.5 text-xs font-bold text-white">
      <span aria-hidden className="live-dot h-1.5 w-1.5 rounded-full bg-white" />
      LIVE
    </span>
  );
}
