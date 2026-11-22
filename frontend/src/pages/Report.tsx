import { useState } from 'react'
import { api } from '../lib/api'
import { useI18n, type Key } from '../lib/i18n'
import { useLoad } from '../lib/useLoad'
import { ErrorNote, PageHeader, Skeleton } from '../components'

// What SHEFA did for the clinic this week, in numbers the owner can check, plus the same as a
// short Bangla message to forward on WhatsApp. Test calls are never counted (shefa/report.py).

type Report = {
  from: string
  to: string
  desk_hours: string
  calls: { answered_by_shefa: number; after_hours: number; handed_to_a_person: number; turned_away_busy: number }
  bookings: { by_shefa_phone: number; by_web_page: number; walk_in: number; after_hours: number; total: number }
  visits: { completed: number; no_show: number; cancelled: number; no_show_rate: number | null }
  missed_calls: { total: number; booked: number }
  sms: { sent: number; failed: number; not_sent_no_gateway: number }
  estimate: { staff_minutes_saved: number; minutes_per_booking_assumed: number }
  text_bn: string
}

export function Report() {
  const { t, num, date } = useI18n()
  const [copied, setCopied] = useState(false)
  const r = useLoad(() => api<Report>('/api/v1/report?days=7'), [])
  if (r.error) return <ErrorNote error={r.error} onRetry={r.reload} />
  if (!r.data) return <Skeleton rows={6} />
  const d = r.data
  const tiles: [Key, number, string?][] = [
    ['repCalls', d.calls.answered_by_shefa, t('repAfterHours', { n: num(d.calls.after_hours) })],
    ['repBookings', d.bookings.by_shefa_phone + d.bookings.by_web_page, t('repAfterHours', { n: num(d.bookings.after_hours) })],
    ['repHanded', d.calls.handed_to_a_person],
    ['repMissed', d.missed_calls.total, t('repMissedBooked', { n: num(d.missed_calls.booked) })],
    ['repNoShow', d.visits.no_show, d.visits.no_show_rate === null ? undefined : `${num(Math.round(d.visits.no_show_rate * 100))}%`],
    ['repMinutes', d.estimate.staff_minutes_saved, t('repEstimate', { n: num(d.estimate.minutes_per_booking_assumed) })],
  ]
  async function copy() {
    try {
      await navigator.clipboard.writeText(d.text_bn)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }
  return (
    <>
      <PageHeader title={t('reportTitle')}>
        <button type="button" className="btn no-print" onClick={() => window.print()}>{t('print')}</button>
      </PageHeader>
      <p className="muted meta">
        {date(d.from, { dateStyle: 'medium' })} – {date(d.to, { dateStyle: 'medium' })} · {t('repDeskHours', { h: d.desk_hours })}
      </p>
      <div className="tiles">
        {tiles.map(([key, value, sub]) => (
          <div className="tile" key={key}>
            <div className="tile-num">{num(value)}</div>
            <div className="tile-label">{t(key)}</div>
            {sub ? <div className="muted small">{sub}</div> : null}
          </div>
        ))}
      </div>
      <section className="sources" aria-labelledby="src-h">
        <h2 id="src-h" className="section-title">{t('repBySource')}</h2>
        <ul className="ledger">
          {([
            ['srcPhone', d.bookings.by_shefa_phone, 'hatch-shefa'],
            ['srcWeb', d.bookings.by_web_page, 'hatch-shefa'],
            ['srcWalkIn', d.bookings.walk_in, 'hatch-2'],
          ] as [Key, number, string][]).map(([key, n, hatch]) => {
            const most = Math.max(1, d.bookings.by_shefa_phone, d.bookings.by_web_page, d.bookings.walk_in)
            return (
              <li key={key} className="ledger-row source-row">
                <span className="source-name">{t(key)}</span>
                <span className="source-track" aria-hidden="true">
                  <span className={`source-bar ${n ? hatch : ''}`} style={{ width: `${(n / most) * 100}%` }} />
                </span>
                <span className="source-n mono">{num(n)}</span>
              </li>
            )
          })}
        </ul>
      </section>
      {d.sms.not_sent_no_gateway ? <div className="note note-warn">{t('repSmsOff', { n: num(d.sms.not_sent_no_gateway) })}</div> : null}
      <section className="card stack no-print">
        <h2 className="section-title">{t('repShare')}</h2>
        <pre className="share-text" lang="bn">{d.text_bn}</pre>
        <div className="inline-form">
          <button type="button" className="btn" onClick={() => void copy()}>{copied ? t('copied') : t('copy')}</button>
          <a className="btn btn-primary" href={`https://wa.me/?text=${encodeURIComponent(d.text_bn)}`} target="_blank" rel="noopener noreferrer">
            {t('repWhatsapp')}
          </a>
        </div>
      </section>
    </>
  )
}
