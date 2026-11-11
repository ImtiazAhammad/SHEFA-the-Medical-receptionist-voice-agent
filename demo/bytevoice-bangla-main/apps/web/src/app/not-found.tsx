import Link from "next/link";

export default function NotFound() {
  return (
    <main lang="en" className="flex min-h-screen flex-col items-center justify-center gap-4 bg-enamel px-4 text-center font-sans">
      <div aria-hidden className="poster-orb h-24 w-24 rounded-full" data-mode="ended" />
      <h1 className="text-2xl font-bold text-ink">This page does not exist</h1>
      <p className="text-ink-soft">The link may be wrong, or the call may have been removed.</p>
      <div className="flex gap-3">
        <Link href="/" className="rounded-full bg-ink px-5 py-2.5 text-sm font-semibold text-white">Landing page</Link>
        <Link href="/portal" className="rounded-full border border-line px-5 py-2.5 text-sm font-semibold text-ink">Staff portal</Link>
      </div>
    </main>
  );
}
