import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Mic, PhoneOff, Send } from 'lucide-react'
import { dictionaries, type DKey, type DLang } from './strings'
import { VoiceCall, type VoiceEnd, type VoiceState } from './voice'
import '@world/fonts-lite.css'
import '../patient/patient.css'
import './demo.css'

interface Line {
  id: number
  role: 'user' | 'assistant'
  text: string
}
interface DemoInfo {
  enabled: boolean
  max_call_seconds: number
  busy: boolean
}

function initialLang(): DLang {
  try {
    const saved = localStorage.getItem('shefa.lang')
    if (saved === 'bn' || saved === 'en') return saved
  } catch {
    /* storage blocked: Bangla */
  }
  return 'bn'
}

const END_MESSAGE: Record<VoiceEnd, DKey> = {
  ended: 'ended',
  tooLong: 'endedLong',
  busy: 'busy',
  forbidden: 'forbidden',
  micBlocked: 'micBlocked',
  micMissing: 'micMissing',
  failed: 'failed',
}

export default function DemoApp() {
  const [lang, setLang] = useState<DLang>(initialLang)
  const [info, setInfo] = useState<DemoInfo | null>(null)
  const [state, setState] = useState<VoiceState>('idle')
  const [notice, setNotice] = useState<DKey | null>(null)
  const [lines, setLines] = useState<Line[]>([])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [secondsLeft, setSecondsLeft] = useState(0)
  const nextId = useRef(1)
  const call = useRef<VoiceCall | null>(null)
  const log = useRef<HTMLOListElement>(null)
  const session = useMemo(() => crypto.randomUUID().slice(0, 18), [])
  const t = dictionaries[lang]
  const digits = useMemo(() => new Intl.NumberFormat(lang === 'bn' ? 'bn-BD' : 'en'), [lang])

  useEffect(() => {
    document.documentElement.lang = lang
    document.title = `${t.brand} · ${lang === 'bn' ? 'ডেমো' : 'Demo'}`
    try {
      localStorage.setItem('shefa.lang', lang)
    } catch {
      /* ignore */
    }
  }, [lang, t.brand])

  useEffect(() => {
    fetch('/api/v1/public/demo')
      .then((r) => (r.ok ? (r.json() as Promise<DemoInfo>) : null))
      .then(setInfo)
      .catch(() => setInfo(null))
  }, [])

  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight, behavior: 'smooth' })
  }, [lines])

  const add = useCallback((role: Line['role'], text: string) => {
    setLines((current) => [...current, { id: nextId.current++, role, text }])
  }, [])

  // The countdown only tells the visitor how long the demo call lasts; the server enforces it.
  useEffect(() => {
    if (state !== 'live' || !info) return
    setSecondsLeft(info.max_call_seconds)
    const timer = window.setInterval(() => setSecondsLeft((s) => Math.max(0, s - 1)), 1000)
    return () => window.clearInterval(timer)
  }, [state, info])

  useEffect(() => () => call.current?.stop(), [])

  async function toggleCall() {
    if (state !== 'idle') {
      call.current?.stop()
      return
    }
    setNotice(null)
    call.current = new VoiceCall({
      onState: setState,
      onTurn: add,
      onEnd: (why) => setNotice(why === 'ended' ? null : END_MESSAGE[why]),
    })
    await call.current.start()
  }

  async function send(text: string) {
    const message = text.trim()
    if (!message || sending || state !== 'idle') return
    setSending(true)
    setNotice(null)
    add('user', message)
    setDraft('')
    try {
      const response = await fetch('/api/v1/public/demo/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, session }),
      })
      const body = (await response.json()) as { reply?: string; error?: { code: string } }
      if (response.ok && body.reply) add('assistant', body.reply)
      else setNotice(body.error?.code === 'chat_limit' ? 'chatLimit' : 'chatError')
    } catch {
      setNotice('chatError')
    } finally {
      setSending(false)
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    void send(draft)
  }

  const live = state === 'live'
  const time = `${digits.format(Math.floor(secondsLeft / 60))}:${secondsLeft % 60 < 10 ? digits.format(0) : ''}${digits.format(secondsLeft % 60)}`

  if (info && !info.enabled) return null

  return (
    <div className="patient demo">
      <header className="p-top">
        <span className="p-brand">
          <svg width="26" height="26" viewBox="0 0 28 28" aria-hidden="true">
              <rect x="0.5" y="0.5" width="27" height="27" fill="none" stroke="currentColor" />
              <rect x="4" y="4" width="5" height="20" fill="currentColor" />
              <rect x="11.5" y="4" width="5" height="20" fill="currentColor" opacity="0.55" />
              <rect x="19" y="4" width="5" height="20" fill="var(--dichroic)" />
          </svg>
          {t.brand}
        </span>
        <button type="button" className="p-lang" onClick={() => setLang(lang === 'bn' ? 'en' : 'bn')}>
          {t.language}
        </button>
      </header>
      <main className="p-main">
        <h1>{t.title}</h1>
        <p className="p-lead">{t.lead}</p>
        <p className="demo-sample">{t.sample}</p>

        <section className="demo-call" aria-label={t.start}>
          <button
            type="button"
            className={`demo-orb${live ? ' live' : ''}`}
            onClick={() => void toggleCall()}
            disabled={state === 'connecting'}
            aria-pressed={live}
          >
            {live ? <PhoneOff size={34} aria-hidden="true" /> : <Mic size={34} aria-hidden="true" />}
            <span>{state === 'connecting' ? t.connecting : live ? t.hangUp : t.start}</span>
          </button>
          <p className="demo-state" role="status">
            {live ? `${t.live} · ${t.timeLeft.replace('{time}', time)}` : notice ? t[notice] : ''}
          </p>
        </section>

        <section aria-label={t.tryTitle}>
          <h2>{t.tryTitle}</h2>
          <ul className="demo-chips">
            {t.chips.map((chip) => (
              <li key={chip}>
                <button type="button" onClick={() => void send(chip)} disabled={live || sending}>
                  {chip}
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="demo-chat">
          {lines.length === 0 ? (
            <p className="p-lead">{t.empty}</p>
          ) : (
            <ol className="demo-log" ref={log} aria-live="polite">
              {lines.map((line) => (
                <li key={line.id} className={`demo-line demo-${line.role}`}>
                  <small>{line.role === 'user' ? t.you : t.agent}</small>
                  <p>{line.text}</p>
                </li>
              ))}
            </ol>
          )}
          <form className="demo-form" onSubmit={onSubmit}>
            <label htmlFor="demo-text">{t.typeLabel}</label>
            <div className="demo-row">
              <input
                id="demo-text"
                value={draft}
                maxLength={400}
                onChange={(e) => setDraft(e.target.value)}
                placeholder={t.typePlaceholder}
                disabled={live}
                autoComplete="off"
              />
              <button type="submit" disabled={live || sending || !draft.trim()} aria-label={t.send}>
                <Send size={18} aria-hidden="true" />
              </button>
            </div>
          </form>
        </section>

        <section>
          <h2>{t.howTitle}</h2>
          <ol className="demo-steps">
            {t.steps.map(([head, body]) => (
              <li key={head}>
                <strong>{head}</strong>
                <span>{body}</span>
              </li>
            ))}
          </ol>
        </section>

        <section>
          <h2>{t.safeTitle}</h2>
          <ul className="demo-safe">
            {t.safe.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>

        <p className="demo-foot">
          <a href="/book">{t.bookLink}</a> · {t.emergency}
        </p>
      </main>
    </div>
  )
}
