"use client";

import { useState, useSyncExternalStore, type FormEvent } from "react";
import { VISITOR_KEY_TEST_ENDPOINT } from "@/constants/call";
import { useLanguage } from "@/i18n/language-provider";
import { createLogger } from "@/lib/logger";
import { forgetVisitorKey, readTestedVisitorKey, saveTestedVisitorKey } from "@/lib/visitor-key-storage";
import { apiErrorSchema } from "@/schemas/requests";

const logger = createLogger("own-key-panel");
const listeners = new Set<() => void>();

type FailureKey = "invalid_api_key" | "api_key_model_unavailable" | "api_key_quota_exhausted" | "api_key_test_failed" | "rate_limited";
const FAILURE_KEYS = new Set<string>([
  "invalid_api_key",
  "api_key_model_unavailable",
  "api_key_quota_exhausted",
  "api_key_test_failed",
  "rate_limited",
]);

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function notify(): void {
  for (const listener of listeners) {
    listener();
  }
}

function maskKey(apiKey: string): string {
  return `${apiKey.slice(0, 4)}…${apiKey.slice(-4)}`;
}

async function testKey(apiKey: string): Promise<FailureKey | null> {
  try {
    const response = await fetch(VISITOR_KEY_TEST_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ apiKey }),
    });
    if (response.ok) {
      return null;
    }
    const parsed = apiErrorSchema.safeParse(await response.json());
    const code = parsed.success ? parsed.data.error.code : "api_key_test_failed";
    return FAILURE_KEYS.has(code) ? (code as FailureKey) : "api_key_test_failed";
  } catch (error) {
    logger.warn("Key test request failed", { error: error instanceof Error ? error.name : "unknown" });
    return "api_key_test_failed";
  }
}

export function OwnKeyPanel() {
  const { dictionary } = useLanguage();
  const text = dictionary.call.ownKey;
  const testedKey = useSyncExternalStore(subscribe, readTestedVisitorKey, () => null);
  const [draft, setDraft] = useState("");
  const [isTesting, setIsTesting] = useState(false);
  const [failure, setFailure] = useState<FailureKey | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const candidate = draft.trim();
    if (!candidate || isTesting) {
      return;
    }
    setIsTesting(true);
    setFailure(null);
    const result = await testKey(candidate);
    setIsTesting(false);
    if (result) {
      setFailure(result);
      return;
    }
    saveTestedVisitorKey(candidate);
    setDraft("");
    notify();
  }

  function handleRemove(): void {
    forgetVisitorKey();
    setFailure(null);
    notify();
  }

  return (
    <details className="group w-full max-w-md rounded-2xl border border-night-line/70 bg-night/40 px-4 py-3 text-sm text-mint/80" open={Boolean(testedKey)}>
      <summary className="cursor-pointer select-none font-medium text-enamel/90 marker:text-mint/60">{text.toggle}</summary>
      {testedKey ? (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
          <p className="flex items-center gap-2 text-mint">
            <span className="h-2 w-2 rounded-full bg-teal" aria-hidden />
            {text.active} <span className="font-mono text-xs text-enamel/70">({maskKey(testedKey)})</span>
          </p>
          <button type="button" onClick={handleRemove} className="rounded-full border border-mint/40 px-3 py-1 text-xs font-semibold text-mint hover:bg-mint/10">
            {text.remove}
          </button>
        </div>
      ) : (
        <form onSubmit={(event) => void handleSubmit(event)} className="mt-3 flex flex-col gap-2">
          <p className="leading-relaxed">{text.body}</p>
          <label className="text-xs font-semibold uppercase tracking-wide text-mint/70" htmlFor="visitor-gemini-key">
            {text.label}
          </label>
          <div className="flex gap-2">
            <input
              id="visitor-gemini-key"
              type="password"
              autoComplete="off"
              spellCheck={false}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              placeholder={text.placeholder}
              className="min-w-0 flex-1 rounded-xl border border-night-line bg-night px-3 py-2 font-mono text-enamel placeholder:text-slate focus:border-teal focus:outline-none"
            />
            <button
              type="submit"
              disabled={isTesting || !draft.trim()}
              className="shrink-0 rounded-xl bg-teal px-4 py-2 font-semibold text-night transition hover:bg-mint disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isTesting ? text.testing : text.test}
            </button>
          </div>
          {failure ? (
            <p role="alert" className="text-rose">
              {text.failures[failure]}
            </p>
          ) : null}
          <p className="text-xs text-slate">{text.privacy}</p>
        </form>
      )}
    </details>
  );
}
