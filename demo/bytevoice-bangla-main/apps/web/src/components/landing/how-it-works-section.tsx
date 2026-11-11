"use client";

import { useLanguage } from "@/i18n/language-provider";
import { toBanglaDigits } from "@/lib/format";

export function HowItWorksSection() {
  const { dictionary, language } = useLanguage();
  const text = dictionary.how;

  return (
    <section id="how-it-works" aria-labelledby="how-title" className="bg-paper">
      <div className="mx-auto w-full max-w-7xl px-4 py-20 sm:px-6 lg:px-8 lg:py-24">
        <h2 id="how-title" className="text-[clamp(1.9rem,3.6vw,2.9rem)] font-bold leading-tight text-ink">
          {text.title}
        </h2>
        <ol className="relative mt-12 grid gap-10 md:grid-cols-3 md:gap-8">
          <span aria-hidden className="absolute left-6 right-6 top-6 hidden h-px bg-line md:block" />
          {text.steps.map((step, index) => (
            <li key={step.title} className="relative">
              <span className="relative z-10 flex h-12 w-12 items-center justify-center rounded-full border-2 border-teal bg-paper text-lg font-bold text-teal-deep">
                {language === "bn" ? toBanglaDigits(index + 1) : index + 1}
              </span>
              <h3 className="mt-5 text-xl font-semibold text-ink">{step.title}</h3>
              <p className="mt-2 max-w-sm leading-relaxed text-ink-soft">{step.body}</p>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
