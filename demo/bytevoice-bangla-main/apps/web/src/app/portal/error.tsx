"use client";

import { useEffect } from "react";
import { createLogger } from "@/lib/logger";

const logger = createLogger("portal.error-boundary");

export default function PortalError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    logger.error("Portal page crashed", { error, digest: error.digest });
  }, [error]);

  return (
    <div role="alert" className="rounded-2xl border border-rose/30 bg-rose/5 px-6 py-8">
      <p className="font-semibold text-rose">Something went wrong while loading this page.</p>
      <button type="button" onClick={reset} className="mt-4 rounded-full bg-ink px-4 py-2 text-sm font-semibold text-white">
        Try again
      </button>
    </div>
  );
}
