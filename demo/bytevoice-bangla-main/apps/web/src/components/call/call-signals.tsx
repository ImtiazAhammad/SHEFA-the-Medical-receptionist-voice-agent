"use client";

import { useLocalParticipant, useTrackVolume, useVoiceAssistant, type AgentState } from "@livekit/components-react";
import { LocalAudioTrack } from "livekit-client";
import { useEffect } from "react";

interface CallSignalsProps {
  onVolumes: (micVolume: number, agentVolume: number) => void;
  onAgentStateChange: (state: AgentState) => void;
}

export function CallSignals({ onVolumes, onAgentStateChange }: CallSignalsProps) {
  const { state, audioTrack } = useVoiceAssistant();
  const agentVolume = useTrackVolume(audioTrack);
  const { microphoneTrack } = useLocalParticipant();
  const localTrack = microphoneTrack?.track instanceof LocalAudioTrack ? microphoneTrack.track : undefined;
  const micVolume = useTrackVolume(localTrack);

  useEffect(() => {
    onVolumes(micVolume, agentVolume);
  }, [agentVolume, micVolume, onVolumes]);

  useEffect(() => {
    onAgentStateChange(state);
  }, [onAgentStateChange, state]);

  return null;
}
