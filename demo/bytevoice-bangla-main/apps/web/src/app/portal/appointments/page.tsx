import type { Metadata } from "next";
import Link from "next/link";
import { Badge } from "@/components/portal/badge";
import { PageHeader } from "@/components/portal/page-header";
import { EmptyState, ErrorState } from "@/components/portal/states";
import { SupabaseMissing } from "@/components/portal/supabase-missing";
import { APPOINTMENT_STATUS_LABELS } from "@/constants/portal";
import { dhakaDayKey, formatDhakaLongDay, formatPhone, formatSlot, parseTimestampRange } from "@/lib/format";
import { createLogger } from "@/lib/logger";
import { listUpcomingAppointments } from "@/lib/repositories/appointments-repository";
import { requirePortalContext } from "@/lib/supabase/server";
import type { AppointmentRow } from "@/types/database";
import type { TimeSlot } from "@/types/portal";

export const metadata: Metadata = { title: "Appointments" };

const logger = createLogger("portal.appointments");

interface ScheduledAppointment {
  appointment: AppointmentRow;
  slot: TimeSlot;
}

interface DoctorSchedule {
  doctorId: string;
  doctorNameEn: string;
  doctorNameBn: string;
  days: { dayKey: string; label: string; items: ScheduledAppointment[] }[];
  total: number;
}

function groupByDoctorAndDay(appointments: AppointmentRow[]): DoctorSchedule[] {
  const doctors = new Map<string, DoctorSchedule>();
  for (const appointment of appointments) {
    const slot = parseTimestampRange(appointment.slot);
    if (!slot) {
      continue;
    }
    const schedule = doctors.get(appointment.doctor_id) ?? {
      doctorId: appointment.doctor_id,
      doctorNameEn: appointment.doctors?.full_name_en ?? "Doctor",
      doctorNameBn: appointment.doctors?.full_name_bn ?? "",
      days: [],
      total: 0,
    };
    const dayKey = dhakaDayKey(slot.start);
    let day = schedule.days.find((entry) => entry.dayKey === dayKey);
    if (!day) {
      day = { dayKey, label: formatDhakaLongDay(slot.start), items: [] };
      schedule.days.push(day);
    }
    day.items.push({ appointment, slot });
    schedule.total += 1;
    doctors.set(appointment.doctor_id, schedule);
  }
  return Array.from(doctors.values())
    .map((schedule) => ({
      ...schedule,
      days: schedule.days
        .sort((first, second) => first.dayKey.localeCompare(second.dayKey))
        .map((day) => ({ ...day, items: day.items.sort((first, second) => first.slot.start.getTime() - second.slot.start.getTime()) })),
    }))
    .sort((first, second) => first.doctorNameEn.localeCompare(second.doctorNameEn));
}

export default async function AppointmentsPage() {
  const access = await requirePortalContext();
  if (access === "unconfigured") {
    return <SupabaseMissing />;
  }
  let schedules: DoctorSchedule[] | null = null;
  try {
    schedules = groupByDoctorAndDay(await listUpcomingAppointments(access.client, new Date()));
  } catch (error) {
    logger.error("Appointments failed to load", { error });
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader title="Upcoming appointments" description="Active bookings from today onwards, grouped by doctor and day." />
      {!schedules ? (
        <ErrorState title="Could not load appointments" body="Refresh the page to try again." />
      ) : schedules.length === 0 ? (
        <EmptyState title="No upcoming appointments" body="Bookings made by Nila appear here as soon as they are confirmed." />
      ) : (
        <div className="grid gap-6 xl:grid-cols-2">
          {schedules.map((schedule) => (
            <section key={schedule.doctorId} className="rounded-2xl border border-line bg-paper">
              <header className="flex items-baseline justify-between gap-3 border-b border-line px-5 py-4">
                <div>
                  <h2 className="font-semibold text-ink">{schedule.doctorNameEn}</h2>
                  <p className="text-sm text-slate" lang="bn">
                    {schedule.doctorNameBn}
                  </p>
                </div>
                <span className="text-sm tabular-nums text-ink-soft">{schedule.total} booked</span>
              </header>
              <div className="divide-y divide-line">
                {schedule.days.map((day) => (
                  <div key={day.dayKey} className="px-5 py-4">
                    <h3 className="text-sm font-semibold text-teal-deep">{day.label}</h3>
                    <ul className="mt-2 flex flex-col gap-2">
                      {day.items.map(({ appointment, slot }) => (
                        <li key={appointment.id} className="grid grid-cols-[7.5rem_1fr_auto] items-start gap-3 text-sm">
                          <span className="tabular-nums text-ink">{formatSlot(slot)}</span>
                          <span className="min-w-0">
                            <span className="block truncate font-medium text-ink" lang="bn">
                              {appointment.patients?.full_name_bn ?? appointment.patients?.full_name_en ?? "Patient"}
                            </span>
                            <span className="block text-xs text-slate">
                              {appointment.services?.name_en ?? "Service"} · {formatPhone(appointment.patients?.phone_e164)}
                            </span>
                          </span>
                          <span className="flex flex-col items-end gap-1">
                            <Badge tone={APPOINTMENT_STATUS_LABELS[appointment.status].tone}>
                              {APPOINTMENT_STATUS_LABELS[appointment.status].label}
                            </Badge>
                            {appointment.call_id ? (
                              <Link href={`/portal/calls/${appointment.call_id}`} className="text-xs text-teal-deep hover:underline">
                                View call
                              </Link>
                            ) : null}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
