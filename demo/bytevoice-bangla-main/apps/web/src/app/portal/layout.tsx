import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";
import { BrandMark } from "@/components/landing/brand-mark";
import { PortalNavigation } from "@/components/portal/portal-navigation";
import { getAuthenticatedContext } from "@/lib/supabase/server";
import { signOut } from "@/app/portal/actions";

export const metadata: Metadata = {
  title: "Staff portal",
  robots: { index: false, follow: false },
};

export const dynamic = "force-dynamic";

export default async function PortalLayout({ children }: { children: ReactNode }) {
  const authenticated = await getAuthenticatedContext();
  const email = authenticated?.user.email ?? "";

  return (
    <div lang="en" className="min-h-screen bg-enamel font-sans lg:grid lg:grid-cols-[15rem_1fr]">
      <aside className="sticky top-0 z-20 flex flex-col gap-4 bg-night px-4 py-4 text-enamel lg:h-screen lg:py-6">
        <div className="flex items-center justify-between gap-3">
          <Link href="/portal" aria-label="Portal home">
            <BrandMark />
          </Link>
          <form action={signOut} className="lg:hidden">
            <button type="submit" className="rounded-lg px-3 py-1.5 text-sm text-enamel/70 hover:text-white">
              Sign out
            </button>
          </form>
        </div>
        <p className="hidden text-xs leading-relaxed text-enamel/50 lg:block">
          One Smile Dental Lounge, Uttara
          <br />
          Demo, not affiliated
        </p>
        <PortalNavigation />
        <div className="mt-auto hidden flex-col gap-2 border-t border-night-line pt-4 lg:flex">
          <span className="truncate text-xs text-enamel/60" title={email}>
            {email}
          </span>
          <form action={signOut}>
            <button type="submit" className="text-sm font-medium text-enamel/80 hover:text-white">
              Sign out
            </button>
          </form>
          <Link href="/" className="text-sm text-enamel/60 hover:text-white">
            Back to the landing page
          </Link>
        </div>
      </aside>
      <div className="min-w-0">
        <div className="flex items-center gap-2 border-b border-marigold/30 bg-marigold/12 px-4 py-2 text-sm text-marigold-deep sm:px-8">
          <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-marigold" />
          Demo data — fake patients. All times are shown in Asia/Dhaka.
        </div>
        <main className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-8 sm:py-8">{children}</main>
      </div>
    </div>
  );
}
