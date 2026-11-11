import type { z } from "zod";
import type { callIdMessageSchema, toolEventMessageSchema } from "@/schemas/requests";

export type CallPhase = "idle" | "requesting_mic" | "connecting" | "live" | "ended" | "error";

export type CallErrorCode =
  | "mic_denied"
  | "no_input_device"
  | "agent_unavailable"
  | "network_lost"
  | "unsupported_browser"
  | "rate_limited"
  | "invalid_api_key";

export type CallEndReason = "caller_hung_up" | "agent_ended" | "call_cap_reached";

export type OrbMode = "idle" | "connecting" | "listening" | "speaking" | "ended";

export type ToolEventMessage = z.infer<typeof toolEventMessageSchema>;
export type CallIdMessage = z.infer<typeof callIdMessageSchema>;

export interface ToolChip extends ToolEventMessage {
  id: string;
  receivedAt: number;
}

export interface CaptionLine {
  id: string;
  speaker: "agent" | "caller";
  text: string;
}

export type BrowserName = "chrome" | "safari" | "firefox" | "edge" | "other";

export interface OrbSignal {
  mode: OrbMode;
  micVolume: number;
  agentVolume: number;
}
