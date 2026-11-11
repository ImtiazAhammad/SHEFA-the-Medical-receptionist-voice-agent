import { Badge } from "@/components/portal/badge";
import { APPOINTMENT_STATUS_LABELS } from "@/constants/portal";
import { formatDhakaLongDay, formatSlot, parseTimestampRange } from "@/lib/format";
import type { AppointmentRow } from "@/types/database";

export function AppointmentLine({ appointment }: { appointment: AppointmentRow }) {
  const slot = parseTimestampRange(appointment.slot);
  const status = APPOINTMENT_STATUS_LABELS[appointment.status];
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <p className="font-semibold text-ink">{slot ? formatDhakaLongDay(slot.start) : appointment.slot}</p>
        {slot ? <p className="tabular-nums text-ink-soft">{formatSlot(slot)}</p> : null}
        <p className="mt-1 text-sm text-ink-soft">
          {appointment.services?.name_en ?? "Service"} with {appointment.doctors?.full_name_en ?? "a doctor"}
        </p>
        {appointment.doctors ? <p className="text-xs text-slate" lang="bn">{appointment.services?.name_bn} · {appointment.doctors.full_name_bn}</p> : null}
      </div>
      <Badge tone={status.tone}>{status.label}</Badge>
    </div>
  );
}
