"use client";

import { useLanguage } from "@/i18n/language-provider";

export function UseCasesSection() {
  const { dictionary } = useLanguage();
  const text = dictionary.useCases;

  return (
    <section id="use-cases" aria-labelledby="use-cases-title" className="bg-paper">
      <div className="mx-auto w-full max-w-7xl px-4 py-20 sm:px-6 lg:px-8 lg:py-24">
        <h2 id="use-cases-title" className="text-[clamp(1.9rem,3.6vw,2.9rem)] font-bold leading-tight text-ink">
          {text.title}
        </h2>
        <ul className="mt-10 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {text.items.map((item) => (
            <li key={item.title} className="flex flex-col gap-4 border-t-2 border-teal pt-5">
              <h3 className="text-lg font-semibold text-ink">{item.title}</h3>
              <blockquote className="text-ink-soft">{item.quote}</blockquote>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
