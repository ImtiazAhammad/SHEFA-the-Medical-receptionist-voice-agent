import type { SupabaseClient } from "@supabase/supabase-js";
import { UPCOMING_APPOINTMENTS_LIMIT } from "@/constants/portal";
import { parseTimestampRange } from "@/lib/format";
import { parseRows, RepositoryError } from "@/lib/repositories/parse";
import { appointmentRowSchema } from "@/schemas/database";
import type { AppointmentRow } from "@/types/database";

const APPOINTMENT_SELECT =
  "id, doctor_id, call_id, slot, status, created_at, doctors(full_name_bn, full_name_en), services(code, name_bn, name_en), patients(full_name_bn, full_name_en, phone_e164)";

export async function listUpcomingAppointments(client: SupabaseClient, now: Date): Promise<AppointmentRow[]> {
  const { data, error } = await client
    .from("appointments")
    .select(APPOINTMENT_SELECT)
    .in("status", ["booked", "rescheduled"])
    .order("slot", { ascending: true })
    .limit(UPCOMING_APPOINTMENTS_LIMIT);
  if (error) {
    throw new RepositoryError("listUpcomingAppointments", error.message);
  }
  return parseRows(appointmentRowSchema, data, "listUpcomingAppointments").filter((appointment) => {
    const slot = parseTimestampRange(appointment.slot);
    return slot !== null && slot.end.getTime() >= now.getTime();
  });
}

export async function listAppointmentsForCall(client: SupabaseClient, callId: string): Promise<AppointmentRow[]> {
  const { data, error } = await client
    .from("appointments")
    .select(APPOINTMENT_SELECT)
    .eq("call_id", callId)
    .order("created_at", { ascending: true });
  if (error) {
    throw new RepositoryError("listAppointmentsForCall", error.message);
  }
  return parseRows(appointmentRowSchema, data, "listAppointmentsForCall");
}
