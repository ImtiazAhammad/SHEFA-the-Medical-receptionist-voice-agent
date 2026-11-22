import { useState } from 'react'
import { api, type MyAppointment } from '../lib/api'
import { useI18n, type Key } from '../lib/i18n'
import { useLoad } from '../lib/useLoad'
import { Empty, ErrorNote, PageHeader, Pill, Skeleton, type Tone } from '../components'

const TODAY = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Dhaka' }).format(new Date())

const STATUS: Record<string, { key: Key; tone: Tone }> = {
  booked: { key: 'statusBooked', tone: 'quiet' },
  completed: { key: 'statusCompleted', tone: 'ok' },
  no_show: { key: 'statusNoShow', tone: 'warn' },
  cancelled: { key: 'statusCancelled', tone: 'gone' },
}

/** A doctor's own day: their patients and nobody else's. */
export function MyDay() {
  const { t, clock, date } = useI18n()
  const [day, setDay] = useState(TODAY)
  const [saving, setSaving] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)
  const list = useLoad(() => api<MyAppointment[]>(`/api/v1/me/day?date=${day}`), [day], 15000)

  async function mark(id: string, status: string) {
    setSaving(id)
    setFailed(false)
    try {
      await api(`/api/v1/me/appointments/${encodeURIComponent(id)}/status`, {
        method: 'POST',
        body: JSON.stringify({ status }),
      })
      list.reload()
    } catch {
      setFailed(true)
    } finally {
      setSaving(null)
    }
  }

  const rows = [...(list.data ?? [])].sort((a, b) => a.start_time.localeCompare(b.start_time))
  return (
    <>
      <PageHeader title={t('myDayTitle')}>
        <label className="inline-field">
          <span>{t('day')}</span>
          <input type="date" value={day} onChange={(e) => e.target.value && setDay(e.target.value)} />
        </label>
        {day !== TODAY() ? (
          <button type="button" className="btn" onClick={() => setDay(TODAY())}>
            {t('today')}
          </button>
        ) : null}
      </PageHeader>
      <p className="muted meta">{date(day, { dateStyle: 'full', timeZone: 'Asia/Dhaka' })}</p>
      {list.error ? <ErrorNote error={list.error} onRetry={list.reload} /> : null}
      {failed ? (
        <div className="note note-error" role="alert">
          {t('couldNotSave')}
        </div>
      ) : null}
      {list.loading && !list.data ? <Skeleton rows={4} /> : null}
      {list.data && rows.length === 0 ? <Empty title={t('noPatients')} /> : null}
      <ul className="rows myday-feed">
        {rows.map((a) => {
          const s = STATUS[a.status] ?? STATUS.booked
          return (
            <li key={a.appointment_id} className="row">
              <strong className="stamp serial">{clock(a.start_time)}</strong>
              <span>{a.patient_name ?? '-'}</span>
              <Pill tone={s.tone}>{t(s.key)}</Pill>
              {a.reason ? (
                <span className="muted">
                  {t('reasonLabel')}: {a.reason}
                </span>
              ) : null}
              <span className="row-end actions">
                {a.status === 'booked' ? (
                  <>
                    <button type="button" className="btn btn-small" disabled={saving === a.appointment_id} onClick={() => void mark(a.appointment_id, 'completed')}>
                      {t('markDone')}
                    </button>
                    <button type="button" className="btn btn-small" disabled={saving === a.appointment_id} onClick={() => void mark(a.appointment_id, 'no_show')}>
                      {t('markNoShow')}
                    </button>
                  </>
                ) : (
                  <button type="button" className="btn btn-small" disabled={saving === a.appointment_id} onClick={() => void mark(a.appointment_id, 'booked')}>
                    {t('markBooked')}
                  </button>
                )}
              </span>
            </li>
          )
        })}
      </ul>
    </>
  )
}
