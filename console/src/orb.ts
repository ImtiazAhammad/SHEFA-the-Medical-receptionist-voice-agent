// Orb lifecycle for a live call.
//
// Every rule here traces to one constraint: this animation runs while the
// operator is on a phone call and driving a clinical workflow. Motion here is
// not free, so it is gated rather than assumed.

// A call's phases, mapped to the nine shipped orb states. `listening` is the
// only steady state — the agent's turn-taking needs a calm indicator, not a
// busy one.
export type CallPhase =
  | 'idle'
  | 'connecting'
  | 'listening'
  | 'thinking'
  | 'speaking'
  | 'ended';

export const ORB_STATE = {
  connecting: 'connecting',
  listening: 'listening',
  thinking: 'searching',
  speaking: 'weaving',
} as const;

// The operator can turn motion off for good (accessibility, or a low-end
// handset where a live canvas loop shows up in the battery trace).
export const MOTION_PREF_KEY = 'shefa.motion';

export function motionAllowed(): boolean {
  if (typeof window === 'undefined') return false;
  if (localStorage.getItem(MOTION_PREF_KEY) === 'off') return false;
  return !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export function setMotion(allowed: boolean): void {
  localStorage.setItem(MOTION_PREF_KEY, allowed ? 'on' : 'off');
}