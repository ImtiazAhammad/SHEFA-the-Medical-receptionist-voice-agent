import { useEffect, useRef, type ReactNode } from 'react'
import { AlertTriangle, WifiOff, X } from 'lucide-react'
import { ApiError } from './lib/api'
import { useI18n } from './lib/i18n'

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <header className="page-head">
      <h1 className="display">{title}</h1>
      {children ? <div className="page-tools">{children}</div> : null}
    </header>
  )
}

export function Skeleton({ rows = 4 }: { rows?: number }) {
  const { t } = useI18n()
  return (
    <div className="skeleton" role="status" aria-label={t('loading')}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton-row" />
      ))}
    </div>
  )
}

export function Empty({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="empty">
      <p className="empty-title">{title}</p>
      {hint ? <p className="empty-hint">{hint}</p> : null}
      {action}
    </div>
  )
}

/** A failed load names the problem and offers the way out; stale data stays visible above it. */
export function ErrorNote({ error, onRetry }: { error: ApiError; onRetry: () => void }) {
  const { t } = useI18n()
  const message = error.status === 0 ? t('offline') : error.status === 403 ? t('denied') : t('failed')
  const Icon = error.status === 0 ? WifiOff : AlertTriangle
  return (
    <div className="note note-error" role="alert">
      <Icon size={18} aria-hidden="true" />
      <span>{message}</span>
      {error.status !== 403 ? (
        <button type="button" className="btn btn-quiet" onClick={onRetry}>
          {t('retry')}
        </button>
      ) : null}
    </div>
  )
}

export type Tone = 'ok' | 'warn' | 'bad' | 'info' | 'quiet' | 'gone' | 'sel' | 'shefa' | 'live'

/** A state mark: the legend's colour (red needs a person, amber waiting, green done, blue SHEFA) AND words;
 * the drawing never carries meaning alone. `info` reads as a plain settled frame. */
export function Pill({ tone, children }: { tone: Tone; children: ReactNode }) {
  const cls = tone === 'info' ? 'ok' : tone === 'live' ? 'shefa mark-live' : tone
  return <span className={`mark mark-${cls}`}>{children}</span>
}

/** A doctor's box colour: the same doctor wears the same colour on every screen. */
export function docClass(id: number | undefined | null): string {
  return id == null ? '' : `doc-c${Math.abs(id) % 6}`
}

/**
 * A sheet laid over the page, sliding in from the side like a box pulled from the shelf.
 * It is a modal <dialog>: Esc and the close button leave, focus stays inside while it is open
 * and returns to where it was. The page under it stays visible.
 */
export function Sheet({ label, onClose, children }: { label: string; onClose: () => void; children: ReactNode }) {
  const { t } = useI18n()
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current
    const before = document.activeElement as HTMLElement | null
    if (dialog && !dialog.open) dialog.showModal()
    return () => {
      before?.focus?.()
    }
  }, [])
  return (
    <dialog
      ref={ref}
      className="sheet"
      aria-label={label}
      onCancel={(e) => {
        e.preventDefault()
        onClose()
      }}
      onClick={(e) => {
        if (e.target === ref.current) onClose()
      }}
    >
      <div className="sheet-body">
        <div className="sheet-bar">
          <span className="legend">{label}</span>
          <button type="button" className="btn btn-small btn-quiet" onClick={onClose}>
            <X size={16} aria-hidden="true" /> {t('close')}
          </button>
        </div>
        {children}
      </div>
    </dialog>
  )
}

export function durationText(seconds: number | null, t: ReturnType<typeof useI18n>['t'], num: (n: number) => string) {
  if (seconds == null) return '-'
  const s = Math.round(seconds)
  return s >= 60 ? `${num(Math.floor(s / 60))} ${t('min')} ${num(s % 60)} ${t('sec')}` : `${num(s)} ${t('sec')}`
}
