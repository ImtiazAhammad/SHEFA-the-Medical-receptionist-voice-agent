"use client";

import { OwnKeyPanel } from "@/components/call/own-key-panel";
import Link from "next/link";
import { useSyncExternalStore } from "react";
import { CallTimer } from "@/components/call/call-timer";
import type { CallSession } from "@/components/call/use-call-session";
import { detectBrowser } from "@/lib/browser";
import type { BrowserName } from "@/types/call";
import type { Dictionary, Language } from "@/types/i18n";

interface CallControlsProps {
  session: CallSession;
  dictionary: Dictionary;
  language: Language;
}

function subscribeToNothing(): () => void {
  return () => undefined;
}

function useBrowserName(): BrowserName {
  return useSyncExternalStore(
    subscribeToNothing,
    () => detectBrowser(navigator.userAgent),
    () => "other",
  );
}

function PhoneIcon() {
  return (
    <svg aria-hidden viewBox="0 0 24 24" className="h-6 w-6">
      <path
        d="M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1z"
        fill="currentColor"
      />
    </svg>
  );
}

function MicrophoneIcon({ muted }: { muted: boolean }) {
  return (
    <svg aria-hidden viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
      {muted ? <path d="M4 4l16 16" /> : null}
    </svg>
  );
}

const primaryButton =
  "inline-flex items-center justify-center gap-3 rounded-full bg-marigold px-7 text-ink font-semibold shadow-[0_10px_40px_-10px_rgb(244_166_58/0.7)] transition hover:bg-[#ffb751] active:translate-y-px disabled:cursor-wait disabled:opacity-80";
const secondaryButton =
  "inline-flex h-12 items-center justify-center gap-2 rounded-full border border-night-line bg-night-raised px-5 text-sm font-medium text-enamel transition hover:border-mint/50";

export function CallControls({ session, dictionary, language }: CallControlsProps) {
  const browserName = useBrowserName();
  const callText = dictionary.call;

  if (session.phase === "live" || session.phase === "connecting" || session.phase === "requesting_mic") {
    const isLive = session.phase === "live";
    const pendingStatus = session.phase === "requesting_mic" ? callText.status.requesting_mic : callText.status.connecting;
    return (
      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-3">
          {isLive && session.startedAt !== null ? (
            <CallTimer startedAt={session.startedAt} language={language} />
          ) : (
            <span className="text-sm text-mint/80">{pendingStatus}</span>
          )}
          <div className="ml-auto flex items-center gap-2 sm:ml-6">
            <button
              type="button"
              onClick={() => void session.toggleMute()}
              disabled={!isLive}
              aria-pressed={session.isMuted}
              className={`${secondaryButton} disabled:opacity-40`}
            >
              <MicrophoneIcon muted={session.isMuted} />
              {session.isMuted ? callText.unmute : callText.mute}
            </button>
            <button
              type="button"
              onClick={() => void session.end()}
              className="inline-flex h-12 items-center gap-2 rounded-full bg-rose px-5 text-sm font-semibold text-white transition hover:bg-[#c94449]"
            >
              <span className="rotate-[135deg]">
                <PhoneIcon />
              </span>
              {callText.end}
            </button>
          </div>
        </div>
        {session.isReconnecting ? (
          <p role="status" className="rounded-xl border border-marigold/40 bg-marigold/10 px-4 py-2 text-sm text-marigold">
            {callText.reconnecting}
          </p>
        ) : null}
        {session.isAudioBlocked && isLive ? (
          <button type="button" onClick={() => void session.enableAudio()} className={secondaryButton}>
            {callText.enableAudio}
          </button>
        ) : null}
      </div>
    );
  }

  if (session.phase === "ended") {
    const detail =
      session.endReason === "call_cap_reached"
        ? callText.endedCap
        : session.endReason === "agent_ended"
          ? callText.endedByAgent
          : null;
    return (
      <div role="status" className="flex flex-col gap-4">
        <div>
          <p className="text-xl font-semibold text-enamel">{callText.endedTitle}</p>
          <p className="mt-1 max-w-md text-mint/80">
            {detail ? `${detail} ` : ""}
            {callText.endedBody}
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          {session.callId ? (
            <Link href={`/portal/calls/${session.callId}`} className={`${primaryButton} h-12`}>
              {callText.viewInPortal}
            </Link>
          ) : (
            <Link href="/portal/calls" className={`${primaryButton} h-12`}>
              {callText.viewInPortal}
            </Link>
          )}
          <button type="button" onClick={() => void session.start(language)} className={secondaryButton}>
            {callText.callAgain}
          </button>
        </div>
      </div>
    );
  }

  if (session.phase === "error" && session.errorCode) {
    const errorText = callText.errors[session.errorCode];
    return (
      <div role="alert" className="flex flex-col gap-4 rounded-2xl border border-rose/40 bg-rose/10 p-5">
        <div>
          <p className="text-lg font-semibold text-enamel">{errorText.title}</p>
          <p className="mt-1 text-mint/85">{errorText.body}</p>
          {session.errorCode === "mic_denied" ? (
            <p className="mt-3 rounded-lg bg-night/60 px-3 py-2 text-sm text-enamel/85">{callText.micTips[browserName]}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap gap-3">
          {session.errorCode !== "unsupported_browser" ? (
            <button type="button" onClick={() => void session.start(language)} className={`${primaryButton} h-12`}>
              {callText.retry}
            </button>
          ) : null}
          <button type="button" onClick={session.reset} className={secondaryButton}>
            {callText.dismiss}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-start gap-3">
      <button type="button" onClick={() => void session.start(language)} className={`${primaryButton} h-16 text-lg sm:text-xl`}>
        <PhoneIcon />
        {dictionary.hero.cta}
      </button>
      <p className="text-sm text-mint/70">{dictionary.hero.ctaHint}</p>
      <OwnKeyPanel />
    </div>
  );
}
