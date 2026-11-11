import type { CallOutcome, CallStatus } from "@/types/database";

export interface CallListFilters {
  search: string;
  status: CallStatus | null;
  outcome: CallOutcome | null;
  dateFrom: string | null;
  dateTo: string | null;
  page: number;
}

export interface PagedResult<Row> {
  rows: Row[];
  total: number;
  page: number;
  pageSize: number;
}

export interface DailyCallCount {
  dateKey: string;
  label: string;
  count: number;
  booked: number;
}

export interface OverviewMetrics {
  callsToday: number;
  callsInWindow: number;
  bookedPercent: number | null;
  afterHoursPercent: number | null;
  averageDurationSeconds: number | null;
  openCallbacks: number;
  liveCalls: number;
  daily: DailyCallCount[];
}

export interface TimeSlot {
  start: Date;
  end: Date;
}

export interface LatencySummary {
  metric: string;
  count: number;
  averageMilliseconds: number;
  p50Milliseconds: number;
  maxMilliseconds: number;
}

export type RepositoryResult<Value> =
  | { ok: true; value: Value }
  | { ok: false; message: string };

export interface ActionState {
  status: "idle" | "error" | "success";
  message: string;
}
