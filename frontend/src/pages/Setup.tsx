import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../lib/api'
import { useI18n, type Key } from '../lib/i18n'
import { useLoad } from '../lib/useLoad'
import { ErrorNote, PageHeader, Pill, Skeleton } from '../components'

// The clinic sets up its own doctors, chamber hours and leave here: no file to edit, no call to us.
// Every change goes to /api/v1/admin/* (owner only); a change that strands upcoming bookings
// answers with them, and they are listed so the desk can phone those patients.

type Session = { weekday: number; start_time: string; end_time: string; patients: number }
type Leave = { id: number; start_date: string; end_date: string; reason: string }
type Doctor = {
  id: number
  name_en: string
  name_bn: string
  department_id: number
  qualification: string
  visit_fee: number | null
  booking_mode: 'slot' | 'serial'
  active: boolean
  sessions: Session[]
  leaves: Leave[]
}
type Department = { id: number; name_en: string; name_bn: string }
type Directory = {
  clinic: { name_bn: string; name_en: string }
  departments: Department[]
  doctors: Doctor[]
}
type Stranded = {
  appointment_id: string
  date: string
  start_time: string
  serial_no: number | null
  phone: string
  patient_name: string
}
type Saved = Doctor & { stranded?: Stranded[] }

// Saturday first: the Bangladeshi working week
const WEEK: [number, Key][] = [
  [5, 'daySat'],
  [6, 'daySun'],
  [0, 'dayMon'],
  [1, 'dayTue'],
  [2, 'dayWed'],
  [3, 'dayThu'],
  [4, 'dayFri'],
]

function errorText(e: unknown, fallback: string) {
  return e instanceof ApiError && e.message ? e.message : fallback
}

export function Setup() {
  const { t } = useI18n()
  const dir = useLoad(() => api<Directory>('/api/v1/admin/directory'), [])
  const [open, setOpen] = useState<number | 'new' | null>(null)
  const [note, setNote] = useState<{ tone: 'ok' | 'bad'; text: string } | null>(null)
  const [stranded, setStranded] = useState<Stranded[]>([])

  function saved(text: string, result?: Saved) {
    setNote({ tone: 'ok', text })
    setStranded(result?.stranded ?? [])
    dir.reload()
  }
  function failed(e: unknown) {
    setNote({ tone: 'bad', text: errorText(e, t('couldNotSave')) })
  }

  if (dir.error) return <ErrorNote error={dir.error} onRetry={dir.reload} />
  if (!dir.data) return <Skeleton rows={6} />
  const data = dir.data

  return (
    <>
      <PageHeader title={t('setupTitle')} />
      <p className="muted meta">{t('setupIntro')}</p>
      {note ? (
        <div className={`note ${note.tone === 'bad' ? 'note-error' : ''}`} role={note.tone === 'bad' ? 'alert' : 'status'}>
          {note.text}
        </div>
      ) : null}
      {stranded.length ? <StrandedList rows={stranded} onDone={() => setStranded([])} /> : null}

      <ClinicName clinic={data.clinic} onSaved={() => saved(t('saved'))} onError={failed} />
      <Departments departments={data.departments} onSaved={() => saved(t('saved'))} onError={failed} />

      <h2 className="section-title">{t('setupDoctors')}</h2>
      <div className="stack">
        {data.doctors.map((d) => (
          <section key={d.id} className="card">
            <div className="row-between">
              <div>
                <strong>{d.name_bn || d.name_en}</strong>{' '}
                <span className="muted small">{deptName(data.departments, d.department_id)}</span>{' '}
                <Pill tone={d.booking_mode === 'serial' ? 'info' : 'quiet'}>
                  {t(d.booking_mode === 'serial' ? 'modeSerial' : 'modeSlot')}
                </Pill>{' '}
                {!d.active ? <Pill tone="warn">{t('doctorOff')}</Pill> : null}
                <div className="muted small">{sessionsLine(d.sessions, t)}</div>
              </div>
              <button type="button" className="btn btn-small" aria-expanded={open === d.id} onClick={() => setOpen(open === d.id ? null : d.id)}>
                {open === d.id ? t('close') : t('edit')}
              </button>
            </div>
            {open === d.id ? (
              <DoctorEditor
                doctor={d}
                departments={data.departments}
                onSaved={(r) => saved(t('saved'), r)}
                onError={failed}
              />
            ) : null}
          </section>
        ))}
        {open === 'new' ? (
          <section className="card">
            <DoctorEditor
              departments={data.departments}
              onSaved={(r) => {
                setOpen(r.id)
                saved(t('doctorAdded'), r)
              }}
              onError={failed}
            />
          </section>
        ) : (
          <button type="button" className="btn btn-primary" disabled={!data.departments.length} onClick={() => setOpen('new')}>
            {t('addDoctor')}
          </button>
        )}
        {!data.departments.length ? <p className="muted small">{t('needDepartmentFirst')}</p> : null}
      </div>
    </>
  )
}

function deptName(departments: Department[], id: number) {
  const d = departments.find((x) => x.id === id)
  return d ? d.name_bn || d.name_en : ''
}

function sessionsLine(sessions: Session[], t: (k: Key) => string) {
  if (!sessions.length) return t('noSessions')
  return WEEK.flatMap(([day, key]) =>
    sessions.filter((s) => s.weekday === day).map((s) => `${t(key)} ${s.start_time}–${s.end_time}`),
  ).join(' · ')
}

function ClinicName({ clinic, onSaved, onError }: { clinic: Directory['clinic']; onSaved: () => void; onError: (e: unknown) => void }) {
  const { t } = useI18n()
  const [form, setForm] = useState(clinic)
  const [busy, setBusy] = useState(false)
  async function save(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      await api('/api/v1/admin/clinic', { method: 'PUT', body: JSON.stringify(form) })
      onSaved()
    } catch (err) {
      onError(err)
    } finally {
      setBusy(false)
    }
  }
  return (
    <form className="card stack" onSubmit={(e) => void save(e)}>
      <h2 className="section-title">{t('clinicName')}</h2>
      <p className="muted small">{t('clinicNameHint')}</p>
      <label className="inline-field">
        <span>{t('nameBangla')}</span>
        <input value={form.name_bn} maxLength={80} onChange={(e) => setForm({ ...form, name_bn: e.target.value })} lang="bn" />
      </label>
      <label className="inline-field">
        <span>{t('nameEnglish')}</span>
        <input value={form.name_en} maxLength={80} onChange={(e) => setForm({ ...form, name_en: e.target.value })} lang="en" />
      </label>
      <div>
        <button type="submit" className="btn btn-primary" disabled={busy}>{t('save')}</button>
      </div>
    </form>
  )
}

function Departments({ departments, onSaved, onError }: { departments: Department[]; onSaved: () => void; onError: (e: unknown) => void }) {
  const { t } = useI18n()
  const [form, setForm] = useState({ name_en: '', name_bn: '' })
  async function add(e: FormEvent) {
    e.preventDefault()
    try {
      await api('/api/v1/admin/departments', { method: 'POST', body: JSON.stringify(form) })
      setForm({ name_en: '', name_bn: '' })
      onSaved()
    } catch (err) {
      onError(err)
    }
  }
  return (
    <section className="card stack">
      <h2 className="section-title">{t('setupDepartments')}</h2>
      {departments.length ? (
        <p>{departments.map((d) => d.name_bn || d.name_en).join(' · ')}</p>
      ) : (
        <p className="muted">{t('noDepartments')}</p>
      )}
      <form className="inline-form" onSubmit={(e) => void add(e)}>
        <label className="inline-field">
          <span>{t('nameBangla')}</span>
          <input value={form.name_bn} placeholder="নিউরোলজি" onChange={(e) => setForm({ ...form, name_bn: e.target.value })} lang="bn" />
        </label>
        <label className="inline-field">
          <span>{t('nameEnglish')}</span>
          <input value={form.name_en} placeholder="Neurology" required onChange={(e) => setForm({ ...form, name_en: e.target.value })} lang="en" />
        </label>
        <button type="submit" className="btn">{t('addDepartment')}</button>
      </form>
    </section>
  )
}

function DoctorEditor({
  doctor,
  departments,
  onSaved,
  onError,
}: {
  doctor?: Doctor
  departments: Department[]
  onSaved: (r: Saved) => void
  onError: (e: unknown) => void
}) {
  const { t } = useI18n()
  const [form, setForm] = useState({
    name_en: doctor?.name_en ?? '',
    name_bn: doctor?.name_bn ?? '',
    department_id: doctor?.department_id ?? departments[0]?.id ?? 0,
    qualification: doctor?.qualification ?? '',
    visit_fee: doctor?.visit_fee ?? null,
    booking_mode: doctor?.booking_mode ?? 'serial',
    active: doctor?.active ?? true,
  })
  const [sessions, setSessions] = useState<Session[]>(doctor?.sessions.map((s) => ({ ...s })) ?? [])
  const [leave, setLeave] = useState({ start_date: '', end_date: '', reason: '' })
  const [busy, setBusy] = useState(false)

  async function run(fn: () => Promise<Saved | void>) {
    setBusy(true)
    try {
      const r = await fn()
      if (r) onSaved(r)
    } catch (err) {
      onError(err)
    } finally {
      setBusy(false)
    }
  }

  const saveDetails = (e: FormEvent) => {
    e.preventDefault()
    void run(() =>
      doctor
        ? api<Saved>(`/api/v1/admin/doctors/${doctor.id}`, { method: 'PUT', body: JSON.stringify(form) })
        : api<Saved>('/api/v1/admin/doctors', { method: 'POST', body: JSON.stringify(form) }),
    )
  }
  const saveWeek = () =>
    void run(() =>
      api<Saved>(`/api/v1/admin/doctors/${doctor!.id}/schedule`, {
        method: 'PUT',
        body: JSON.stringify({
          sessions: sessions.map((s) => ({ weekday: s.weekday, start_time: s.start_time, end_time: s.end_time, patients: s.patients })),
        }),
      }),
    )
  const addLeave = (e: FormEvent) => {
    e.preventDefault()
    void run(async () => {
      const r = await api<Saved>(`/api/v1/admin/doctors/${doctor!.id}/leave`, {
        method: 'POST',
        body: JSON.stringify({ ...leave, end_date: leave.end_date || leave.start_date }),
      })
      setLeave({ start_date: '', end_date: '', reason: '' })
      return r
    })
  }
  const removeLeave = (id: number) =>
    void run(async () => {
      await api(`/api/v1/admin/leave/${id}`, { method: 'DELETE' })
      onSaved({ ...doctor!, stranded: [] })
    })

  function patch(i: number, change: Partial<Session>) {
    setSessions(sessions.map((s, j) => (i === j ? { ...s, ...change } : s)))
  }

  return (
    <div className="stack editor">
      <form className="stack" onSubmit={saveDetails}>
        <div className="grid-2">
          <label className="inline-field">
            <span>{t('nameBangla')}</span>
            <input value={form.name_bn} placeholder="কবির হোসেন" onChange={(e) => setForm({ ...form, name_bn: e.target.value })} lang="bn" />
          </label>
          <label className="inline-field">
            <span>{t('nameEnglish')}</span>
            <input value={form.name_en} required placeholder="Kabir Hossain" onChange={(e) => setForm({ ...form, name_en: e.target.value })} lang="en" />
          </label>
          <label className="inline-field">
            <span>{t('department')}</span>
            <select value={form.department_id} onChange={(e) => setForm({ ...form, department_id: Number(e.target.value) })}>
              {departments.map((d) => (
                <option key={d.id} value={d.id}>{d.name_bn || d.name_en}</option>
              ))}
            </select>
          </label>
          <label className="inline-field">
            <span>{t('qualification')}</span>
            <input value={form.qualification} placeholder="MBBS, FCPS" onChange={(e) => setForm({ ...form, qualification: e.target.value })} />
          </label>
          <label className="inline-field">
            <span>{t('visitFee')}</span>
            <input
              type="number"
              min={0}
              inputMode="numeric"
              value={form.visit_fee ?? ''}
              onChange={(e) => setForm({ ...form, visit_fee: e.target.value === '' ? null : Number(e.target.value) })}
            />
          </label>
        </div>
        <fieldset className="choice">
          <legend>{t('bookingMode')}</legend>
          <label>
            <input type="radio" name={`mode-${doctor?.id ?? 'new'}`} checked={form.booking_mode === 'serial'} onChange={() => setForm({ ...form, booking_mode: 'serial' })} />{' '}
            {t('modeSerial')} <span className="muted small">{t('modeSerialHint')}</span>
          </label>
          <label>
            <input type="radio" name={`mode-${doctor?.id ?? 'new'}`} checked={form.booking_mode === 'slot'} onChange={() => setForm({ ...form, booking_mode: 'slot' })} />{' '}
            {t('modeSlot')} <span className="muted small">{t('modeSlotHint')}</span>
          </label>
        </fieldset>
        {doctor ? (
          <label>
            <input type="checkbox" checked={form.active} onChange={(e) => setForm({ ...form, active: e.target.checked })} /> {t('doctorActive')}
          </label>
        ) : null}
        <div>
          <button type="submit" className="btn btn-primary" disabled={busy}>{doctor ? t('save') : t('addDoctor')}</button>
        </div>
      </form>

      {doctor ? (
        <>
          <h3 className="section-title">{t('chamberWeek')}</h3>
          <p className="muted small">{t('chamberWeekHint')}</p>
          {sessions.map((s, i) => (
            <div className="session-row" key={i}>
              <select aria-label={t('day')} value={s.weekday} onChange={(e) => patch(i, { weekday: Number(e.target.value) })}>
                {WEEK.map(([d, key]) => (
                  <option key={d} value={d}>{t(key)}</option>
                ))}
              </select>
              <input aria-label={t('from')} type="time" value={s.start_time} onChange={(e) => patch(i, { start_time: e.target.value })} />
              <input aria-label={t('to')} type="time" value={s.end_time} onChange={(e) => patch(i, { end_time: e.target.value })} />
              <label className="inline-field">
                <input
                  aria-label={t('patientsPerSession')}
                  type="number"
                  min={1}
                  max={300}
                  inputMode="numeric"
                  value={s.patients}
                  onChange={(e) => patch(i, { patients: Number(e.target.value) || 1 })}
                />
                <span className="muted small">{t('patientsWord')}</span>
              </label>
              <button type="button" className="btn btn-small" onClick={() => setSessions(sessions.filter((_, j) => j !== i))}>
                {t('remove')}
              </button>
            </div>
          ))}
          <div className="row">
            <button
              type="button"
              className="btn"
              onClick={() => {
                const last = sessions[sessions.length - 1]
                setSessions([...sessions, last ? { ...last, weekday: (last.weekday + 1) % 7 } : { weekday: 5, start_time: '17:00', end_time: '21:00', patients: 30 }])
              }}
            >
              {t('addSession')}
            </button>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={saveWeek}>
              {t('saveWeek')}
            </button>
          </div>

          <h3 className="section-title">{t('leaveTitle')}</h3>
          {doctor.leaves.length ? (
            <ul className="plain">
              {doctor.leaves.map((l) => (
                <li key={l.id}>
                  {l.start_date}
                  {l.end_date !== l.start_date ? ` – ${l.end_date}` : ''} {l.reason ? <span className="muted">({l.reason})</span> : null}{' '}
                  <button type="button" className="btn btn-small" onClick={() => removeLeave(l.id)}>
                    {t('remove')}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted small">{t('noLeave')}</p>
          )}
          <form className="inline-form" onSubmit={addLeave}>
            <label className="inline-field">
              <span>{t('from')}</span>
              <input type="date" required value={leave.start_date} onChange={(e) => setLeave({ ...leave, start_date: e.target.value })} />
            </label>
            <label className="inline-field">
              <span>{t('to')}</span>
              <input type="date" value={leave.end_date} min={leave.start_date} onChange={(e) => setLeave({ ...leave, end_date: e.target.value })} />
            </label>
            <label className="inline-field">
              <span>{t('reason')}</span>
              <input value={leave.reason} maxLength={120} onChange={(e) => setLeave({ ...leave, reason: e.target.value })} />
            </label>
            <button type="submit" className="btn" disabled={busy}>{t('addLeave')}</button>
          </form>
        </>
      ) : null}
    </div>
  )
}

function StrandedList({ rows, onDone }: { rows: Stranded[]; onDone: () => void }) {
  const { t } = useI18n()
  return (
    <div className="note note-warn stack" role="alert">
      <strong>{t('strandedTitle')}</strong>
      <ul className="plain">
        {rows.map((r) => (
          <li key={r.appointment_id}>
            {r.date} {r.serial_no ? `#${r.serial_no}` : r.start_time} · {r.patient_name || '—'} · <a href={`tel:${r.phone}`}>{r.phone}</a>
          </li>
        ))}
      </ul>
      <div>
        <button type="button" className="btn btn-small" onClick={onDone}>{t('strandedDone')}</button>
      </div>
    </div>
  )
}
