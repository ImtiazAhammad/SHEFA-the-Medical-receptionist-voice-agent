// The reviewer page's rules, kept free of the DOM so they can be checked in Node.
//
// The most important rule: the screen is chosen from item.mode ONLY. We never look at whether a
// field happens to be filled in, because the server can send a draft for a mode that must not show
// one (an "adjudicate" clip from the training pool carries its machine draft). And "blind" and
// "seed" must be indistinguishable, so both map to the same view and nothing downstream may ever
// see the original mode name, the clip's split or the status in the submit reply.

export const REJECT_FLAGS = ["unusable", "other_language", "personal_details", "offensive"];
export const KEPT_FLAGS = ["noisy", "unclear"];
export const MAX_TEXT = 600; // server limit on the typed text

/** Which screen to draw, and what goes in the text box at first. */
export function viewFor(item) {
  const mode = item && item.mode;
  if (mode === "draft") {
    const draft = typeof item.draft === "string" ? item.draft : "";
    return { ui: "draft", prefill: draft, noDraft: draft === "", expected: "", candidates: [] };
  }
  if (mode === "verify") {
    const expected = typeof item.expected === "string" ? item.expected : "";
    // Without an expected text there is nothing to confirm: fall back to plain typing.
    if (!expected) return { ui: "type", prefill: "", noDraft: false, expected: "", candidates: [] };
    return { ui: "verify", prefill: expected, noDraft: false, expected, candidates: [] };
  }
  if (mode === "adjudicate") {
    const candidates = Array.isArray(item.candidates)
      ? item.candidates.map((c) => ({ text: String((c && c.text) || ""), flags: Array.isArray(c && c.flags) ? c.flags.map(String) : [] }))
      : [];
    return { ui: "adjudicate", prefill: "", noDraft: false, expected: "", candidates };
  }
  // blind, seed, and anything unknown: a clean box, no hints. Same view for all of them.
  return { ui: "type", prefill: "", noDraft: false, expected: "", candidates: [] };
}

export function isRejecting(flags) {
  return flags.some((flag) => REJECT_FLAGS.includes(flag));
}

/** How much of the clip must have been played before a transcript is accepted (anchoring guard). */
export function heardEnough(heardSeconds, durationSeconds) {
  const duration = Number(durationSeconds) || 0;
  if (duration <= 0) return true; // unknown length: do not block
  const needed = Math.min(duration * 0.7, Math.max(duration - 0.6, 0.3));
  return heardSeconds >= needed;
}

/** Seconds spent on this clip, capped so a forgotten tab does not skew the numbers. */
export function secondsSpent(startedMs, nowMs) {
  const seconds = Math.max(0, (nowMs - startedMs) / 1000);
  return Math.round(Math.min(seconds, 900) * 10) / 10;
}

/** Map a server error to a string key (the server's own messages are English only). */
export function submitErrorKey(error) {
  switch (error && error.code) {
    case "empty": return "rv_err_empty";
    case "no_bangla": return "rv_err_no_bangla";
    case "slow_down": return "err_slow_down";
    case "network": return "err_network";
    case "invalid": return "rv_err_invalid";
    default: return "err_generic";
  }
}

/** Errors after which the right move is simply to fetch the next clip. */
export function skipsToNext(error) {
  return !!error && (error.code === "already" || error.code === "no_clip" || error.status === 404 || error.status === 409);
}

/** The server's notes are English sentences; known ones get a Bangla key, others show as sent. */
const KNOWN_NOTES = {
  "digits were written as words (phone numbers stay as digits)": "note_digits",
};
export function noteKey(note) { return KNOWN_NOTES[note] || ""; }

/** Build the POST body. Rejecting flags need no text; text is trimmed and limited. */
export function buildSubmission({ clipId, text, flags, seconds }) {
  const unique = [...new Set(flags)];
  return { clip_id: clipId, text: String(text || "").slice(0, MAX_TEXT), flags: unique, seconds };
}
