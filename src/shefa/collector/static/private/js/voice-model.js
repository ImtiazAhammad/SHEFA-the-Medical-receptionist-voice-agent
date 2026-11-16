// Voice packs: the rules of the "record the desk's lines" page and the admin's voices tab, kept
// free of the DOM so they can be checked in Node. The server is the judge (api.py voice_put);
// these only mirror its limits so a person learns early what will be refused.

/** The server refuses under 1 s and over 30 s. Stop a little before 30 so a late tap is safe. */
export const MIN_LINE_S = 1.0;
export const MAX_LINE_S = 29.5;
export const COUNTDOWN_S = 5;

/** Openings first: they are what every call starts with, so they matter most. */
export const GROUP_ORDER = ["opening", "question", "closing", "doctors"];

/** [[group, [line, ...]], ...] in GROUP_ORDER, unknown groups last, server order kept inside a group. */
export function groupLines(lines) {
  const groups = new Map();
  for (const line of Array.isArray(lines) ? lines : []) {
    const group = String((line && line.group) || "other");
    if (!groups.has(group)) groups.set(group, []);
    groups.get(group).push(line);
  }
  const known = GROUP_ORDER.filter((g) => groups.has(g)).map((g) => [g, groups.get(g)]);
  const rest = [...groups.keys()].filter((g) => !GROUP_ORDER.includes(g)).map((g) => [g, groups.get(g)]);
  return [...known, ...rest];
}

export function progressOf(lines) {
  const list = Array.isArray(lines) ? lines : [];
  const done = list.filter((line) => line && line.recorded).length;
  const openings = list.filter((line) => line && line.group === "opening");
  return {
    done,
    total: list.length,
    pct: list.length ? (done / list.length) * 100 : 0,
    openingsDone: openings.filter((line) => line.recorded).length,
    openingsTotal: openings.length,
  };
}

/** Why an upload was refused, as a string key. The server's own message is Bangla only. */
export function uploadErrorKey(error) {
  const reason = error && error.reason;
  if (reason && ["too_short", "too_long", "silent", "clipped", "unreadable"].includes(reason)) return `vr_bad_${reason}`;
  const code = error && error.code;
  if (code === "too_big") return "vr_bad_too_long";
  if (code === "consent") return "vr_need_consent";
  if (code === "not_found") return "vr_bad_line";
  if (code === "slow_down") return "err_slow_down";
  if (code === "network") return "err_network";
  return "err_generic";
}

/** A take checked before upload, so an obviously short take is not sent at all. */
export function takeProblem(take) {
  if (!take || !take.blob || !take.blob.size) return "vr_bad_unreadable";
  if (Number(take.dur) > 0 && Number(take.dur) < MIN_LINE_S) return "vr_bad_too_short";
  return "";
}

/** Admin: "how often a human voice is used", shown as a whole percent, stored as 0..1. */
export function shareToPercent(share) {
  const value = Number(share);
  if (!Number.isFinite(value)) return 0;
  return Math.round(Math.max(0, Math.min(1, value)) * 100);
}

/** "" or a non-number gives null (nothing to save); otherwise 0..1 with two decimals. */
export function percentToShare(raw) {
  const text = String(raw ?? "").trim();
  if (!/^\d{1,3}$/.test(text)) return null;
  const value = Number(text);
  if (value < 0 || value > 100) return null;
  return Math.round(value) / 100;
}
