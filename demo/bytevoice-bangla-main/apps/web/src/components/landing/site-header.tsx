"use client";

import Link from "next/link";
import { BrandMark } from "@/components/landing/brand-mark";
import { useLanguage } from "@/i18n/language-provider";

export function SiteHeader() {
  const { dictionary, toggleLanguage } = useLanguage();
  const links = [
    { href: "#meet-nila", label: dictionary.nav.meetNila },
    { href: "#how-it-works", label: dictionary.nav.howItWorks },
    { href: "#features", label: dictionary.nav.features },
    { href: "#use-cases", label: dictionary.nav.useCases },
    { href: "#contact", label: dictionary.nav.contact },
  ];

  return (
    <header className="relative z-10 mx-auto flex w-full max-w-7xl items-center gap-6 px-4 py-5 sm:px-6 lg:px-8">
      <Link href="/" aria-label="ByteVoice Bangla">
        <BrandMark />
      </Link>
      <nav aria-label="Sections" className="hidden flex-1 justify-center gap-7 text-sm text-enamel/70 lg:flex">
        {links.map((link) => (
          <a key={link.href} href={link.href} className="transition hover:text-white">
            {link.label}
          </a>
        ))}
      </nav>
      <div className="ml-auto flex items-center gap-2 lg:ml-0">
        <button
          type="button"
          onClick={toggleLanguage}
          aria-label={dictionary.meta.switchLabel}
          className="h-9 rounded-full border border-night-line px-4 text-sm font-medium text-enamel transition hover:border-mint/60"
        >
          {dictionary.meta.switchTo}
        </button>
        <Link
          href="/portal"
          className="hidden h-9 items-center rounded-full bg-enamel/10 px-4 text-sm font-medium text-enamel transition hover:bg-enamel/20 sm:inline-flex"
        >
          {dictionary.nav.portal}
        </Link>
      </div>
    </header>
  );
}
