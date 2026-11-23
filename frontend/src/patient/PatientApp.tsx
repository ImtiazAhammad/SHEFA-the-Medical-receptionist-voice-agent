import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { api, ApiError } from '../lib/api'
import { dictionaries, type PKey, type PLang } from './strings'
import '@world/fonts-lite.css'
import { ThemeSwitch } from '../lib/theme'
import './patient.css'

interface PublicDoctor {
  id: number
  name: string
  name_bn: string
  department: string
  department_bn: string
  department_id: number
  qualification: string
  visit_fee: number | null
}
interface PublicClinic {
  days_ahead: number
  callback: boolean
  departments: { id: number; name: string; name_bn: string }[]
  doctors: PublicDoctor[]
}
interface SlotDay {
  date: string
  times: string[]
}
interface Receipt {
  reference: string
  status: string
  confirmed: boolean
  doctor: string
  doctor_bn: string
  department: string
  date: string
  time: string
  end_time: string
}

type View = 'doctor' | 'time' | 'details' | 'done' | 'manage'

const TZ = 'Asia/Dhaka'

function initialLang(): PLang {
  try {
    const saved = localStorage.getItem('shefa.lang')
    if (saved === 'bn' || saved === 'en') return saved
  } catch {
    /* storage blocked: fall back to Bangla */
  }
  return 'bn'
}

function initialView(): View {
  return window.location.pathname.replace(/\/+$/, '').endsWith('/manage') ? 'manage' : 'doctor'
}

/** A server error code or a dropped connection, as a sentence the patient can act on. */
function errorKey(e: unknown): PKey {
  if (e instanceof ApiError) {
    if (e.status === 0) return 'errOffline'
    const key = `err${e.code.charAt(0).toUpperCase()}${e.code.slice(1)}` as PKey
    if (key in dictionaries.en) return key
  }
  return 'errGeneric'
}

function icsStamp(date: string, time: string): string {
  return `${date.replaceAll('-', '')}T${time.replace(':', '')}00`
}

function downloadCalendar(receipt: Receipt) {
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//SHEFA//Booking//EN',
    'BEGIN:VEVENT',
    `UID:${receipt.reference}@shefa`,
    `DTSTAMP:${new Date().toISOString().replaceAll(/[-:]/g, '').slice(0, 15)}Z`,
    `DTSTART;TZID=${TZ}:${icsStamp(receipt.date, receipt.time)}`,
    `DTEND;TZID=${TZ}:${icsStamp(receipt.date, receipt.end_time)}`,
    `SUMMARY:Visit with ${receipt.doctor}`,
    `DESCRIPTION:Booking reference ${receipt.reference}`,
    'END:VEVENT',
    'END:VCALENDAR',
  ]
  const url = URL.createObjectURL(new Blob([lines.join('\r\n')], { type: 'text/calendar' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `${receipt.reference}.ics`
  link.click()
  URL.revokeObjectURL(url)
}

/** "সকাল ১০:৪৫": a Bangladeshi reader expects the part of the day, not AM or PM. */
function banglaClock(h: number, m: number): string {
  const part = h < 5 ? 'রাত' : h < 12 ? 'সকাল' : h < 16 ? 'দুপুর' : h < 18 ? 'বিকাল' : h < 20 ? 'সন্ধ্যা' : 'রাত'
  const twelve = h % 12 === 0 ? 12 : h % 12
  const digits = new Intl.NumberFormat('bn-BD', { useGrouping: false, minimumIntegerDigits: 2 })
  return `${part} ${new Intl.NumberFormat('bn-BD').format(twelve)}:${digits.format(m)}`
}

export default function PatientApp() {
  const [lang, setLang] = useState<PLang>(initialLang)
  const [view, setView] = useState<View>(initialView)
  const [clinic, setClinic] = useState<PublicClinic | null>(null)
  const [loadError, setLoadError] = useState<PKey | null>(null)
  const [dept, setDept] = useState<number | null>(null)
  const [doctor, setDoctor] = useState<PublicDoctor | null>(null)
  const [days, setDays] = useState<SlotDay[] | null>(null)
  const [day, setDay] = useState<string>('')
  const [time, setTime] = useState<string>('')
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)

  const t = useCallback(
    (key: PKey, vars?: Record<string, string | number>) =>
      Object.entries(vars ?? {}).reduce(
        (text, [name, v]) => text.replace(`{${name}}`, String(v)),
        dictionaries[lang][key],
      ),
    [lang],
  )
  const locale = lang === 'bn' ? 'bn-BD' : 'en-GB'
  const num = (n: number | string) => new Intl.NumberFormat(locale, { useGrouping: false }).format(Number(n))
  const dayLabel = (iso: string) =>
    new Intl.DateTimeFormat(locale, { weekday: 'short', day: 'numeric', month: 'short', timeZone: TZ }).format(
      new Date(`${iso}T12:00:00+06:00`),
    )
  const longDay = (iso: string) =>
    new Intl.DateTimeFormat(locale, { dateStyle: 'full', timeZone: TZ }).format(new Date(`${iso}T12:00:00+06:00`))
  const clock = (hhmm: string) => {
    const [h, m] = hhmm.split(':').map(Number)
    if (lang === 'bn') return banglaClock(h, m)
    return new Intl.DateTimeFormat(locale, { hour: 'numeric', minute: '2-digit', timeZone: 'UTC' }).format(
      new Date(Date.UTC(2000, 0, 1, h, m)),
    )
  }
  const doctorName = (d: { name: string; name_bn: string }) => (lang === 'bn' && d.name_bn ? d.name_bn : d.name)

  useEffect(() => {
    document.documentElement.lang = lang
    document.title = `${t('title')} · SHEFA`
    try {
      localStorage.setItem('shefa.lang', lang)
    } catch {
      /* storage blocked */
    }
  }, [lang, t])

  const fetchClinic = useCallback(() => {
    api<PublicClinic>('/api/v1/public/clinic')
      .then((c) => {
        setLoadError(null)
        setClinic(c)
      })
      .catch((e) => setLoadError(errorKey(e) === 'errBooking_closed' ? 'errBooking_closed' : 'loadFailed'))
  }, [])
  useEffect(fetchClinic, [fetchClinic])

  // Move focus to the new step's heading so a screen reader announces it.
  useEffect(() => {
    window.scrollTo(0, 0)
    heading.current?.focus({ preventScroll: true })
  }, [view])

  const departments = useMemo(() => clinic?.departments ?? [], [clinic])
  const shown = useMemo(
    () => (clinic?.doctors ?? []).filter((d) => dept === null || d.department_id === dept),
    [clinic, dept],
  )

  async function chooseDoctor(d: PublicDoctor) {
    setDoctor(d)
    setDays(null)
    setDay('')
    setTime('')
    setView('time')
    try {
      const list = await api<SlotDay[]>(`/api/v1/public/slots?doctor_id=${d.id}`)
      setDays(list)
      if (list.length > 0) setDay(list[0].date)
    } catch {
      setDays([])
    }
  }

  function restart() {
    setDoctor(null)
    setDays(null)
    setDay('')
    setTime('')
    setReceipt(null)
    setView('doctor')
  }

  const steps: [View, PKey][] = [
    ['doctor', 'stepDoctor'],
    ['time', 'stepTime'],
    ['details', 'stepDetails'],
  ]
  const stepIndex = steps.findIndex(([v]) => v === view)
  // which way the booking moved, so the next step slides in from that side (transitions.dev page
  // side-by-side): forward from the right, back from the left, nothing on first load
  const [moved, setMoved] = useState<{ view: View; dir: number }>({ view, dir: 0 })
  if (moved.view !== view) {
    const from = steps.findIndex(([v]) => v === moved.view)
    setMoved({ view, dir: stepIndex < 0 || from < 0 ? 0 : stepIndex > from ? 1 : -1 })
  }

  return (
    <div className="patient" data-step-dir={moved.dir}>
      <header className="p-top">
        <span className="p-brand" aria-label="SHEFA">
          <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
            <rect width="32" height="32" rx="8" fill="var(--brand)" />
            <rect x="0.75" y="0.75" width="30.5" height="30.5" rx="7.25" fill="none" stroke="rgba(255,255,255,0.35)" strokeWidth="1.5" />
            <g transform="rotate(-38 16 16)">
              <rect x="6" y="11.5" width="20" height="9" rx="4.5" fill="#fff" />
              <path d="M16 11.5h5.5a4.5 4.5 0 0 1 0 9H16z" fill="#c9b8f4" />
            </g>
          </svg>
          SHEFA
        </span>
        <div className="p-prefs">
          <ThemeSwitch labels={lang === 'bn' ? { group: 'থিম', auto: 'ডিভাইসের মতো', light: 'আলো', dark: 'অন্ধকার' } : { group: 'Theme', auto: 'Follow this device', light: 'Light', dark: 'Dark' }} />
          <button type="button" className="p-lang" onClick={() => setLang(lang === 'bn' ? 'en' : 'bn')}>
            {t('language')}
          </button>
        </div>
      </header>

      <main className="p-main" id="main">
        <p className="p-emergency" role="note">
          {t('emergency')}
        </p>

        {view !== 'done' && view !== 'manage' ? (
          <>
            <h1 ref={heading} tabIndex={-1}>
              {t('title')}
            </h1>
            <p className="p-lead">{t('subtitle')}</p>
            <ol className="p-steps" aria-label={t('title')}>
              {steps.map(([v, key], i) => (
                <li key={v} aria-current={v === view ? 'step' : undefined} className={i <= stepIndex ? 'on' : ''}>
                  <span>{num(i + 1)}</span> {t(key)}
                </li>
              ))}
            </ol>
          </>
        ) : null}

        {loadError ? (
          <div className="p-note p-error" role="alert">
            <p>{t(loadError)}</p>
            {loadError !== 'errBooking_closed' ? (
              <button type="button" className="p-btn" onClick={fetchClinic}>
                {t('retry')}
              </button>
            ) : null}
          </div>
        ) : null}
        {!clinic && !loadError && view !== 'manage' ? (
          <p className="p-muted" role="status">
            {t('loading')}
          </p>
        ) : null}

        {clinic && view === 'doctor' ? (
          <section className="p-step" aria-labelledby="who">
            <h2 id="who">{t('chooseDoctor')}</h2>
            {departments.length > 1 ? (
              <div className="p-chips" role="group" aria-label={t('stepDoctor')}>
                <button type="button" aria-pressed={dept === null} onClick={() => setDept(null)}>
                  {t('all')}
                </button>
                {departments.map((d) => (
                  <button key={d.id} type="button" aria-pressed={dept === d.id} onClick={() => setDept(d.id)}>
                    {lang === 'bn' && d.name_bn ? d.name_bn : d.name}
                  </button>
                ))}
              </div>
            ) : null}
            <ul className="p-list">
              {shown.map((d) => (
                <li key={d.id}>
                  <button type="button" className={`p-card doc-c${Math.abs(d.id) % 6}`} onClick={() => void chooseDoctor(d)}>
                    <strong>{doctorName(d)}</strong>
                    <span>{lang === 'bn' && d.department_bn ? d.department_bn : d.department}</span>
                    {d.qualification ? <span className="p-muted">{d.qualification}</span> : null}
                    {d.visit_fee != null ? <span className="p-fee">{t('fee', { fee: num(d.visit_fee) })}</span> : null}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {view === 'time' && doctor ? (
          <section className="p-step" aria-labelledby="when">
            <p className={`p-picked doc-c${Math.abs(doctor.id) % 6}`}><span className="p-docname">{doctorName(doctor)}</span></p>
            {days === null ? (
              <p className="p-muted" role="status">
                {t('loading')}
              </p>
            ) : days.length === 0 ? (
              <div className="p-note">
                <p>{t('noSlots', { days: num(clinic?.days_ahead ?? 14) })}</p>
              </div>
            ) : (
              <>
                <h2 id="when">{t('pickDay')}</h2>
                <div className="p-chips" role="group" aria-label={t('pickDay')}>
                  {days.map((d) => (
                    <button
                      key={d.date}
                      type="button"
                      aria-pressed={day === d.date}
                      onClick={() => {
                        setDay(d.date)
                        setTime('')
                      }}
                    >
                      {dayLabel(d.date)}
                    </button>
                  ))}
                </div>
                <h2>{t('pickTime')}</h2>
                <div className="p-times" role="group" aria-label={t('pickTime')}>
                  {(days.find((d) => d.date === day)?.times ?? []).map((tm) => (
                    <button key={tm} type="button" aria-pressed={time === tm} onClick={() => setTime(tm)}>
                      {clock(tm)}
                    </button>
                  ))}
                </div>
              </>
            )}
            <div className="p-actions">
              <button type="button" className="p-btn" onClick={() => setView('doctor')}>
                {t('back')}
              </button>
              <button type="button" className="p-btn p-primary" disabled={!time} onClick={() => setView('details')}>
                {t('stepDetails')}
              </button>
            </div>
          </section>
        ) : null}

        {view === 'details' && doctor ? (
          <div className="p-step">
            <Details
              t={t}
              doctor={doctor}
              doctorName={doctorName(doctor)}
              doctorId={doctor.id}
              when={`${longDay(day)} · ${clock(time)}`}
              day={day}
              time={time}
              callbackOn={clinic?.callback ?? false}
              onBack={() => setView('time')}
              onSlotTaken={() => {
                void chooseDoctor(doctor)
              }}
              onDone={(r) => {
                setReceipt(r)
                setView('done')
              }}
            />
          </div>
        ) : null}

        {view === 'done' && receipt ? (
          <section aria-labelledby="booked">
            {/* the one moment a patient waits for: the tick draws itself in (transitions.dev
                success check); the heading beside it says it in words */}
            <span className="t-success-check p-tick" data-state="in" aria-hidden="true">
              <svg viewBox="0 0 48 48" fill="none">
                <path d="M14 25l7 7 13-15" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
            <h1 id="booked" ref={heading} tabIndex={-1}>
              {t('done')}
            </h1>
            <div className="p-receipt">
              <p className="p-muted">{t('reference')}</p>
              <p className="p-ref" aria-label={`${t('reference')} ${receipt.reference}`}>
                {receipt.reference}
              </p>
              <p>
                <strong>{lang === 'bn' && receipt.doctor_bn ? receipt.doctor_bn : receipt.doctor}</strong>
              </p>
              <p>
                {longDay(receipt.date)} · {clock(receipt.time)}
              </p>
            </div>
            <p className="p-note">{receipt.confirmed ? t('confirmed') : t('unconfirmed')}</p>
            <p className="p-muted">{t('keepRef')}</p>
            <div className="p-actions">
              <button type="button" className="p-btn" onClick={() => downloadCalendar(receipt)}>
                {t('addCalendar')}
              </button>
              <button type="button" className="p-btn" onClick={restart}>
                {t('bookAnother')}
              </button>
            </div>
          </section>
        ) : null}

        {view === 'manage' ? (
          <Manage t={t} longDay={longDay} clock={clock} lang={lang} onBook={restart} />
        ) : null}

        {view !== 'manage' && view !== 'done' ? (
          <p className="p-foot">
            <button type="button" className="p-link" onClick={() => setView('manage')}>
              {t('manage')}
            </button>
          </p>
        ) : null}
        {clinic?.callback && view !== 'details' ? <Callback t={t} /> : null}
      </main>
    </div>
  )
}

type T = (key: PKey, vars?: Record<string, string | number>) => string

function Details(props: {
  t: T
  doctor: PublicDoctor
  doctorName: string
  doctorId: number
  when: string
  day: string
  time: string
  callbackOn: boolean
  onBack: () => void
  onSlotTaken: () => void
  onDone: (r: Receipt) => void
}) {
  const { t } = props
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [reason, setReason] = useState('')
  const [call, setCall] = useState(true)
  const [trap, setTrap] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<PKey | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const receipt = await api<Receipt>('/api/v1/public/appointments', {
        method: 'POST',
        body: JSON.stringify({
          doctor_id: props.doctor.id,
          date: props.day,
          time: props.time,
          name,
          phone,
          reason,
          confirm_by_call: props.callbackOn && call,
          website: trap,
        }),
      })
      props.onDone(receipt)
    } catch (err) {
      const key = errorKey(err)
      setError(key)
      if (key === 'errSlot_taken') props.onSlotTaken()
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={(e) => void submit(e)} aria-labelledby="details">
      <h2 id="details">{t('yourDetails')}</h2>
      <div className={`p-chosen doc-c${Math.abs(props.doctorId) % 6}`}>
        <span className="p-docname">{props.doctorName}</span>
        <span className="p-when">{props.when}</span>
      </div>
      <label className="p-field">
        <span>{t('name')}</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          autoComplete="name"
          required
          maxLength={80}
          aria-invalid={error === 'errName_invalid'}
        />
      </label>
      <label className="p-field">
        <span>{t('phone')}</span>
        <input
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          required
          maxLength={20}
          aria-describedby="phone-help"
          aria-invalid={error === 'errPhone_invalid'}
        />
        <small id="phone-help">{t('phoneHelp')}</small>
      </label>
      <label className="p-field">
        <span>{t('reason')}</span>
        <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={200} aria-describedby="reason-help" />
        <small id="reason-help">{t('reasonHelp')}</small>
      </label>
      {props.callbackOn ? (
        <label className="p-check">
          <input type="checkbox" checked={call} onChange={(e) => setCall(e.target.checked)} />
          <span>{t('confirmCall')}</span>
        </label>
      ) : null}
      {/* A person never sees or fills this; a form-filling bot does. */}
      <div className="p-trap" aria-hidden="true">
        <label>
          Website
          <input value={trap} onChange={(e) => setTrap(e.target.value)} tabIndex={-1} autoComplete="off" />
        </label>
      </div>
      <p className="p-muted">{t('privacy')}</p>
      {error ? (
        <div className="p-note p-error" role="alert">
          {t(error)}
        </div>
      ) : null}
      <div className="p-actions">
        <button type="button" className="p-btn" onClick={props.onBack}>
          {t('back')}
        </button>
        <button type="submit" className="p-btn p-primary" disabled={busy}>
          {busy ? t('booking') : t('book')}
        </button>
      </div>
    </form>
  )
}

function Manage(props: {
  t: T
  longDay: (iso: string) => string
  clock: (hhmm: string) => string
  lang: PLang
  onBook: () => void
}) {
  const { t } = props
  const title = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    title.current?.focus({ preventScroll: true })
  }, [])
  const [reference, setReference] = useState('')
  const [phone, setPhone] = useState('')
  const [found, setFound] = useState<Receipt | null>(null)
  const [cancelled, setCancelled] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<PKey | null>(null)

  async function call(path: 'lookup' | 'cancel') {
    setBusy(true)
    setError(null)
    try {
      const receipt = await api<Receipt>(`/api/v1/public/appointments/${path}`, {
        method: 'POST',
        body: JSON.stringify({ reference, phone }),
      })
      setFound(receipt)
      setCancelled(receipt.status === 'cancelled')
    } catch (e) {
      setError(errorKey(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section aria-labelledby="manage-h">
      <h1 id="manage-h" ref={title} tabIndex={-1}>
        {t('manage')}
      </h1>
      <p className="p-lead">{t('manageIntro')}</p>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void call('lookup')
        }}
      >
        <label className="p-field">
          <span>{t('reference')}</span>
          <input value={reference} onChange={(e) => setReference(e.target.value)} required maxLength={20} autoCapitalize="characters" />
        </label>
        <label className="p-field">
          <span>{t('phone')}</span>
          <input value={phone} onChange={(e) => setPhone(e.target.value)} type="tel" inputMode="tel" required maxLength={20} />
        </label>
        {error ? (
          <div className="p-note p-error" role="alert">
            {t(error)}
          </div>
        ) : null}
        <div className="p-actions">
          <button type="submit" className="p-btn p-primary" disabled={busy}>
            {busy ? t('working') : t('lookup')}
          </button>
        </div>
      </form>
      {found ? (
        <div className="p-receipt" aria-live="polite">
          <p>
            <strong>{props.lang === 'bn' && found.doctor_bn ? found.doctor_bn : found.doctor}</strong>
          </p>
          <p>
            {props.longDay(found.date)} · {props.clock(found.time)}
          </p>
          {cancelled ? (
            <>
              <p className="p-note">{t('cancelled')}</p>
              <button type="button" className="p-btn" onClick={props.onBook}>
                {t('bookAnother')}
              </button>
            </>
          ) : (
            <button type="button" className="p-btn p-danger" disabled={busy} onClick={() => void call('cancel')}>
              {t('cancelBooking')}
            </button>
          )}
        </div>
      ) : null}
    </section>
  )
}

function Callback({ t }: { t: T }) {
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [trap, setTrap] = useState('')
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<PKey | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api('/api/v1/public/callback-requests', {
        method: 'POST',
        body: JSON.stringify({ name, phone, language: document.documentElement.lang, website: trap }),
      })
      setSent(true)
    } catch (err) {
      setError(errorKey(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <aside className="p-callback" aria-labelledby="cb">
      <h2 id="cb">{t('callbackTitle')}</h2>
      {sent ? (
        <p className="p-note" role="status">
          {t('callbackSent')}
        </p>
      ) : open ? (
        <form onSubmit={(e) => void submit(e)}>
          <label className="p-field">
            <span>{t('name')}</span>
            <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" required maxLength={80} />
          </label>
          <label className="p-field">
            <span>{t('phone')}</span>
            <input value={phone} onChange={(e) => setPhone(e.target.value)} type="tel" inputMode="tel" autoComplete="tel" required maxLength={20} />
          </label>
          <div className="p-trap" aria-hidden="true">
            <label>
              Website
              <input value={trap} onChange={(e) => setTrap(e.target.value)} tabIndex={-1} autoComplete="off" />
            </label>
          </div>
          {error ? (
            <div className="p-note p-error" role="alert">
              {t(error)}
            </div>
          ) : null}
          <button type="submit" className="p-btn p-primary" disabled={busy}>
            {busy ? t('working') : t('callbackBtn')}
          </button>
        </form>
      ) : (
        <button type="button" className="p-btn" onClick={() => setOpen(true)}>
          {t('callbackBtn')}
        </button>
      )}
    </aside>
  )
}
