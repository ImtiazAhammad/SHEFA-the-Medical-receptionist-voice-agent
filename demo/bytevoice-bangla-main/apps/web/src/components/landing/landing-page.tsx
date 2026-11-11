"use client";

import { ContactSection } from "@/components/landing/contact-section";
import { FeaturesSection } from "@/components/landing/features-section";
import { Hero } from "@/components/landing/hero";
import { HowItWorksSection } from "@/components/landing/how-it-works-section";
import { PersonaSection } from "@/components/landing/persona-section";
import { PortalPreviewSection } from "@/components/landing/portal-preview-section";
import { ProblemSection } from "@/components/landing/problem-section";
import { SiteFooter } from "@/components/landing/site-footer";
import { UseCasesSection } from "@/components/landing/use-cases-section";
import { LanguageProvider } from "@/i18n/language-provider";

export function LandingPage() {
  return (
    <LanguageProvider>
      <main>
        <Hero />
        <PersonaSection />
        <ProblemSection />
        <HowItWorksSection />
        <FeaturesSection />
        <UseCasesSection />
        <PortalPreviewSection />
        <ContactSection />
      </main>
      <SiteFooter />
    </LanguageProvider>
  );
}
