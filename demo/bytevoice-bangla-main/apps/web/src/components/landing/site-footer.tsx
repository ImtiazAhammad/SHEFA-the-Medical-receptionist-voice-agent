"use client";

import Link from "next/link";
import { BrandMark } from "@/components/landing/brand-mark";
import { useLanguage } from "@/i18n/language-provider";

export function SiteFooter() {
  const { dictionary } = useLanguage();
  return (
    <footer className="bg-night text-enamel/70">
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-4 py-12 sm:px-6 md:flex-row md:items-end md:justify-between lg:px-8">
        <div className="max-w-md">
          <BrandMark />
          <p className="mt-4 text-sm leading-relaxed">{dictionary.footer.tagline}</p>
          <p className="mt-2 text-sm text-marigold/90">{dictionary.footer.disclaimer}</p>
        </div>
        <Link href="/portal" className="text-sm font-medium text-enamel underline-offset-4 hover:underline">
          {dictionary.footer.portal}
        </Link>
      </div>
    </footer>
  );
}
