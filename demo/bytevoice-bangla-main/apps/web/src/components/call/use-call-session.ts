"use client";

import {
  DisconnectReason,
  isBrowserSupported,
  ParticipantKind,
  Room,
  RoomEvent,
  type RemoteParticipant,
} from "livekit-client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  AGENT_JOIN_TIMEOUT_MILLISECONDS,
  CALL_CAP_TOLERANCE_SECONDS,
  DATA_TOPIC_CALL,
  DATA_TOPIC_TOOL,
  LIVEKIT_TOKEN_ENDPOINT,
  MAX_CALL_SECONDS,
  MAX_TOOL_CHIPS,
  TOOL_CHIP_LIFETIME_MILLISECONDS,
} from "@/constants/call";
import { createLogger } from "@/lib/logger";
import { readTestedVisitorKey } from "@/lib/visitor-key-storage";
import { apiErrorSchema, callIdMessageSchema, toolEventMessageSchema } from "@/schemas/requests";
import type { TokenResponse } from "@/types/api";
import type { CallEndReason, CallErrorCode, CallPhase, ToolChip } from "@/types/call";
import type { Language } from "@/types/i18n";

const logger = createLogger("call.session");
const textDecoder = new TextDecoder();

class CallStartError extends Error {
  constructor(readonly code: CallErrorCode) {
    super(code);
    this.name = "CallStartError";
  }
}

function microphoneErrorCode(error: unknown): CallErrorCode {
  const name = error instanceof DOMException || error instanceof Error ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError") {
    return "mic_denied";
  }
  return "no_input_device";
}

async function ensureMicrophoneAccess(): Promise<void> {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    for (const track of stream.getTracks()) {
      track.stop();
    }
  } catch (error) {
    logger.warn("Microphone access failed", { error });
    throw new CallStartError(microphoneErrorCode(error));
  }
}

const VISITOR_KEY_FAILURE_CODES = new Set<string>([
  "invalid_api_key",
  "api_key_model_unavailable",
  "api_key_quota_exhausted",
  "api_key_test_failed",
]);

async function errorCodeOf(response: Response): Promise<string | null> {
  try {
    const parsed = apiErrorSchema.safeParse(await response.json());
    return parsed.success ? parsed.data.error.code : null;
  } catch {
    return null;
  }
}

async function requestToken(language: Language): Promise<TokenResponse> {
  const visitorKey = readTestedVisitorKey();
  let response: Response;
  try {
    response = await fetch(LIVEKIT_TOKEN_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(visitorKey ? { language, geminiApiKey: visitorKey } : { language }),
    });
  } catch (error) {
    logger.warn("Token request could not reach the server", { error });
    throw new CallStartError("network_lost");
  }
  if (response.status === 429) {
    throw new CallStartError("rate_limited");
  }
  if (!response.ok) {
    const code = await errorCodeOf(response);
    if (visitorKey && code && VISITOR_KEY_FAILURE_CODES.has(code)) {
      throw new CallStartError("invalid_api_key");
    }
    logger.warn("Token request rejected", { status: response.status });
    throw new CallStartError("agent_unavailable");
  }
  return (await response.json()) as TokenResponse;
}

function isAgentParticipant(participant: RemoteParticipant): boolean {
  return participant.kind === ParticipantKind.AGENT || participant.identity.startsWith("agent");
}

export interface CallSession {
  phase: CallPhase;
  errorCode: CallErrorCode | null;
  endReason: CallEndReason | null;
  room: Room | null;
  callId: string | null;
  toolChips: ToolChip[];
  isMuted: boolean;
  isReconnecting: boolean;
  isAudioBlocked: boolean;
  startedAt: number | null;
  start: (language: Language) => Promise<void>;
  end: () => Promise<void>;
  toggleMute: () => Promise<void>;
  enableAudio: () => Promise<void>;
  reset: () => void;
}

export function useCallSession(): CallSession {
  const [phase, setPhase] = useState<CallPhase>("idle");
  const [errorCode, setErrorCode] = useState<CallErrorCode | null>(null);
  const [endReason, setEndReason] = useState<CallEndReason | null>(null);
  const [room, setRoom] = useState<Room | null>(null);
  const [callId, setCallId] = useState<string | null>(null);
  const [toolChips, setToolChips] = useState<ToolChip[]>([]);
  const [isMuted, setIsMuted] = useState(false);
  const [isReconnecting, setIsReconnecting] = useState(false);
  const [isAudioBlocked, setIsAudioBlocked] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);

  const phaseRef = useRef<CallPhase>("idle");
  const roomRef = useRef<Room | null>(null);
  const startedAtRef = useRef<number | null>(null);
  const agentTimeoutRef = useRef<number | null>(null);
  const chipTimersRef = useRef<Set<number>>(new Set());

  const updatePhase = useCallback((next: CallPhase) => {
    phaseRef.current = next;
    setPhase(next);
  }, []);

  const clearAgentTimeout = useCallback(() => {
    if (agentTimeoutRef.current !== null) {
      window.clearTimeout(agentTimeoutRef.current);
      agentTimeoutRef.current = null;
    }
  }, []);

  const resolveEndReason = useCallback((fallback: CallEndReason): CallEndReason => {
    const started = startedAtRef.current;
    if (started !== null && (Date.now() - started) / 1000 >= MAX_CALL_SECONDS - CALL_CAP_TOLERANCE_SECONDS) {
      return "call_cap_reached";
    }
    return fallback;
  }, []);

  const finishCall = useCallback(
    (reason: CallEndReason) => {
      clearAgentTimeout();
      setEndReason(reason);
      setIsReconnecting(false);
      updatePhase("ended");
      const activeRoom = roomRef.current;
      if (activeRoom) {
        void activeRoom.disconnect();
      }
    },
    [clearAgentTimeout, updatePhase],
  );

  const failCall = useCallback(
    (code: CallErrorCode) => {
      clearAgentTimeout();
      setErrorCode(code);
      setIsReconnecting(false);
      updatePhase("error");
      const activeRoom = roomRef.current;
      roomRef.current = null;
      setRoom(null);
      if (activeRoom) {
        void activeRoom.disconnect();
      }
    },
    [clearAgentTimeout, updatePhase],
  );

  const markLive = useCallback(() => {
    if (phaseRef.current !== "connecting") {
      return;
    }
    clearAgentTimeout();
    const now = Date.now();
    startedAtRef.current = now;
    setStartedAt(now);
    updatePhase("live");
  }, [clearAgentTimeout, updatePhase]);

  const handleToolMessage = useCallback((payload: Uint8Array) => {
    const parsed = toolEventMessageSchema.safeParse(JSON.parse(textDecoder.decode(payload)));
    if (!parsed.success) {
      logger.debug("Ignored malformed tool message");
      return;
    }
    const chip: ToolChip = { ...parsed.data, id: `${parsed.data.tool}-${Date.now()}`, receivedAt: Date.now() };
    setToolChips((current) => {
      const withoutSameTool = current.filter((existing) => existing.tool !== chip.tool || existing.phase !== "start");
      return [...withoutSameTool, chip].slice(-MAX_TOOL_CHIPS);
    });
    if (chip.phase !== "start") {
      const timer = window.setTimeout(() => {
        chipTimersRef.current.delete(timer);
        setToolChips((current) => current.filter((existing) => existing.id !== chip.id));
      }, TOOL_CHIP_LIFETIME_MILLISECONDS);
      chipTimersRef.current.add(timer);
    }
  }, []);

  const handleCallMessage = useCallback((payload: Uint8Array) => {
    const parsed = callIdMessageSchema.safeParse(JSON.parse(textDecoder.decode(payload)));
    if (parsed.success) {
      setCallId(parsed.data.call_id);
    }
  }, []);

  const start = useCallback(
    async (language: Language) => {
      if (phaseRef.current === "requesting_mic" || phaseRef.current === "connecting" || phaseRef.current === "live") {
        return;
      }
      setErrorCode(null);
      setEndReason(null);
      setCallId(null);
      setToolChips([]);
      setIsMuted(false);
      setIsAudioBlocked(false);
      setStartedAt(null);
      startedAtRef.current = null;

      try {
        if (!isBrowserSupported() || !navigator.mediaDevices?.getUserMedia) {
          throw new CallStartError("unsupported_browser");
        }
        updatePhase("requesting_mic");
        await ensureMicrophoneAccess();

        updatePhase("connecting");
        const { serverUrl, participantToken } = await requestToken(language);

        const nextRoom = new Room({
          adaptiveStream: true,
          dynacast: true,
          audioCaptureDefaults: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        });
        roomRef.current = nextRoom;

        nextRoom
          .on(RoomEvent.DataReceived, (payload, _participant, _kind, topic) => {
            try {
              if (topic === DATA_TOPIC_TOOL) {
                handleToolMessage(payload);
              } else if (topic === DATA_TOPIC_CALL) {
                handleCallMessage(payload);
              }
            } catch (error) {
              logger.debug("Data message could not be parsed", { error, topic });
            }
          })
          .on(RoomEvent.ParticipantConnected, (participant) => {
            if (isAgentParticipant(participant)) {
              markLive();
            }
          })
          .on(RoomEvent.ParticipantDisconnected, (participant) => {
            if (isAgentParticipant(participant) && phaseRef.current === "live") {
              finishCall(resolveEndReason("agent_ended"));
            }
          })
          .on(RoomEvent.Reconnecting, () => setIsReconnecting(true))
          .on(RoomEvent.Reconnected, () => setIsReconnecting(false))
          .on(RoomEvent.AudioPlaybackStatusChanged, () => setIsAudioBlocked(!nextRoom.canPlaybackAudio))
          .on(RoomEvent.MediaDevicesError, (error) => {
            logger.warn("Media device error during call", { error });
          })
          .on(RoomEvent.Disconnected, (reason) => {
            if (phaseRef.current === "live") {
              const byServer = reason === DisconnectReason.ROOM_DELETED || reason === DisconnectReason.PARTICIPANT_REMOVED;
              if (byServer || reason === DisconnectReason.CLIENT_INITIATED) {
                finishCall(resolveEndReason("agent_ended"));
              } else {
                failCall("network_lost");
              }
            } else if (phaseRef.current === "connecting") {
              failCall("network_lost");
            }
          });

        await nextRoom.connect(serverUrl, participantToken);
        setRoom(nextRoom);

        try {
          await nextRoom.localParticipant.setMicrophoneEnabled(true);
        } catch (error) {
          logger.warn("Publishing the microphone failed", { error });
          throw new CallStartError(microphoneErrorCode(error));
        }

        try {
          await nextRoom.startAudio();
        } catch (error) {
          logger.debug("Audio playback needs a user gesture", { error });
        }
        setIsAudioBlocked(!nextRoom.canPlaybackAudio);

        const agentPresent = Array.from(nextRoom.remoteParticipants.values()).some(isAgentParticipant);
        if (agentPresent) {
          markLive();
        } else {
          agentTimeoutRef.current = window.setTimeout(() => {
            if (phaseRef.current === "connecting") {
              logger.warn("Agent did not join in time");
              failCall("agent_unavailable");
            }
          }, AGENT_JOIN_TIMEOUT_MILLISECONDS);
        }
      } catch (error) {
        if (error instanceof CallStartError) {
          logger.warn("Call could not start", { code: error.code });
          failCall(error.code);
          return;
        }
        logger.error("Call could not start", { error });
        failCall("agent_unavailable");
      }
    },
    [failCall, finishCall, handleCallMessage, handleToolMessage, markLive, resolveEndReason, updatePhase],
  );

  const end = useCallback(async () => {
    try {
      if (phaseRef.current === "connecting" || phaseRef.current === "requesting_mic") {
        clearAgentTimeout();
        updatePhase("idle");
        const activeRoom = roomRef.current;
        roomRef.current = null;
        setRoom(null);
        if (activeRoom) {
          await activeRoom.disconnect();
        }
        return;
      }
      finishCall("caller_hung_up");
    } catch (error) {
      logger.error("Ending the call failed", { error });
    }
  }, [clearAgentTimeout, finishCall, updatePhase]);

  const toggleMute = useCallback(async () => {
    const activeRoom = roomRef.current;
    if (!activeRoom) {
      return;
    }
    try {
      const nextMuted = !isMuted;
      await activeRoom.localParticipant.setMicrophoneEnabled(!nextMuted);
      setIsMuted(nextMuted);
    } catch (error) {
      logger.error("Toggling the microphone failed", { error });
    }
  }, [isMuted]);

  const enableAudio = useCallback(async () => {
    try {
      await roomRef.current?.startAudio();
      setIsAudioBlocked(!(roomRef.current?.canPlaybackAudio ?? true));
    } catch (error) {
      logger.warn("Audio playback still blocked", { error });
    }
  }, []);

  const reset = useCallback(() => {
    setErrorCode(null);
    setEndReason(null);
    setToolChips([]);
    updatePhase("idle");
  }, [updatePhase]);

  useEffect(() => {
    const timers = chipTimersRef.current;
    return () => {
      clearAgentTimeout();
      for (const timer of timers) {
        window.clearTimeout(timer);
      }
      const activeRoom = roomRef.current;
      roomRef.current = null;
      if (activeRoom) {
        void activeRoom.disconnect();
      }
    };
  }, [clearAgentTimeout]);

  return {
    phase,
    errorCode,
    endReason,
    room,
    callId,
    toolChips,
    isMuted,
    isReconnecting,
    isAudioBlocked,
    startedAt,
    start,
    end,
    toggleMute,
    enableAudio,
    reset,
  };
}
