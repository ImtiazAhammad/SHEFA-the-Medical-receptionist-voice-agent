import { useState, type FormEvent } from 'react'
import { api, ApiError, type Appointment, type Department } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n, type Key } from '../lib/i18n'
import { useLoad } from '../lib/useLoad'
import { Empty, ErrorNote, PageHeader, Pill, Skeleton, docClass, type Tone } from '../components'

const TODAY = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Dhaka' }).format(new Date())

// booked: an outlined pill (nothing to do yet); seen: green; no-show: amber; cancelled: struck grey.
const STATUS: Record<string, { key: Key; tone: Tone }> = {
  booked: { key: 'statusBooked', tone: 'quiet' },
  completed: { key: 'statusCompleted', tone: 'ok' },
  no_show: { key: 'statusNoShow', tone: 'warn' },
  cancelled: { key: 'statusCancelled', tone: 'gone' },
}

export function Appointments() {
  const { t, date, clock, num } = useI18n()
  const { can } = useAuth()
  const [day, setDay] = useState(TODAY)
  const [saving, setSaving] = useState<string | null>(null)
  const [saveFailed, setSaveFailed] = useState(false)
  // What happened to the confirmation SMS of the booking just confirmed: shown, never assumed.
  const [smsNote, setSmsNote] = useState<{ sent: boolean; reason: string } | null>(null)
  const [walkIn, setWalkIn] = useState<{ doctor_id: string; name: string; phone: string } | null>(null)
  const [walkInNote, setWalkInNote] = useState<{ tone: 'ok' | 'bad'; text: string } | null>(null)
  const dir = useLoad(() => api<Department[]>('/api/v1/directory'), [])
  const doctors = (dir.data ?? []).flatMap((d) => d.doctors).filter((d) => d.id !== undefined)
  const list = useLoad(() => api<Appointment[]>(`/api/v1/appointments?date=${day}&status=all`), [day], 15000)

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

  async function confirm(id: string) {
    setSaving(id)
    setSaveFailed(false)
    try {
      const done = await api<{ sms: { sent: boolean; reason: string } | null }>(
        `/api/v1/appointments/${encodeURIComponent(id)}/confirm`,
        { method: 'POST' },
      )
      setSmsNote(done.sms)
      list.reload()
    } catch (e) {
      if (!(e instanceof ApiError)) throw e
      setSaveFailed(true)
    } finally {
      setSaving(null)
    }
  }

  async function addWalkIn(e: FormEvent) {
    e.preventDefault()
    if (!walkIn) return
    setWalkInNote(null)
    try {
      const r = await api<{ serial_no: number | null; start_time: string }>('/api/v1/appointments/walk-in', {
        method: 'POST',
        body: JSON.stringify({ doctor_id: Number(walkIn.doctor_id), name: walkIn.name, phone: walkIn.phone }),
      })
      setWalkInNote({
        tone: 'ok',
        text: r.serial_no
          ? t('walkInSerial', { serial: num(r.serial_no), time: clock(r.start_time) })
          : t('walkInTime', { time: clock(r.start_time) }),
      })
      setWalkIn(null)
      if (day !== TODAY()) setDay(TODAY())
      list.reload()
    } catch (err) {
      setWalkInNote({ tone: 'bad', text: err instanceof ApiError && err.message ? err.message : t('couldNotSave') })
    }
  }

  const rows = [...(list.data ?? [])].sort((a, b) => a.start_time.localeCompare(b.start_time))
  const byDoctor = new Map<string, Appointment[]>()
  for (const a of rows.filter((r) => r.status === 'booked')) {
    const key = a.doctor_bn || a.doctor
    byDoctor.set(key, [...(byDoctor.get(key) ?? []), a])
  }
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
        {can('records:write') ? (
          <button
            type="button"
            className="btn btn-primary no-print"
            onClick={() => setWalkIn(walkIn ? null : { doctor_id: String(doctors[0]?.id ?? ''), name: '', phone: '' })}
          >
            {t('addWalkIn')}
          </button>
        ) : null}
        <button type="button" className="btn no-print" disabled={!rows.length} onClick={() => window.print()}>
          {t('printList')}
        </button>
      </PageHeader>
      {walkIn ? (
        <form className="card inline-form no-print" onSubmit={(e) => void addWalkIn(e)}>
          <label className="inline-field">
            <span>{t('doctor')}</span>
            <select value={walkIn.doctor_id} onChange={(e) => setWalkIn({ ...walkIn, doctor_id: e.target.value })} required>
              {doctors.map((d) => (
                <option key={d.id} value={d.id}>{d.name_bn || d.name}</option>
              ))}
            </select>
          </label>
          <label className="inline-field">
            <span>{t('patientName')}</span>
            <input value={walkIn.name} required maxLength={80} onChange={(e) => setWalkIn({ ...walkIn, name: e.target.value })} autoFocus />
          </label>
          <label className="inline-field">
            <span>{t('phoneOptional')}</span>
            <input value={walkIn.phone} inputMode="tel" maxLength={20} onChange={(e) => setWalkIn({ ...walkIn, phone: e.target.value })} />
          </label>
          <button type="submit" className="btn btn-primary">{t('giveSerial')}</button>
        </form>
      ) : null}
      {walkInNote ? (
        <div className={`note no-print ${walkInNote.tone === 'bad' ? 'note-error' : ''}`} role={walkInNote.tone === 'bad' ? 'alert' : 'status'}>
          {walkInNote.text}
        </div>
      ) : null}
      <p className="muted meta">{date(day, { dateStyle: 'full', timeZone: 'Asia/Dhaka' })}</p>
      {list.error ? <ErrorNote error={list.error} onRetry={list.reload} /> : null}
      {smsNote ? (
        <div className={smsNote.sent ? 'note' : 'note note-warn'} role="status">
          {smsNote.sent ? t('smsSent') : `${t('smsNotSent')} ${smsNote.reason}`}
        </div>
      ) : null}
      {saveFailed ? (
        <div className="note note-error" role="alert">
          {t('couldNotSave')}
        </div>
      ) : null}
      {list.loading && !list.data ? <Skeleton rows={5} /> : null}
      {list.data && rows.length === 0 ? <Empty title={t('noAppointments')} /> : null}
      {rows.length > 0 ? (
        <div className="table-wrap no-print">
          <table className="stack-table">
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
                    <td className="num" data-label={t('time')}>
                      {a.serial_no ? <span className="stamp serial"><small>{t('serialCol')}</small>{num(a.serial_no)}</span> : null}
                      <div className={a.serial_no ? 'muted small' : ''}>{clock(a.start_time)}</div>
                    </td>
                    <td data-label={t('doctor')}>
                      <span className={`doc-name ${docClass(a.doctor_id)}`}>{a.doctor_bn || a.doctor}</span>
                      {a.source === 'walkin' ? <div className="small"><Pill tone="quiet">{t('walkIn')}</Pill></div> : null}
                      {a.source === 'phone' || a.source === 'web' ? <div className="small"><Pill tone="shefa">{t('byShefa')}</Pill></div> : null}
                    </td>
                    <td data-label={t('patient')}>
                      {a.patient_name ?? '—'}
                      <div className="muted small">
                        {a.phone} · {t('reference')} {num(Number(a.appointment_id.replace(/\D/g, '')) || 0)}
                      </div>
                    </td>
                    <td data-label={t('status')}>
                      <Pill tone={s.tone}>{t(s.key)}</Pill>
                      {a.status === 'booked' && a.confirmed === false ? (
                        <div className="small">
                          <Pill tone="warn">{t('unconfirmed')}</Pill>
                        </div>
                      ) : null}
                    </td>
                    <td className="actions">
                      {can('records:write') && a.status === 'booked' && a.confirmed === false ? (
                        <button
                          type="button"
                          className="btn btn-small btn-primary"
                          disabled={saving === a.appointment_id}
                          onClick={() => void confirm(a.appointment_id)}
                        >
                          {t('confirmBooking')}
                        </button>
                      ) : null}
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
      <section className="print-only" aria-hidden="true">
        {[...byDoctor.entries()].map(([doctor, list]) => (
          <div className="print-doctor" key={doctor}>
            <h2>
              {doctor} · {date(day, { dateStyle: 'full', timeZone: 'Asia/Dhaka' })}
            </h2>
            <table>
              <thead>
                <tr>
                  <th>{t('serialCol')}</th>
                  <th>{t('time')}</th>
                  <th>{t('patient')}</th>
                  <th>{t('phone')}</th>
                  <th>{t('arrived')}</th>
                </tr>
              </thead>
              <tbody>
                {[...list]
                  .sort((x, y) => (x.serial_no ?? 0) - (y.serial_no ?? 0) || x.start_time.localeCompare(y.start_time))
                  .map((a) => (
                    <tr key={a.appointment_id}>
                      <td>{a.serial_no ? num(a.serial_no) : ''}</td>
                      <td>{clock(a.start_time)}</td>
                      <td>{a.patient_name ?? ''}</td>
                      <td>{a.phone}</td>
                      <td className="tick-box" />
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        ))}
      </section>
    </>
  )
}
