"use client";

import { useLanguage } from "@/i18n/language-provider";

export function ProblemSection() {
  const { dictionary } = useLanguage();
  const text = dictionary.problem;

  return (
    <section aria-labelledby="problem-title" className="mx-auto w-full max-w-7xl px-4 py-20 sm:px-6 lg:px-8 lg:py-28">
      <div className="grid gap-10 lg:grid-cols-[0.8fr_1.2fr] lg:gap-16">
        <div className="lg:sticky lg:top-12 lg:self-start">
          <h2 id="problem-title" className="text-[clamp(1.9rem,3.6vw,2.9rem)] font-bold leading-tight text-ink">
            {text.title}
          </h2>
          <p className="mt-4 max-w-md text-lg leading-relaxed text-ink-soft">{text.intro}</p>
        </div>
        <div>
          <div className="hidden grid-cols-2 gap-8 border-b border-line pb-3 text-sm font-semibold text-slate sm:grid">
            <span>{text.todayLabel}</span>
            <span className="text-teal-deep">{text.fixLabel}</span>
          </div>
          <ul>
            {text.rows.map((row) => (
              <li key={row.problem} className="grid gap-3 border-b border-line py-6 sm:grid-cols-2 sm:gap-8">
                <p className="text-ink-soft">
                  <span className="mb-1 block text-xs font-semibold text-slate sm:hidden">{text.todayLabel}</span>
                  {row.problem}
                </p>
                <p className="flex gap-3 font-medium text-ink">
                  <svg aria-hidden viewBox="0 0 16 16" className="mt-1.5 h-4 w-4 shrink-0 text-teal">
                    <path d="M3 8.5 6.5 12 13 4.5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  {row.fix}
                </p>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}
