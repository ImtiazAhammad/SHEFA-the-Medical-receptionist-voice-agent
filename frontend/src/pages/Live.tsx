import { Link, Outlet } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { Phone } from 'lucide-react'
import { api, type Callback, type CallRow, type SessionLoad } from '../lib/api'
import { useAuth } from '../lib/auth'
import { Legend } from '../Shell'
import { useI18n } from '../lib/i18n'
import { useLoad } from '../lib/useLoad'
import { Empty, ErrorNote, PageHeader, Pill, Skeleton, docClass, durationText } from '../components'

export function CallStatus({ call }: { call: CallRow }) {
  const { t } = useI18n()
  return call.status === 'in_progress' ? <Pill tone="live">{t('inProgress')}</Pill> : <Pill tone="quiet">{t('completed')}</Pill>
}

const minutes = (hhmm: string) => {
  const [h, m] = hhmm.split(':').map(Number)
  return h * 60 + m
}

function nowMinutes() {
  const parts = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'Asia/Dhaka' }).format(new Date())
  return minutes(parts)
}

/**
 * Today's chamber sessions on one time axis, each doctor in their own box colour. A block's
 * length is the session's real duration; it fills with the doctor's colour as places are taken,
 * and says its count in a printed stamp.
 */
function DayLoad() {
  const { t, num, clock, pick } = useI18n()
  const load = useLoad(() => api<SessionLoad[]>('/api/v1/day-load'), [], 30000)
  const [now, setNow] = useState(nowMinutes)
  useEffect(() => {
    const id = window.setInterval(() => setNow(nowMinutes()), 60000)
    return () => window.clearInterval(id)
  }, [])

  const rows = load.data ?? []
  const byDoctor = new Map<number, SessionLoad[]>()
  for (const s of rows) byDoctor.set(s.doctor_id, [...(byDoctor.get(s.doctor_id) ?? []), s])
  const start = rows.length ? Math.floor(Math.min(...rows.map((s) => minutes(s.start_time))) / 60) * 60 : 0
  const end = rows.length ? Math.ceil(Math.max(...rows.map((s) => minutes(s.end_time))) / 60) * 60 : 0
  const span = Math.max(60, end - start)
  const at = (m: number) => `${((m - start) / span) * 100}%`
  const hours = Array.from({ length: span / 60 + 1 }, (_, i) => start + i * 60)
  const step = hours.length > 10 ? 2 : 1

  return (
    <section className="dayload" aria-labelledby="load-h">
      <div className="section-head">
        <h2 id="load-h">{t('loadTitle')}</h2>

      </div>
      {load.error ? <ErrorNote error={load.error} onRetry={load.reload} /> : null}
      {load.loading && !load.data ? <Skeleton rows={2} /> : null}
      {load.data && rows.length === 0 ? <p className="muted">{t('loadNone')}</p> : null}
      {rows.length > 0 ? (
        <div className="load-grid">
          <div className="load-axis" aria-hidden="true">
            <span />
            <div className="load-track">
              {hours.map((h, i) =>
                i % step === 0 ? (
                  <span key={h} className="load-hour" style={{ left: at(h) }}>
                    {clock(`${String(h / 60).padStart(2, '0')}:00`)}
                  </span>
                ) : null,
              )}
            </div>
          </div>
          <ul className="load-rows">
            {[...byDoctor.values()].map((sessions) => {
              const d = sessions[0]
              return (
                <li key={d.doctor_id} className={`load-row ${docClass(d.doctor_id)}`}>
                  <span className="load-name">{pick(d.doctor_en, d.doctor_bn)}</span>
                  <div className="load-track">
                    {hours.map((h) => (
                      <span key={h} className="load-tick" style={{ left: at(h) }} aria-hidden="true" />
                    ))}
                    {now > start && now < end ? <span className="load-now" style={{ left: at(now) }} aria-hidden="true" /> : null}
                    {sessions.map((s) => {
                      const full = s.booked >= s.capacity && s.capacity > 0
                      const words = s.on_leave
                        ? t('loadOnLeave')
                        : `${t('sessionTime', { a: clock(s.start_time), b: clock(s.end_time) })}: ${t('loadPlaces', { b: num(s.booked), c: num(s.capacity) })}`
                      return (
                        <div
                          key={s.start_time}
                          className={`load-block${s.on_leave ? ' is-leave' : ''}${full ? ' is-full' : ''}`}
                          style={{ left: at(minutes(s.start_time)), width: `calc(${((minutes(s.end_time) - minutes(s.start_time)) / span) * 100}% - 2px)` }}
                          title={words}
                        >
                          {!s.on_leave ? (
                            <span
                              className="load-fill"
                              style={{ width: `${Math.min(100, (s.booked / Math.max(1, s.capacity)) * 100)}%` }}
                              aria-hidden="true"
                            />
                          ) : null}
                          <span className="load-count">
                            {s.on_leave ? (
                              t('loadOnLeave')
                            ) : (
                              <>
                                <span className="stamp" aria-hidden="true">
                                  {num(s.booked)}/{num(s.capacity)}
                                </span>
                                {full ? <span className="load-full"> {t('loadFull')}</span> : null}
                              </>
                            )}
                            <span className="visually-hidden">{words}</span>
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      ) : null}
    </section>
  )
}

/** Callers SHEFA handed to a person: the desk's first job, so it comes first and lifts. */
function Callbacks() {
  const { t, date } = useI18n()
  const { can } = useAuth()
  const list = useLoad(() => api<Callback[]>('/api/v1/callbacks'), [], 5000)
  const [busy, setBusy] = useState<number | null>(null)

  async function resolve(id: number) {
    setBusy(id)
    try {
      await api(`/api/v1/callbacks/${id}/resolve`, { method: 'POST', body: JSON.stringify({}) })
      list.reload()
    } finally {
      setBusy(null)
    }
  }

  const items = list.data ?? []
  return (
    <section className={`callbacks${items.length ? ' has-items' : ''}`} aria-labelledby="cb-h" aria-live="polite">
      <div className="section-head">
        <h2 id="cb-h">{t('callbacksTitle')}</h2>
        {items.length ? <span className="count-big">{items.length}</span> : null}
      </div>
      {list.error ? <ErrorNote error={list.error} onRetry={list.reload} /> : null}
      {list.data && items.length === 0 ? <p className="muted callbacks-none">{t('noCallbacks')}</p> : null}
      {items.length ? (
        <ul className="ledger">
          {items.map((c) => (
            <li key={c.id} className="ledger-row is-urgent">
              <Pill tone="bad">{t('needsPersonShort')}</Pill>
              <Phone size={16} strokeWidth={1.75} aria-hidden="true" />
              {c.phone ? (
                <a href={`tel:${c.phone}`} className="phone">
                  {c.phone}
                </a>
              ) : (
                <span className="muted">-</span>
              )}
              <span className="muted">
                {t('waiting', { when: date(c.created_at, { timeStyle: 'short', dateStyle: 'medium', timeZone: 'Asia/Dhaka' }) })}
              </span>
              {can('records:write') ? (
                <button type="button" className="btn btn-small ledger-end" disabled={busy === c.id} onClick={() => void resolve(c.id)}>
                  {busy === c.id ? t('resolving') : t('resolve')}
                </button>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  )
}

function CallRows({ calls, full }: { calls: CallRow[]; full?: boolean }) {
  const { t, num, date } = useI18n()
  return (
    <ul className="ledger">
      {calls.map((c) => (
        <li key={c.call_sid}>
          <Link className="ledger-row" to={`call/${encodeURIComponent(c.call_sid)}`}>
            <CallStatus call={c} />
            <span>{c.direction === 'outbound' ? t('outbound') : t('inbound')}</span>
            <span className="muted num">
              {c.started_at ? date(c.started_at, full ? { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Dhaka' } : { timeStyle: 'short', timeZone: 'Asia/Dhaka' }) : ''}
            </span>
            <span className="ledger-end num">{full ? durationText(c.duration_seconds, t, num) : t('open')}</span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

export function Live() {
  const { t, date } = useI18n()
  const calls = useLoad(() => api<CallRow[]>('/api/v1/calls?limit=30'), [], 3000)
  const active = (calls.data ?? []).filter((c) => c.status === 'in_progress')
  const recent = (calls.data ?? []).filter((c) => c.status !== 'in_progress').slice(0, 8)
  const last = recent[0]?.started_at

  return (
    <>
      <PageHeader title={t('liveTitle')} />
      <Callbacks />
      <DayLoad />
      <Legend className="page-legend" />
      <div className="live-cols">
        <section aria-labelledby="active-h" aria-live="polite">
          <div className="section-head">
            <h2 id="active-h">{t('inProgress')}</h2>
            {active.length ? <span className="count-big count-shefa">{active.length}</span> : null}
          </div>
          {calls.error ? <ErrorNote error={calls.error} onRetry={calls.reload} /> : null}
          {calls.loading && !calls.data ? <Skeleton rows={2} /> : null}
          {calls.data && active.length === 0 ? (
            <Empty
              title={t('noCallsNow')}
              hint={last ? t('lastCall', { when: date(last, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Dhaka' }) }) : t('noCallsYet')}
            />
          ) : null}
          {active.length ? <CallRows calls={active} /> : null}
        </section>
      </div>
      {recent.length > 0 ? (
        <section aria-labelledby="recent-h">
          <div className="section-head">
            <h2 id="recent-h">{t('recentTitle')}</h2>
            <Link to="/calls" className="legend-link">
              {t('callsTitle')}
            </Link>
          </div>
          <CallRows calls={recent} full />
        </section>
      ) : null}
      <Outlet />
    </>
  )
}
