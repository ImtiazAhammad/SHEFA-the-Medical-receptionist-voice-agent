"use client";

import { useActionState } from "react";
import { signIn } from "@/app/login/actions";
import type { ActionState } from "@/types/portal";

const INITIAL_STATE: ActionState = { status: "idle", message: "" };

const inputClass =
  "mt-1.5 block w-full rounded-xl border border-line bg-white px-4 py-3 text-ink transition focus:border-teal focus:outline-none focus:ring-2 focus:ring-teal/25";

export function LoginForm({ redirectTo, disabled }: { redirectTo: string; disabled: boolean }) {
  const [state, formAction, isPending] = useActionState(signIn, INITIAL_STATE);

  return (
    <form action={formAction} className="flex flex-col gap-4">
      <input type="hidden" name="redirectTo" value={redirectTo} />
      <label className="text-sm font-medium text-ink">
        Email
        <input name="email" type="email" required autoComplete="username" className={inputClass} disabled={disabled} />
      </label>
      <label className="text-sm font-medium text-ink">
        Password
        <input
          name="password"
          type="password"
          required
          autoComplete="current-password"
          className={inputClass}
          disabled={disabled}
        />
      </label>
      {state.status === "error" ? (
        <p role="alert" className="rounded-lg bg-rose/10 px-3 py-2 text-sm text-rose">
          {state.message}
        </p>
      ) : null}
      <button
        type="submit"
        disabled={isPending || disabled}
        className="mt-2 inline-flex h-12 items-center justify-center rounded-full bg-ink font-semibold text-white transition hover:bg-teal-deep disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isPending ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
