import { z } from "zod";

export const callStatusSchema = z.enum(["in_progress", "completed", "failed"]);
export const callOutcomeSchema = z.enum([
  "booked",
  "rescheduled",
  "cancelled",
  "enquiry",
  "follow_up_needed",
  "incomplete",
  "failed",
]);
export const speakerRoleSchema = z.enum(["agent", "caller"]);
export const appointmentStatusSchema = z.enum(["booked", "rescheduled", "cancelled", "completed", "no_show"]);
export const callbackStatusSchema = z.enum(["open", "in_progress", "done"]);

const jsonObjectSchema = z.record(z.string(), z.unknown());

export const callOverviewRowSchema = z.object({
  id: z.string(),
  clinic_id: z.string(),
  room_name: z.string(),
  engine: z.string(),
  started_at: z.string(),
  ended_at: z.string().nullable(),
  duration_s: z.number().nullable(),
  status: callStatusSchema,
  outcome: callOutcomeSchema.nullable(),
  after_hours: z.boolean(),
  summary_bn: z.string().nullable(),
  summary_en: z.string().nullable(),
  caller_name_bn: z.string().nullable(),
  caller_name_en: z.string().nullable(),
  caller_phone: z.string().nullable(),
  intent: z.string().nullable(),
  reason_for_visit: z.string().nullable(),
  turn_count: z.coerce.number(),
});

export const callMetricRowSchema = z.object({
  id: z.string(),
  started_at: z.string(),
  duration_s: z.number().nullable(),
  status: callStatusSchema,
  outcome: callOutcomeSchema.nullable(),
  after_hours: z.boolean(),
});

export const transcriptTurnRowSchema = z.object({
  id: z.coerce.number(),
  call_id: z.string(),
  seq: z.number(),
  speaker: speakerRoleSchema,
  text_bn: z.string(),
  text_en: z.string().nullable(),
  offset_ms: z.number(),
  interrupted: z.boolean(),
  created_at: z.string(),
});

export const callExtractionRowSchema = z.object({
  call_id: z.string(),
  intent: z.string().nullable(),
  patient_name_bn: z.string().nullable(),
  patient_name_en: z.string().nullable(),
  name_confirmed: z.boolean().nullable(),
  phone_spoken_raw: z.string().nullable(),
  phone_e164: z.string().nullable(),
  phone_valid: z.boolean().nullable(),
  reason_for_visit: z.string().nullable(),
  service_code: z.string().nullable(),
  preferred_date: z.string().nullable(),
  preferred_time_window: z.string().nullable(),
  confidence: jsonObjectSchema,
  extractor_model: z.string().nullable(),
  extracted_at: z.string(),
});

export const callEventRowSchema = z.object({
  id: z.coerce.number(),
  call_id: z.string(),
  occurred_at: z.string(),
  event_type: z.enum(["state", "tool_call", "tool_result", "latency", "error"]),
  payload: jsonObjectSchema,
});

const namedDoctorSchema = z.object({ full_name_bn: z.string(), full_name_en: z.string() });
const namedServiceSchema = z.object({ code: z.string(), name_bn: z.string(), name_en: z.string() });
const namedPatientSchema = z.object({
  full_name_bn: z.string().nullable(),
  full_name_en: z.string().nullable(),
  phone_e164: z.string().nullable(),
});

export const appointmentRowSchema = z.object({
  id: z.string(),
  doctor_id: z.string(),
  call_id: z.string().nullable(),
  slot: z.string(),
  status: appointmentStatusSchema,
  created_at: z.string(),
  doctors: namedDoctorSchema.nullable(),
  services: namedServiceSchema.nullable(),
  patients: namedPatientSchema.nullable(),
});

export const callbackRequestRowSchema = z.object({
  id: z.string(),
  call_id: z.string(),
  reason: z.string(),
  priority: z.number(),
  status: callbackStatusSchema,
  created_at: z.string(),
  resolved_at: z.string().nullable(),
  patients: namedPatientSchema.nullable(),
});
