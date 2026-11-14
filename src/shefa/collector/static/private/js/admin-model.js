// The admin page's numbers and links, with no DOM so Node can test them.

/** The go/no-go gate from the design spec (section 8). The numbers are the ML reviewer's estimate. */
export const GATE = { speakers: 100, hoursMin: 8, hoursTarget: 10 };

/** Disk: below stopMb the server refuses uploads (default setting min_free_disk_mb = 1500). */
export const DISK = { stopMb: 1500, warnMb: 5000, fullScaleMb: 20000 };

export const STATUS_ORDER = ["pending", "single", "agreed", "disputed", "adjudicated", "rejected", "withdrawn", "removed"];
export const SPLIT_ORDER = ["train", "dev", "test"];
export const CER_WARN = 0.25;

export function pct(value, total) {
  if (!total || total <= 0) return 0;
  return Math.max(0, Math.min(100, (Number(value) / Number(total)) * 100));
}

export function gate(stats) {
  const progress = (stats && stats.progress) || {};
  const speakers = Number(stats && stats.speakers_with_clips) || 0;
  const hours = (Number(progress.minutes) || 0) / 60;
  const needSpeakers = Math.max(0, GATE.speakers - speakers);
  const needHours = Math.max(0, GATE.hoursMin - hours);
  return {
    speakers, hours, needSpeakers, needHours,
    met: needSpeakers === 0 && needHours === 0,
    speakersPct: pct(speakers, GATE.speakers),
    hoursPct: pct(hours, GATE.hoursMin),
  };
}

export function diskLevel(freeMb) {
  const free = Number(freeMb);
  if (!Number.isFinite(free)) return { level: "warn", pct: 0 };
  const level = free < DISK.stopMb ? "bad" : free < DISK.warnMb ? "warn" : "ok";
  return { level, pct: pct(free, DISK.fullScaleMb) };
}

/** seed_cer is null until a reviewer meets a known-answer clip. Lower is better. */
export function cerState(cer) {
  if (cer === null || cer === undefined || Number.isNaN(Number(cer))) return "none";
  return Number(cer) > CER_WARN ? "high" : "ok";
}

/** Entries of {key: value} sorted from the biggest, dropping empty and non-numeric values. */
export function sortedEntries(object) {
  return Object.entries(object || {})
    .map(([key, value]) => [key, value === null || value === undefined ? NaN : Number(value)])
    .filter(([, value]) => Number.isFinite(value))
    .sort((a, b) => b[1] - a[1]);
}

export function inOrder(object, order) {
  const known = order.filter((key) => key in (object || {})).map((key) => [key, Number(object[key])]);
  const rest = Object.keys(object || {}).filter((key) => !order.includes(key)).map((key) => [key, Number(object[key])]);
  return [...known, ...rest];
}

/** Only an http(s) address may end up in a link. Returns "" for anything else. */
export function normalisePublicAddress(raw) {
  const text = String(raw || "").trim();
  if (!/^https?:\/\//i.test(text)) return "";
  try {
    const url = new URL(text);
    if (url.protocol !== "http:" && url.protocol !== "https:") return "";
    return `${url.origin}${url.pathname.replace(/\/+$/, "")}`;
  } catch {
    return "";
  }
}

export function campaignLink(base, code) {
  return `${base}/?c=${encodeURIComponent(code)}`;
}

export function whatsappLink(message) {
  return `https://wa.me/?text=${encodeURIComponent(message)}`;
}

/** goal_minutes must be a whole number from 1 to 100000 (server rule). Returns null if not. */
export function parseGoal(raw) {
  const text = String(raw).trim();
  if (!/^\d+$/.test(text)) return null;
  const value = Number(text);
  return value >= 1 && value <= 100000 ? value : null;
}

export const IMPACT_MAX = 300;

export const COMMANDS = [
  "shefa collect backup <folder>",
  "shefa collect export <folder>",
  "shefa collect draft",
  "shefa collect score",
];
