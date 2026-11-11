"use client";

import Link from "next/link";
import { useLanguage } from "@/i18n/language-provider";

export function PortalPreviewSection() {
  const { dictionary } = useLanguage();
  const text = dictionary.portalPreview;

  return (
    <section aria-labelledby="portal-preview-title" className="mx-auto w-full max-w-7xl px-4 py-20 sm:px-6 lg:px-8 lg:py-28">
      <div className="grid items-center gap-12 lg:grid-cols-[0.85fr_1.15fr]">
        <div>
          <h2 id="portal-preview-title" className="text-[clamp(1.9rem,3.6vw,2.9rem)] font-bold leading-tight text-ink">
            {text.title}
          </h2>
          <p className="mt-4 max-w-md text-lg leading-relaxed text-ink-soft">{text.body}</p>
          <Link
            href="/portal"
            className="mt-8 inline-flex h-12 items-center rounded-full bg-ink px-6 font-semibold text-white transition hover:bg-teal-deep"
          >
            {text.cta}
          </Link>
        </div>

        <figure aria-label={text.mockTitle} className="overflow-hidden rounded-3xl border border-line bg-paper shadow-[0_30px_80px_-40px_rgb(12_43_41/0.45)]">
          <div className="flex items-center gap-2 border-b border-line bg-enamel px-5 py-3">
            <span className="h-2.5 w-2.5 rounded-full bg-rose/70" />
            <span className="h-2.5 w-2.5 rounded-full bg-marigold/70" />
            <span className="h-2.5 w-2.5 rounded-full bg-teal/70" />
            <span className="ml-3 text-sm font-medium text-slate">{text.mockTitle}</span>
            <span className="ml-auto inline-flex items-center gap-1.5 rounded-full bg-rose/10 px-2.5 py-0.5 text-xs font-semibold text-rose">
              <span className="live-dot h-1.5 w-1.5 rounded-full bg-rose" />
              LIVE
            </span>
          </div>
          <div className="grid gap-0 sm:grid-cols-[0.9fr_1.1fr]">
            <dl className="divide-y divide-line border-b border-line sm:border-b-0 sm:border-r">
              {text.mockFields.map((field) => (
                <div key={field.label} className="flex items-start justify-between gap-3 px-5 py-3.5">
                  <div>
                    <dt className="text-xs text-slate">{field.label}</dt>
                    <dd className="mt-0.5 font-medium text-ink">{field.value}</dd>
                  </div>
                  <span
                    className={`mt-1 shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${
                      field.valid ? "bg-teal/12 text-teal-deep" : "bg-marigold/15 text-marigold-deep"
                    }`}
                  >
                    {field.valid ? `✓ ${text.mockValid}` : `⚠ ${text.mockCheck}`}
                  </span>
                </div>
              ))}
            </dl>
            <ol className="flex flex-col gap-3 p-5">
              {text.mockTurns.map((turn) => (
                <li key={turn.time} className={`flex flex-col gap-1 ${turn.speaker === "caller" ? "items-end" : "items-start"}`}>
                  <span className="font-numeric text-[0.7rem] tabular-nums text-slate">{turn.time}</span>
                  <p
                    className={`max-w-[90%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${
                      turn.speaker === "caller" ? "rounded-br-sm bg-ink text-white" : "rounded-bl-sm bg-enamel text-ink"
                    }`}
                  >
                    {turn.text}
                  </p>
                </li>
              ))}
            </ol>
          </div>
        </figure>
      </div>
    </section>
  );
}
