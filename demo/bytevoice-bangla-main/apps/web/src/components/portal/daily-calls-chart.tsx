import type { DailyCallCount } from "@/types/portal";

const CHART_HEIGHT = 140;

export function DailyCallsChart({ days }: { days: DailyCallCount[] }) {
  const maximum = Math.max(1, ...days.map((day) => day.count));
  return (
    <figure>
      <div className="flex h-[172px] items-end gap-2 border-b border-line" role="img" aria-label="Calls per day over the last 7 days">
        {days.map((day) => {
          const height = day.count === 0 ? 2 : Math.max(6, Math.round((day.count / maximum) * CHART_HEIGHT));
          return (
            <div key={day.dateKey} className="group relative flex h-full flex-1 flex-col items-center justify-end">
              <span className="mb-1 text-xs font-medium tabular-nums text-ink-soft">{day.count > 0 ? day.count : ""}</span>
              <span
                className={`w-full max-w-10 rounded-t-[4px] transition ${day.count === 0 ? "bg-line" : "bg-teal-deep group-hover:bg-teal"}`}
                style={{ height }}
              />
              <span
                role="tooltip"
                className="pointer-events-none absolute bottom-full z-10 mb-1 hidden whitespace-nowrap rounded-lg bg-ink px-2.5 py-1.5 text-xs text-white shadow-lg group-hover:block"
              >
                {day.label}: {day.count} calls, {day.booked} booked
              </span>
            </div>
          );
        })}
      </div>
      <div className="mt-2 flex gap-2">
        {days.map((day) => (
          <span key={day.dateKey} className="flex-1 text-center text-[0.7rem] text-slate">
            {day.label.split(" ")[0]?.replace(",", "")}
          </span>
        ))}
      </div>
      <figcaption className="sr-only">
        <table>
          <tbody>
            {days.map((day) => (
              <tr key={day.dateKey}>
                <th>{day.label}</th>
                <td>{day.count} calls</td>
                <td>{day.booked} booked</td>
              </tr>
            ))}
          </tbody>
        </table>
      </figcaption>
    </figure>
  );
}
