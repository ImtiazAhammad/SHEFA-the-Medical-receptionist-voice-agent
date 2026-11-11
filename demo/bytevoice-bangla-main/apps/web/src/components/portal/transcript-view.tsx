"use client";

import { useState } from "react";
import { formatOffset } from "@/lib/format";
import type { TranscriptTurnRow } from "@/types/database";

type TranscriptLanguage = "bn" | "en";

export function TranscriptView({ turns, isLive }: { turns: TranscriptTurnRow[]; isLive: boolean }) {
  const [language, setLanguage] = useState<TranscriptLanguage>("bn");
  const hasTranslations = turns.some((turn) => turn.text_en);

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div role="group" aria-label="Transcript language" className="inline-flex rounded-full border border-line bg-enamel p-0.5 text-sm">
          {(["bn", "en"] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={language === option}
              onClick={() => setLanguage(option)}
              className={`rounded-full px-3.5 py-1 font-medium transition ${
                language === option ? "bg-ink text-white" : "text-ink-soft hover:text-ink"
              }`}
            >
              {option === "bn" ? "বাংলা" : "English"}
            </button>
          ))}
        </div>
        {language === "en" && !hasTranslations ? (
          <span className="text-xs text-slate">English translation is added after the call is processed.</span>
        ) : null}
      </div>
      {turns.length === 0 ? (
        <p className="py-6 text-center text-sm text-slate">
          {isLive ? "Waiting for the first words…" : "No transcript was recorded for this call."}
        </p>
      ) : (
        <ol className="flex flex-col gap-3" aria-live={isLive ? "polite" : undefined}>
          {turns.map((turn) => {
            const isAgent = turn.speaker === "agent";
            const text = language === "en" && turn.text_en ? turn.text_en : turn.text_bn;
            return (
              <li key={turn.id} className={`flex flex-col gap-1 ${isAgent ? "items-start" : "items-end"}`}>
                <span className="flex items-center gap-2 text-xs text-slate">
                  <span className={`font-semibold ${isAgent ? "text-teal-deep" : "text-ink"}`}>{isAgent ? "Nila (agent)" : "Caller"}</span>
                  <span className="tabular-nums">{formatOffset(turn.offset_ms)}</span>
                  {turn.interrupted ? (
                    <span className="rounded-full bg-marigold/15 px-2 py-px font-semibold text-marigold-deep" title="The caller spoke over this turn">
                      interrupted
                    </span>
                  ) : null}
                </span>
                <p
                  lang={language === "en" && turn.text_en ? "en" : "bn"}
                  className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 leading-relaxed ${
                    isAgent ? "rounded-tl-sm bg-enamel text-ink" : "rounded-tr-sm bg-ink text-white"
                  } ${turn.interrupted ? "opacity-80" : ""}`}
                >
                  {text}
                  {turn.interrupted ? <span aria-hidden className="ml-1 text-marigold">—</span> : null}
                </p>
              </li>
            );
          })}
          {isLive ? (
            <li className="flex items-center gap-2 text-xs text-slate">
              <span className="live-dot h-2 w-2 rounded-full bg-rose" /> Call in progress
            </li>
          ) : null}
        </ol>
      )}
    </div>
  );
}
