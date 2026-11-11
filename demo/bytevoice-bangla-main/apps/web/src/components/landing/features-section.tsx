"use client";

import type { ReactNode } from "react";
import { useLanguage } from "@/i18n/language-provider";

const FEATURE_ICONS: ReactNode[] = [
  <path key="speech" d="M4 5h16v10H9l-5 4z" />,
  <path key="digits" d="M6 4h.01M12 4h.01M18 4h.01M6 10h.01M12 10h.01M18 10h.01M6 16h.01M12 16h.01M18 16h.01M12 21h.01" strokeWidth="3.2" />,
  <path key="shield" d="M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6zM9 12l2 2 4-4" />,
  <path key="handover" d="M7 11V6a2 2 0 1 1 4 0v5M11 9V5a2 2 0 1 1 4 0v6M15 10a2 2 0 1 1 4 0v3a8 8 0 0 1-8 8H9a5 5 0 0 1-4-2l-2-3" />,
  <path key="portal" d="M3 5h18v14H3zM3 9h18M8 13h5M8 16h8" />,
];

export function FeaturesSection() {
  const { dictionary } = useLanguage();
  const text = dictionary.features;
  const [lead, ...rest] = text.items;

  return (
    <section id="features" aria-labelledby="features-title" className="mx-auto w-full max-w-7xl px-4 py-20 sm:px-6 lg:px-8 lg:py-28">
      <h2 id="features-title" className="max-w-2xl text-[clamp(1.9rem,3.6vw,2.9rem)] font-bold leading-tight text-ink">
        {text.title}
      </h2>
      <div className="mt-12 grid gap-px overflow-hidden rounded-3xl border border-line bg-line lg:grid-cols-3">
        {lead ? (
          <article className="flex flex-col justify-between gap-10 bg-night p-8 text-enamel lg:row-span-2 lg:p-10">
            <FeatureIcon index={0} light />
            <div>
              <h3 className="text-2xl font-semibold text-white">{lead.title}</h3>
              <p className="mt-3 text-lg leading-relaxed text-enamel/75">{lead.body}</p>
            </div>
          </article>
        ) : null}
        {rest.map((item, index) => (
          <article key={item.title} className="flex flex-col gap-6 bg-paper p-8">
            <FeatureIcon index={index + 1} />
            <div>
              <h3 className="text-lg font-semibold text-ink">{item.title}</h3>
              <p className="mt-2 leading-relaxed text-ink-soft">{item.body}</p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

function FeatureIcon({ index, light = false }: { index: number; light?: boolean }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      className={`h-7 w-7 ${light ? "text-marigold" : "text-teal-deep"}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {FEATURE_ICONS[index]}
    </svg>
  );
}
