"use client";

import { useActionState } from "react";
import { resolveCallback } from "@/app/portal/actions";
import type { ActionState } from "@/types/portal";

const INITIAL_STATE: ActionState = { status: "idle", message: "" };

export function ResolveCallbackButton({ callbackId }: { callbackId: string }) {
  const [state, formAction, isPending] = useActionState(resolveCallback, INITIAL_STATE);
  return (
    <form action={formAction} className="flex flex-col items-end gap-1">
      <input type="hidden" name="callbackId" value={callbackId} />
      <button
        type="submit"
        disabled={isPending}
        className="inline-flex h-9 items-center rounded-full bg-ink px-4 text-sm font-semibold text-white transition hover:bg-teal-deep disabled:cursor-wait disabled:opacity-60"
      >
        {isPending ? "Saving…" : "Mark done"}
      </button>
      {state.status === "error" ? (
        <span role="alert" className="text-xs text-rose">
          {state.message}
        </span>
      ) : null}
    </form>
  );
}
