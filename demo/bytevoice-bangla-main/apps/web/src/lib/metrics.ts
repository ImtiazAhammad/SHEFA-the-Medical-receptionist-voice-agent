import { dhakaDayKey, formatDhakaShortDate, percent, startOfDhakaDay } from "@/lib/format";
import { latencyPayloadSchema } from "@/schemas/requests";
import type { CallEventRow, CallMetricRow } from "@/types/database";
import type { DailyCallCount, LatencySummary, OverviewMetrics } from "@/types/portal";

const DAY_MILLISECONDS = 86_400_000;

export function computeOverviewMetrics(
  calls: CallMetricRow[],
  openCallbacks: number,
  now: Date,
  windowDays: number,
): OverviewMetrics {
  const todayStart = startOfDhakaDay(now).getTime();
  const windowStart = todayStart - (windowDays - 1) * DAY_MILLISECONDS;
  const inWindow = calls.filter((call) => new Date(call.started_at).getTime() >= windowStart);
  const finished = inWindow.filter((call) => call.status !== "in_progress");
  const booked = finished.filter((call) => call.outcome === "booked" || call.outcome === "rescheduled");
  const durations = finished.map((call) => call.duration_s).filter((value): value is number => value !== null);

  const daily: DailyCallCount[] = [];
  for (let offset = windowDays - 1; offset >= 0; offset -= 1) {
    const dayStart = new Date(todayStart - offset * DAY_MILLISECONDS);
    const dateKey = dhakaDayKey(dayStart);
    const dayCalls = inWindow.filter((call) => dhakaDayKey(new Date(call.started_at)) === dateKey);
    daily.push({
      dateKey,
      label: formatDhakaShortDate(dayStart),
      count: dayCalls.length,
      booked: dayCalls.filter((call) => call.outcome === "booked" || call.outcome === "rescheduled").length,
    });
  }

  return {
    callsToday: inWindow.filter((call) => new Date(call.started_at).getTime() >= todayStart).length,
    callsInWindow: inWindow.length,
    bookedPercent: percent(booked.length, finished.length),
    afterHoursPercent: percent(inWindow.filter((call) => call.after_hours).length, inWindow.length),
    averageDurationSeconds: durations.length
      ? durations.reduce((total, value) => total + value, 0) / durations.length
      : null,
    openCallbacks,
    liveCalls: calls.filter((call) => call.status === "in_progress").length,
    daily,
  };
}

export function summarizeLatency(events: CallEventRow[]): LatencySummary[] {
  const byMetric = new Map<string, number[]>();
  for (const event of events) {
    if (event.event_type !== "latency") {
      continue;
    }
    const parsed = latencyPayloadSchema.safeParse(event.payload);
    if (!parsed.success) {
      continue;
    }
    const values = byMetric.get(parsed.data.metric) ?? [];
    values.push(parsed.data.value_ms);
    byMetric.set(parsed.data.metric, values);
  }
  return Array.from(byMetric.entries()).map(([metric, values]) => {
    const sorted = [...values].sort((first, second) => first - second);
    const middle = Math.floor(sorted.length / 2);
    const median = sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
    return {
      metric,
      count: sorted.length,
      averageMilliseconds: Math.round(sorted.reduce((total, value) => total + value, 0) / sorted.length),
      p50Milliseconds: Math.round(median),
      maxMilliseconds: Math.round(sorted[sorted.length - 1]),
    };
  });
}
