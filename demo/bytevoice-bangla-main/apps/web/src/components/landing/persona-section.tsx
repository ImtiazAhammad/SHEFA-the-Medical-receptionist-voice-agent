"use client";

import { useEffect, useRef, useState } from "react";
import { NilaAvatar } from "@/components/landing/nila-avatar";
import { useLanguage } from "@/i18n/language-provider";
import type { Dictionary } from "@/types/i18n";

const TOOL_LINE_DELAY_MS = 1100;
const BASE_LINE_DELAY_MS = 900;
const PER_CHARACTER_DELAY_MS = 22;
const MAX_LINE_DELAY_MS = 3200;

type ScriptLine = Dictionary["persona"]["script"][number];

function delayBefore(line: ScriptLine): number {
  if (line.speaker === "tool") {
    return TOOL_LINE_DELAY_MS;
  }
  return Math.min(BASE_LINE_DELAY_MS + line.text.length * PER_CHARACTER_DELAY_MS, MAX_LINE_DELAY_MS);
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function SampleCall({ text }: { text: Dictionary["persona"] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const transcriptRef = useRef<HTMLOListElement>(null);
  const [started, setStarted] = useState(false);
  const [visibleCount, setVisibleCount] = useState(0);
  const script = text.script;
  const finished = visibleCount >= script.length;
  const nextLine = script[visibleCount];
  const agentIsTyping = started && !finished && nextLine?.speaker === "agent";

  useEffect(() => {
    const element = containerRef.current;
    if (!element) {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setStarted(true);
          observer.disconnect();
        }
      },
      { threshold: 0.35 },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!started || finished || !nextLine) {
      return;
    }
    const timer = window.setTimeout(
      () => setVisibleCount(prefersReducedMotion() ? script.length : (count) => count + 1),
      visibleCount === 0 ? 400 : delayBefore(nextLine),
    );
    return () => window.clearTimeout(timer);
  }, [started, finished, nextLine, visibleCount, script.length]);

  useEffect(() => {
    const transcript = transcriptRef.current;
    if (transcript) {
      transcript.scrollTo({ top: transcript.scrollHeight, behavior: prefersReducedMotion() ? "auto" : "smooth" });
    }
  }, [visibleCount, agentIsTyping]);

  return (
    <div ref={containerRef} className="mx-auto w-full max-w-sm">
      <div className="rounded-[2.5rem] border border-night-line bg-night p-3 shadow-[0_40px_80px_-30px_rgb(5_33_31/0.8)]">
        <div className="overflow-hidden rounded-[2rem] bg-night-raised">
          <div className="flex items-center gap-3 border-b border-night-line px-5 pb-4 pt-6">
            <NilaAvatar className="h-11 w-11 shrink-0" speaking={agentIsTyping} />
            <div className="min-w-0 flex-1">
              <p className="text-xs uppercase tracking-[0.18em] text-mint/80">{text.phoneTitle}</p>
              <p className="truncate text-sm font-medium text-paper">{text.phoneCaller}</p>
            </div>
            <span className="flex items-center gap-1.5 rounded-pill bg-teal/15 px-2.5 py-1 text-xs font-semibold text-mint">
              <span className="h-2 w-2 animate-pulse rounded-full bg-teal" aria-hidden />
              {text.name}
            </span>
          </div>
          <ol
            ref={transcriptRef}
            aria-live="polite"
            className="flex h-[26rem] flex-col gap-2.5 overflow-y-auto px-4 py-5 [scrollbar-width:none]"
          >
            {script.slice(0, visibleCount).map((line, index) => {
              if (line.speaker === "tool") {
                return (
                  <li key={index} className="self-center rounded-pill border border-marigold/40 bg-marigold/10 px-3 py-1 text-xs font-medium text-marigold animate-[persona-in_300ms_ease-out]">
                    {line.text}
                  </li>
                );
              }
              const fromAgent = line.speaker === "agent";
              return (
                <li
                  key={index}
                  className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed animate-[persona-in_300ms_ease-out] ${
                    fromAgent
                      ? "self-start rounded-bl-md bg-teal-deep text-paper"
                      : "self-end rounded-br-md bg-paper text-ink"
                  }`}
                >
                  {line.text}
                </li>
              );
            })}
            {agentIsTyping ? (
              <li className="flex gap-1 self-start rounded-2xl rounded-bl-md bg-teal-deep/70 px-3.5 py-3" aria-hidden>
                {[0, 150, 300].map((delay) => (
                  <span
                    key={delay}
                    className="h-1.5 w-1.5 animate-bounce rounded-full bg-mint"
                    style={{ animationDelay: `${delay}ms` }}
                  />
                ))}
              </li>
            ) : null}
          </ol>
          <div className="flex items-center justify-between border-t border-night-line px-5 py-3">
            <p className="text-[11px] leading-snug text-slate">{text.sampleNote}</p>
            {finished ? (
              <button
                type="button"
                onClick={() => setVisibleCount(0)}
                className="ml-3 shrink-0 rounded-pill border border-mint/40 px-3 py-1 text-xs font-semibold text-mint transition hover:bg-mint/10"
              >
                {text.replay}
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}

export function PersonaSection() {
  const { dictionary, language } = useLanguage();
  const text = dictionary.persona;

  return (
    <section id="meet-nila" aria-labelledby="persona-title" className="bg-night text-paper">
      <div className="mx-auto grid w-full max-w-7xl items-center gap-14 px-4 py-20 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:gap-20 lg:px-8 lg:py-28">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.2em] text-marigold">{text.eyebrow}</p>
          <h2 id="persona-title" className="mt-4 text-[clamp(1.9rem,3.6vw,2.9rem)] font-bold leading-tight">
            {text.title}
          </h2>
          <p className="mt-5 max-w-xl text-lg leading-relaxed text-mint/80">{text.body}</p>

          <div className="mt-10 flex max-w-xl items-center gap-5 rounded-3xl border border-night-line bg-night-raised p-5">
            <NilaAvatar className="h-24 w-24 shrink-0 sm:h-28 sm:w-28" />
            <div className="min-w-0">
              <p className="text-2xl font-bold">{text.name}</p>
              <p className="mt-1 text-sm text-mint/80">{text.role}</p>
              <p className="mt-3 inline-flex items-center gap-2 rounded-pill bg-teal/15 px-3 py-1 text-xs font-semibold text-mint">
                <span className="h-2 w-2 animate-pulse rounded-full bg-teal" aria-hidden />
                {text.status}
              </p>
            </div>
          </div>

          <ul className="mt-6 grid max-w-xl gap-2.5 sm:grid-cols-2">
            {text.traits.map((trait) => (
              <li key={trait} className="flex items-start gap-2.5 text-sm leading-relaxed text-paper/90">
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-marigold" aria-hidden />
                {trait}
              </li>
            ))}
          </ul>
        </div>
        <SampleCall key={language} text={text} />
      </div>
    </section>
  );
}
