import { useState } from 'react'
import { api, ApiError, type Appointment } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n, type Key } from '../lib/i18n'
import { useLoad } from '../lib/useLoad'
import { Empty, ErrorNote, PageHeader, Pill, Skeleton } from '../components'

const TODAY = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Dhaka' }).format(new Date())

const STATUS: Record<string, { key: Key; tone: 'ok' | 'warn' | 'bad' | 'info' | 'quiet' }> = {
  booked: { key: 'statusBooked', tone: 'info' },
  completed: { key: 'statusCompleted', tone: 'ok' },
  no_show: { key: 'statusNoShow', tone: 'warn' },
  cancelled: { key: 'statusCancelled', tone: 'quiet' },
}

export function Appointments() {
  const { t, date, clock, num } = useI18n()
  const { can } = useAuth()
  const [day, setDay] = useState(TODAY)
  const [saving, setSaving] = useState<string | null>(null)
  const [saveFailed, setSaveFailed] = useState(false)
  const list = useLoad(() => api<Appointment[]>(`/api/v1/appointments?date=${day}`), [day], 15000)

  async function mark(id: string, status: string) {
    setSaving(id)
    setSaveFailed(false)
    try {
      await api(`/api/v1/appointments/${encodeURIComponent(id)}/status`, {
        method: 'POST',
        body: JSON.stringify({ status }),
      })
      list.reload()
    } catch (e) {
      if (!(e instanceof ApiError)) throw e
      setSaveFailed(true)
    } finally {
      setSaving(null)
    }
  }

  const rows = [...(list.data ?? [])].sort((a, b) => a.start_time.localeCompare(b.start_time))
  const actions: [string, Key][] = [
    ['completed', 'markDone'],
    ['no_show', 'markNoShow'],
    ['cancelled', 'markCancel'],
  ]

  return (
    <>
      <PageHeader title={t('appointmentsTitle')}>
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
      {saveFailed ? (
        <div className="note note-error" role="alert">
          {t('couldNotSave')}
        </div>
      ) : null}
      {list.loading && !list.data ? <Skeleton rows={5} /> : null}
      {list.data && rows.length === 0 ? <Empty title={t('noAppointments')} /> : null}
      {rows.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t('time')}</th>
                <th scope="col">{t('doctor')}</th>
                <th scope="col">{t('patient')}</th>
                <th scope="col">{t('status')}</th>
                <th scope="col">
                  <span className="visually-hidden">{t('open')}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => {
                const s = STATUS[a.status] ?? { key: 'statusBooked' as Key, tone: 'quiet' as const }
                return (
                  <tr key={a.appointment_id}>
                    <td className="num">{clock(a.start_time)}</td>
                    <td>{a.doctor}</td>
                    <td>
                      {a.patient_name ?? '—'}
                      <div className="muted small">
                        {a.phone} · {t('reference')} {num(Number(a.appointment_id.replace(/\D/g, '')) || 0)}
                      </div>
                    </td>
                    <td>
                      <Pill tone={s.tone}>{t(s.key)}</Pill>
                    </td>
                    <td className="actions">
                      {can('records:write')
                        ? a.status === 'booked'
                          ? actions.map(([status, label]) => (
                              <button
                                key={status}
                                type="button"
                                className="btn btn-small"
                                disabled={saving === a.appointment_id}
                                onClick={() => void mark(a.appointment_id, status)}
                              >
                                {t(label)}
                              </button>
                            ))
                          : (
                              <button
                                type="button"
                                className="btn btn-small"
                                disabled={saving === a.appointment_id}
                                onClick={() => void mark(a.appointment_id, 'booked')}
                              >
                                {t('markBooked')}
                              </button>
                            )
                        : null}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : null}
    </>
  )
}
