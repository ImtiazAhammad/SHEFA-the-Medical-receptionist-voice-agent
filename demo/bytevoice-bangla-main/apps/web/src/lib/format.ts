import { DHAKA_TIME_ZONE, DHAKA_UTC_OFFSET_MINUTES } from "@/constants/app";
import type { TimeSlot } from "@/types/portal";

const BANGLA_DIGITS = ["০", "১", "২", "৩", "৪", "৫", "৬", "৭", "৮", "৯"];

const dayKeyFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: DHAKA_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const dateFormatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: DHAKA_TIME_ZONE,
  day: "numeric",
  month: "short",
  year: "numeric",
});

const shortDateFormatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: DHAKA_TIME_ZONE,
  weekday: "short",
  day: "numeric",
  month: "short",
});

const longDayFormatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: DHAKA_TIME_ZONE,
  weekday: "long",
  day: "numeric",
  month: "long",
});

const timeFormatter = new Intl.DateTimeFormat("en-GB", {
  timeZone: DHAKA_TIME_ZONE,
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});

export function toBanglaDigits(value: string | number): string {
  return String(value).replace(/[0-9]/g, (digit) => BANGLA_DIGITS[Number(digit)] ?? digit);
}

export function dhakaDayKey(date: Date): string {
  return dayKeyFormatter.format(date);
}

export function startOfDhakaDay(date: Date): Date {
  const [year, month, day] = dhakaDayKey(date).split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day) - DHAKA_UTC_OFFSET_MINUTES * 60_000);
}

export function dhakaDayKeyToUtcStart(dayKey: string): Date | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dayKey);
  if (!match) {
    return null;
  }
  const [, year, month, day] = match;
  return new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)) - DHAKA_UTC_OFFSET_MINUTES * 60_000);
}

export function formatDhakaDate(value: string | Date): string {
  return dateFormatter.format(typeof value === "string" ? new Date(value) : value);
}

export function formatDhakaShortDate(value: string | Date): string {
  return shortDateFormatter.format(typeof value === "string" ? new Date(value) : value);
}

export function formatDhakaLongDay(value: string | Date): string {
  return longDayFormatter.format(typeof value === "string" ? new Date(value) : value);
}

export function formatDhakaTime(value: string | Date): string {
  return timeFormatter.format(typeof value === "string" ? new Date(value) : value).replace(" ", " ");
}

export function formatDhakaDateTime(value: string | Date): string {
  return `${formatDhakaDate(value)}, ${formatDhakaTime(value)}`;
}

export function formatDuration(totalSeconds: number | null | undefined): string {
  if (totalSeconds === null || totalSeconds === undefined || Number.isNaN(totalSeconds)) {
    return "—";
  }
  const safeSeconds = Math.max(0, Math.round(totalSeconds));
  const minutes = Math.floor(safeSeconds / 60);
  const seconds = safeSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function formatOffset(offsetMilliseconds: number): string {
  return formatDuration(offsetMilliseconds / 1000).padStart(5, "0");
}

export function formatPhone(phone: string | null | undefined): string {
  if (!phone) {
    return "—";
  }
  const digits = phone.replace(/\D/g, "");
  const local = digits.startsWith("880") ? digits.slice(3) : digits.startsWith("0") ? digits.slice(1) : digits;
  if (/^1\d{9}$/.test(local)) {
    return `+880 ${local.slice(0, 4)}-${local.slice(4)}`;
  }
  return phone;
}

function parseRangeBound(bound: string): Date | null {
  const cleaned = bound.trim().replace(/^"|"$/g, "");
  if (!cleaned || cleaned === "infinity" || cleaned === "-infinity") {
    return null;
  }
  const isoLike = cleaned.replace(" ", "T").replace(/([+-]\d{2})$/, "$1:00");
  const parsed = new Date(isoLike);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function parseTimestampRange(range: string): TimeSlot | null {
  const match = /^[[(]\s*("?[^",]*"?)\s*,\s*("?[^",]*"?)\s*[\])]$/.exec(range.trim());
  if (!match) {
    return null;
  }
  const start = parseRangeBound(match[1]);
  const end = parseRangeBound(match[2]);
  return start && end ? { start, end } : null;
}

export function formatSlot(slot: TimeSlot): string {
  return `${formatDhakaTime(slot.start)} – ${formatDhakaTime(slot.end)}`;
}

export function percent(part: number, whole: number): number | null {
  return whole > 0 ? Math.round((part / whole) * 100) : null;
}
