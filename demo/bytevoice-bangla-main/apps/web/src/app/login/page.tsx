import type { Metadata } from "next";
import Link from "next/link";
import { BrandMark } from "@/components/landing/brand-mark";
import { LoginForm } from "@/app/login/login-form";
import { getSupabasePublicConfig } from "@/lib/env";

export const metadata: Metadata = {
  title: "Staff sign in",
  robots: { index: false, follow: false },
};

export default async function LoginPage({ searchParams }: PageProps<"/login">) {
  const parameters = await searchParams;
  const next = typeof parameters.next === "string" ? parameters.next : "/portal";
  const isConfigured = getSupabasePublicConfig() !== null;

  return (
    <main lang="en" className="grid min-h-screen font-sans lg:grid-cols-[1fr_1.1fr]">
      <section className="hero-backdrop grain relative hidden flex-col justify-between overflow-hidden p-10 text-enamel lg:flex">
        <Link href="/" aria-label="ByteVoice Bangla home">
          <BrandMark />
        </Link>
        <div className="relative max-w-md">
          <div aria-hidden className="poster-orb poster-breathe mb-10 h-40 w-40 rounded-full" />
          <p className="text-3xl font-bold leading-snug text-white">Every call Nila takes, organised for your front desk.</p>
          <p className="mt-4 text-enamel/70">
            Transcripts, extracted patient details, bookings and callback requests, updated live while the call is happening.
          </p>
        </div>
        <p className="text-sm text-enamel/50">Demo, not affiliated with One Smile Dental. All patient data is fake.</p>
      </section>
      <section className="flex items-center justify-center bg-enamel px-4 py-16 sm:px-8">
        <div className="w-full max-w-sm">
          <div className="mb-8 lg:hidden">
            <Link href="/" aria-label="ByteVoice Bangla home" className="inline-block rounded-xl bg-night px-3 py-2">
              <BrandMark />
            </Link>
          </div>
          <h1 className="text-2xl font-bold text-ink">Staff sign in</h1>
          <p className="mt-1 text-ink-soft">Use the reviewer credentials from the submission email.</p>
          {!isConfigured ? (
            <p role="alert" className="mt-6 rounded-xl border border-marigold/40 bg-marigold/10 px-4 py-3 text-sm text-marigold-deep">
              The portal is not connected to Supabase in this environment. Set NEXT_PUBLIC_SUPABASE_URL and
              NEXT_PUBLIC_SUPABASE_ANON_KEY to enable sign-in.
            </p>
          ) : null}
          <div className="mt-8">
            <LoginForm redirectTo={next} disabled={!isConfigured} />
          </div>
        </div>
      </section>
    </main>
  );
}
