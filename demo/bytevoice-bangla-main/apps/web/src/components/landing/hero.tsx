"use client";

import { RoomAudioRenderer, RoomContext, type AgentState } from "@livekit/components-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { CallControls } from "@/components/call/call-controls";
import { CallSignals } from "@/components/call/call-signals";
import { CaptionList, LiveCaptions } from "@/components/call/live-captions";
import { ToolChips } from "@/components/call/tool-chips";
import { useCallSession } from "@/components/call/use-call-session";
import { SiteHeader } from "@/components/landing/site-header";
import { CallOrb } from "@/components/orb/call-orb";
import { useLanguage } from "@/i18n/language-provider";
import type { CallPhase, OrbMode, OrbSignal } from "@/types/call";
import type { Dictionary } from "@/types/i18n";

function orbModeFor(phase: CallPhase, agentState: AgentState): OrbMode {
  if (phase === "requesting_mic" || phase === "connecting") {
    return "connecting";
  }
  if (phase === "live") {
    return agentState === "speaking" ? "speaking" : "listening";
  }
  if (phase === "ended") {
    return "ended";
  }
  return "idle";
}

function statusText(dictionary: Dictionary, phase: CallPhase, agentState: AgentState): string {
  const status = dictionary.call.status;
  if (phase === "live") {
    if (agentState === "speaking") {
      return status.speaking;
    }
    if (agentState === "thinking") {
      return status.thinking;
    }
    return status.listening;
  }
  if (phase === "requesting_mic" || phase === "connecting" || phase === "ended") {
    return status[phase];
  }
  return status.idle;
}

export function Hero() {
  const { dictionary, language } = useLanguage();
  const session = useCallSession();
  const [agentState, setAgentState] = useState<AgentState>("disconnected");
  const signalRef = useRef<OrbSignal>({ mode: "idle", micVolume: 0, agentVolume: 0 });

  const orbMode = orbModeFor(session.phase, agentState);

  useEffect(() => {
    signalRef.current.mode = orbMode;
  }, [orbMode]);

  const handleVolumes = useCallback((micVolume: number, agentVolume: number) => {
    signalRef.current.micVolume = micVolume;
    signalRef.current.agentVolume = agentVolume;
  }, []);

  const isLiveLike = session.phase === "live" || session.phase === "connecting";
  const hasRoom = session.room !== null && session.phase !== "idle" && session.phase !== "error";

  return (
    <section className="hero-backdrop grain relative isolate overflow-hidden text-enamel">
      <SiteHeader />
      <div className="mx-auto grid w-full max-w-7xl grid-cols-1 gap-x-12 gap-y-6 px-4 pb-16 pt-6 sm:px-6 lg:grid-cols-[1.1fr_0.9fr] lg:px-8 lg:pb-24 lg:pt-14">
        <div className="lg:col-start-1 lg:row-start-1 lg:self-end">
          <p className="flex items-center gap-2 text-sm text-mint/80">
            <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-marigold" />
            {dictionary.hero.clinicLine}
          </p>
          <h1 className="mt-5 max-w-[15ch] text-[clamp(2.35rem,6.2vw,4.6rem)] font-bold leading-[1.14] tracking-[-0.01em] text-white">
            {dictionary.hero.headline}
          </h1>
          <p className="mt-5 max-w-[38rem] text-base leading-relaxed text-enamel/75 sm:mt-6 sm:text-xl">{dictionary.hero.subline}</p>
        </div>

        <div className="mx-auto flex w-full flex-col items-center lg:col-start-2 lg:row-start-1 lg:self-end">
          <div className="w-full max-w-[15rem] sm:max-w-[24rem] lg:max-w-[32rem]">
            <CallOrb signalRef={signalRef} mode={orbMode} />
          </div>
          <p className="-mt-6 flex items-center gap-2 text-sm font-medium text-mint sm:-mt-8" aria-live="polite">
            <span
              aria-hidden
              className={`h-2 w-2 rounded-full ${
                session.phase === "live" ? "live-dot bg-rose" : isLiveLike ? "live-dot bg-marigold" : "bg-mint/60"
              }`}
            />
            {statusText(dictionary, session.phase, agentState)}
          </p>
        </div>

        <div className="mx-auto w-full max-w-[28rem] max-lg:order-last lg:col-start-2 lg:row-start-2 lg:self-start">
          <div className="rounded-2xl border border-night-line/80 bg-night-raised/60 px-5 py-4 backdrop-blur-sm">
            {hasRoom && session.room ? (
              <RoomContext.Provider value={session.room}>
                <RoomAudioRenderer />
                <CallSignals onVolumes={handleVolumes} onAgentStateChange={setAgentState} />
                <LiveCaptions
                  agentLabel={dictionary.call.agentName}
                  callerLabel={dictionary.call.caller}
                  placeholder={dictionary.call.captionsPlaceholder}
                />
              </RoomContext.Provider>
            ) : (
              <CaptionList
                lines={[]}
                agentLabel={dictionary.call.agentName}
                callerLabel={dictionary.call.caller}
                placeholder={dictionary.call.captionsPlaceholder}
              />
            )}
          </div>
          <div className="mt-3">
            <ToolChips chips={session.toolChips} language={language} />
          </div>
        </div>

        <div className="lg:col-start-1 lg:row-start-2 lg:self-start">
          <CallControls session={session} dictionary={dictionary} language={language} />
          {session.phase === "idle" ? (
            <ul className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-enamel/60">
              {dictionary.hero.notes.map((note) => (
                <li key={note} className="flex items-center gap-2">
                  <svg aria-hidden viewBox="0 0 16 16" className="h-3.5 w-3.5 text-teal">
                    <path d="M3 8.5 6.5 12 13 4.5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  {note}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </section>
  );
}
