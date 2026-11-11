"use client";

import { useEffect, useState } from "react";
import { MAX_CALL_SECONDS } from "@/constants/call";
import { formatDuration, toBanglaDigits } from "@/lib/format";
import type { Language } from "@/types/i18n";

export function CallTimer({ startedAt, language }: { startedAt: number; language: Language }) {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(interval);
  }, []);

  const elapsedSeconds = Math.min(MAX_CALL_SECONDS, Math.max(0, Math.floor((now - startedAt) / 1000)));
  const text = `${formatDuration(elapsedSeconds)} / ${formatDuration(MAX_CALL_SECONDS)}`;
  const progress = elapsedSeconds / MAX_CALL_SECONDS;

  return (
    <div className="flex flex-col gap-1.5" role="timer" aria-label={text}>
      <span className="font-numeric text-lg font-semibold tabular-nums text-enamel">
        {language === "bn" ? toBanglaDigits(text) : text}
      </span>
      <span className="h-1 w-28 overflow-hidden rounded-full bg-night-line">
        <span
          className={`block h-full rounded-full ${progress > 0.85 ? "bg-rose" : "bg-teal"}`}
          style={{ width: `${Math.round(progress * 100)}%` }}
        />
      </span>
    </div>
  );
}
