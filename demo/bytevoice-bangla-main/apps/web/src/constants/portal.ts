import type { AppointmentStatus, CallbackStatus, CallOutcome, CallStatus } from "@/types/database";

export const CALLS_PAGE_SIZE = 20;
export const UPCOMING_APPOINTMENTS_LIMIT = 200;
export const CALLBACKS_LIMIT = 200;
export const OVERVIEW_WINDOW_DAYS = 7;
export const REALTIME_REFRESH_DEBOUNCE_MILLISECONDS = 600;

export const CALL_STATUSES: readonly CallStatus[] = ["in_progress", "completed", "failed"];
export const CALL_OUTCOMES: readonly CallOutcome[] = [
  "booked",
  "rescheduled",
  "cancelled",
  "enquiry",
  "follow_up_needed",
  "incomplete",
  "failed",
];

export type BadgeTone = "teal" | "marigold" | "rose" | "slate" | "sky" | "violet";

export const CALL_STATUS_LABELS: Record<CallStatus, { label: string; tone: BadgeTone }> = {
  in_progress: { label: "Live", tone: "rose" },
  completed: { label: "Completed", tone: "slate" },
  failed: { label: "Failed", tone: "rose" },
};

export const CALL_OUTCOME_LABELS: Record<CallOutcome, { label: string; tone: BadgeTone }> = {
  booked: { label: "Booked", tone: "teal" },
  rescheduled: { label: "Rescheduled", tone: "sky" },
  cancelled: { label: "Cancelled", tone: "slate" },
  enquiry: { label: "Enquiry", tone: "violet" },
  follow_up_needed: { label: "Follow-up needed", tone: "marigold" },
  incomplete: { label: "Incomplete", tone: "slate" },
  failed: { label: "Failed", tone: "rose" },
};

export const APPOINTMENT_STATUS_LABELS: Record<AppointmentStatus, { label: string; tone: BadgeTone }> = {
  booked: { label: "Booked", tone: "teal" },
  rescheduled: { label: "Rescheduled", tone: "sky" },
  cancelled: { label: "Cancelled", tone: "slate" },
  completed: { label: "Completed", tone: "slate" },
  no_show: { label: "No-show", tone: "rose" },
};

export const CALLBACK_STATUS_LABELS: Record<CallbackStatus, { label: string; tone: BadgeTone }> = {
  open: { label: "Open", tone: "marigold" },
  in_progress: { label: "In progress", tone: "sky" },
  done: { label: "Done", tone: "slate" },
};

export const CALLBACK_PRIORITY_LABELS: Record<number, { label: string; tone: BadgeTone }> = {
  1: { label: "Urgent", tone: "rose" },
  2: { label: "Normal", tone: "marigold" },
  3: { label: "Low", tone: "slate" },
};

export const INTENT_LABELS: Record<string, string> = {
  book: "Book",
  reschedule: "Reschedule",
  cancel: "Cancel",
  enquiry: "Enquiry",
  other: "Other",
};

export const PORTAL_NAVIGATION = [
  { href: "/portal", label: "Overview" },
  { href: "/portal/calls", label: "Calls" },
  { href: "/portal/appointments", label: "Appointments" },
  { href: "/portal/callbacks", label: "Callbacks" },
  { href: "/portal/data-model", label: "Data model" },
] as const;

export const GUARDRAIL_LABELS: Record<string, string> = {
  private_staff_info: "Asked for a doctor's or staff member's private details",
  other_patient_info: "Asked about another patient",
  prompt_injection: "Tried to override Nila's instructions",
  medical_advice: "Asked for medical advice",
  emergency: "Described a possible emergency",
  off_topic: "Off-topic request",
  unexpected_phone_number_spoken: "Nila spoke a phone number that is not the caller's or the clinic's",
};
