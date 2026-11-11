"use client";

import { useRoomContext, useTranscriptions } from "@livekit/components-react";
import { useMemo } from "react";
import type { CaptionLine } from "@/types/call";

interface LiveCaptionsProps {
  agentLabel: string;
  callerLabel: string;
  placeholder: string;
}

export function LiveCaptions({ agentLabel, callerLabel, placeholder }: LiveCaptionsProps) {
  const room = useRoomContext();
  const transcriptions = useTranscriptions({ room });
  const localIdentity = room.localParticipant.identity;

  const lines = useMemo<CaptionLine[]>(() => {
    const ordered = [...transcriptions].sort((first, second) => first.streamInfo.timestamp - second.streamInfo.timestamp);
    const latestAgent = ordered.findLast((entry) => entry.participantInfo.identity !== localIdentity);
    const latestCaller = ordered.findLast((entry) => entry.participantInfo.identity === localIdentity);
    return [latestAgent, latestCaller]
      .filter((entry) => entry !== undefined && entry.text.trim().length > 0)
      .sort((first, second) => (first?.streamInfo.timestamp ?? 0) - (second?.streamInfo.timestamp ?? 0))
      .map((entry) => ({
        id: entry?.streamInfo.id ?? "",
        speaker: entry?.participantInfo.identity === localIdentity ? "caller" : "agent",
        text: entry?.text ?? "",
      }));
  }, [localIdentity, transcriptions]);

  return <CaptionList lines={lines} agentLabel={agentLabel} callerLabel={callerLabel} placeholder={placeholder} />;
}

interface CaptionListProps {
  lines: CaptionLine[];
  agentLabel: string;
  callerLabel: string;
  placeholder: string;
}

export function CaptionList({ lines, agentLabel, callerLabel, placeholder }: CaptionListProps) {
  return (
    <div aria-live="polite" className="flex min-h-[5.5rem] w-full flex-col justify-end gap-2 text-left">
      {lines.length === 0 ? (
        <p className="text-center text-sm text-mint/60">{placeholder}</p>
      ) : (
        lines.map((line, index) => (
          <p
            key={line.id}
            className={`line-clamp-2 text-[0.95rem] leading-relaxed transition-opacity ${
              index === lines.length - 1 ? "opacity-100" : "opacity-55"
            }`}
          >
            <span className={`mr-2 font-semibold ${line.speaker === "agent" ? "text-marigold" : "text-mint"}`}>
              {line.speaker === "agent" ? agentLabel : callerLabel}
            </span>
            <span className="text-enamel/90">{line.text}</span>
          </p>
        ))
      )}
    </div>
  );
}
