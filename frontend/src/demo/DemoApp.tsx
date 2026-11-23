import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { Mic, PhoneOff, Send } from 'lucide-react'
import { dictionaries, type DKey, type DLang } from './strings'
import { VoiceCall, type VoiceEnd, type VoiceState } from './voice'
import '@world/fonts-lite.css'
import { VoiceRing } from 'voice-ring'
import { ThinkingOrb } from 'thinking-orbs'
import { ThemeSwitch, useReducedMotion, useShownTheme } from '../lib/theme'
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
  // a reply usually lands in about a second; only a slow one earns the composing orb, so a quick
  // answer never flashes a loader (the orb's own rule: nothing under the wait it takes to notice)
  const [slowReply, setSlowReply] = useState(false)
  const [secondsLeft, setSecondsLeft] = useState(0)
  // who the ring is following on a live call: SHEFA while its words play, otherwise the caller
  const [agentTalking, setAgentTalking] = useState(false)
  const shownTheme = useShownTheme()
  const calm = useReducedMotion()
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

  // the ring's level is read straight from the call every frame; only the speaker needs React
  useEffect(() => {
    if (state !== 'live') return
    const timer = window.setInterval(() => setAgentTalking(call.current?.agentSpeaking() ?? false), 120)
    return () => {
      window.clearInterval(timer)
      setAgentTalking(false)
    }
  }, [state])

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
    const slow = window.setTimeout(() => setSlowReply(true), 800)
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
      window.clearTimeout(slow)
      setSlowReply(false)
      setSending(false)
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    void send(draft)
  }

  const live = state === 'live'
  const ringState = state === 'connecting' ? 'processing' : live ? (agentTalking ? 'speaking' : 'listening') : 'idle'
  const time = `${digits.format(Math.floor(secondsLeft / 60))}:${secondsLeft % 60 < 10 ? digits.format(0) : ''}${digits.format(secondsLeft % 60)}`

  if (info && !info.enabled) return null

  return (
    <div className="patient demo">
      <header className="p-top">
        <span className="p-brand">
          <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden="true">
            <rect width="32" height="32" rx="8" fill="var(--brand)" />
            <rect x="0.75" y="0.75" width="30.5" height="30.5" rx="7.25" fill="none" stroke="rgba(255,255,255,0.35)" strokeWidth="1.5" />
            <g transform="rotate(-38 16 16)">
              <rect x="6" y="11.5" width="20" height="9" rx="4.5" fill="#fff" />
              <path d="M16 11.5h5.5a4.5 4.5 0 0 1 0 9H16z" fill="#c9b8f4" />
            </g>
          </svg>
          {t.brand}
        </span>
        <div className="p-prefs">
          <ThemeSwitch labels={lang === 'bn' ? { group: 'থিম', auto: 'ডিভাইসের মতো', light: 'আলো', dark: 'অন্ধকার' } : { group: 'Theme', auto: 'Follow this device', light: 'Light', dark: 'Dark' }} />
          <button type="button" className="p-lang" onClick={() => setLang(lang === 'bn' ? 'en' : 'bn')}>
            {t.language}
          </button>
        </div>
      </header>
      <main className="p-main">
        <h1>{t.title}</h1>
        <p className="p-lead">{t.lead}</p>
        <p className="demo-sample">{t.sample}</p>

        <section className="demo-call" aria-label={t.start}>
          <div className="demo-orb-wrap">
            {/* the assistant's ring of light: decoration, so hidden from screen readers; the button
                and the status line below carry everything it shows */}
            <div className="demo-ring" aria-hidden="true">
              <VoiceRing
                size={272}
                state={ringState}
                level={() => call.current?.level() ?? 0}
                theme={shownTheme}
                paused={calm}
              />
            </div>
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
          </div>
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
              {sending && slowReply ? (
                <li className="demo-line demo-assistant demo-pending">
                  <small>{t.agent}</small>
                  <p>
                    <ThinkingOrb state="composing" size={20} aria-hidden="true" />
                    {t.writing}
                  </p>
                </li>
              ) : null}
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
