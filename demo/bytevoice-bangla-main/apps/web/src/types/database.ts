import type { z } from "zod";
import type {
  appointmentRowSchema,
  appointmentStatusSchema,
  callbackRequestRowSchema,
  callbackStatusSchema,
  callEventRowSchema,
  callExtractionRowSchema,
  callMetricRowSchema,
  callOutcomeSchema,
  callOverviewRowSchema,
  callStatusSchema,
  speakerRoleSchema,
  transcriptTurnRowSchema,
} from "@/schemas/database";

export type CallStatus = z.infer<typeof callStatusSchema>;
export type CallOutcome = z.infer<typeof callOutcomeSchema>;
export type SpeakerRole = z.infer<typeof speakerRoleSchema>;
export type AppointmentStatus = z.infer<typeof appointmentStatusSchema>;
export type CallbackStatus = z.infer<typeof callbackStatusSchema>;

export type CallOverviewRow = z.infer<typeof callOverviewRowSchema>;
export type CallMetricRow = z.infer<typeof callMetricRowSchema>;
export type TranscriptTurnRow = z.infer<typeof transcriptTurnRowSchema>;
export type CallExtractionRow = z.infer<typeof callExtractionRowSchema>;
export type CallEventRow = z.infer<typeof callEventRowSchema>;
export type AppointmentRow = z.infer<typeof appointmentRowSchema>;
export type CallbackRequestRow = z.infer<typeof callbackRequestRowSchema>;

export interface LeadInsert {
  contact_name: string;
  organisation: string | null;
  phone: string | null;
  email: string | null;
  message: string | null;
}
