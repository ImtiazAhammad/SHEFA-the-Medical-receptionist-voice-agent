import { useState } from 'react'
import { api, type Overview as OverviewData } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useLoad } from '../lib/useLoad'
import { useSegPill } from '../lib/motion'
import { Empty, ErrorNote, PageHeader, Skeleton, durationText } from '../components'

const PERIODS = [1, 7, 30]

export function Overview() {
  const { t, num } = useI18n()
  const [days, setDays] = useState(7)
  const pill = useSegPill<HTMLDivElement>(days)
  const data = useLoad(() => api<OverviewData>(`/api/v1/overview?days=${days}`), [days], 30000)
  const o = data.data
  const d = o?.calls.dispositions ?? {}
  const rows: [string, number, string?][] = o
    ? [
        [t('statCalls'), o.calls.calls],
        [t('statBooked'), o.booked_by_agent],
        [t('statHandedOver'), d.handed_over ?? 0],
        [t('statFailed'), d.failed ?? 0],
        [t('statCallbacks'), o.open_callbacks],
        [
          t('statReminders'),
          o.reminders.completed,
          o.reminders.attempted ? t('ofAttempted', { n: num(o.reminders.attempted) }) : undefined,
        ],
      ]
    : []

  return (
    <>
      <PageHeader title={t('overviewTitle')}>
        <div className="seg" role="group" aria-label={t('lastDays', { n: '' })} ref={pill}>
          <span className="seg-pill" aria-hidden="true" />
          {PERIODS.map((p) => (
            <button key={p} type="button" aria-pressed={days === p} onClick={() => setDays(p)}>
              {p === 1 ? t('today1') : t('lastDays', { n: num(p) })}
            </button>
          ))}
        </div>
      </PageHeader>
      {data.error ? <ErrorNote error={data.error} onRetry={data.reload} /> : null}
      {data.loading && !o ? <Skeleton rows={3} /> : null}
      {o && o.calls.calls === 0 && o.open_callbacks === 0 ? <Empty title={t('noCallsPeriod')} /> : null}
      {o ? (
        <dl className="stats">
          {rows.map(([label, value, extra]) => (
            <div key={label} className="stat">
              <dt>{label}</dt>
              <dd>
                {num(value)}
                {extra ? <span className="muted small"> {extra}</span> : null}
              </dd>
            </div>
          ))}
          {o.calls.average_seconds != null ? (
            <div className="stat">
              <dt>{t('avgLength')}</dt>
              <dd>{durationText(o.calls.average_seconds, t, num)}</dd>
            </div>
          ) : null}
        </dl>
      ) : null}
    </>
  )
}
