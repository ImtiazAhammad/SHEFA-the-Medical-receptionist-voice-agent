"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { createLogger } from "@/lib/logger";
import type { ApiErrorResponse } from "@/types/api";

const logger = createLogger("portal.reprocess");

type ReprocessState = { status: "idle" | "running" | "done" | "error"; message: string };

export function ReprocessButton({ callId, disabled }: { callId: string; disabled: boolean }) {
  const router = useRouter();
  const [state, setState] = useState<ReprocessState>({ status: "idle", message: "" });

  async function handleClick() {
    setState({ status: "running", message: "" });
    try {
      const response = await fetch(`/api/calls/${callId}/reprocess`, { method: "POST" });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as ApiErrorResponse | null;
        setState({ status: "error", message: body?.error.message ?? `Request failed (${response.status}).` });
        return;
      }
      setState({ status: "done", message: "Reprocessing started. Results refresh automatically." });
      router.refresh();
    } catch (error) {
      logger.error("Reprocess request failed", { error });
      setState({ status: "error", message: "Could not reach the server." });
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={() => void handleClick()}
        disabled={disabled || state.status === "running"}
        title={disabled ? "Available once the call has ended" : "Re-run extraction, summary and translation"}
        className="inline-flex h-10 items-center gap-2 rounded-full border border-line bg-paper px-4 text-sm font-semibold text-ink transition hover:border-teal disabled:cursor-not-allowed disabled:opacity-50"
      >
        <svg aria-hidden viewBox="0 0 24 24" className={`h-4 w-4 ${state.status === "running" ? "animate-spin" : ""}`} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
          <path d="M20 12a8 8 0 1 1-2.34-5.66M20 4v4h-4" />
        </svg>
        {state.status === "running" ? "Reprocessing…" : "Reprocess"}
      </button>
      {state.message ? (
        <span role={state.status === "error" ? "alert" : "status"} className={`text-xs ${state.status === "error" ? "text-rose" : "text-teal-deep"}`}>
          {state.message}
        </span>
      ) : null}
    </div>
  );
}
