import { Link } from 'react-router-dom'
import { useState } from 'react'
import { Phone } from 'lucide-react'
import { api, type Callback, type CallRow } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { useLoad } from '../lib/useLoad'
import { Empty, ErrorNote, PageHeader, Pill, Skeleton, durationText } from '../components'

export function CallStatus({ call }: { call: CallRow }) {
  const { t } = useI18n()
  return call.status === 'in_progress' ? <Pill tone="info">{t('inProgress')}</Pill> : <Pill tone="quiet">{t('completed')}</Pill>
}

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

  return (
    <section aria-labelledby="cb-h" aria-live="polite">
      <h2 id="cb-h">{t('callbacksTitle')}</h2>
      {list.error ? <ErrorNote error={list.error} onRetry={list.reload} /> : null}
      {list.data && list.data.length === 0 ? <Empty title={t('noCallbacks')} /> : null}
      <ul className="rows">
        {(list.data ?? []).map((c) => (
          <li key={c.id} className="row">
            <Phone size={18} aria-hidden="true" />
            {c.phone ? (
              <a href={`tel:${c.phone}`} className="phone">
                {c.phone}
              </a>
            ) : (
              <span className="muted">—</span>
            )}
            <span className="muted">
              {t('waiting', { when: date(c.created_at, { timeStyle: 'short', dateStyle: 'medium', timeZone: 'Asia/Dhaka' }) })}
            </span>
            {can('records:write') ? (
              <button
                type="button"
                className="btn btn-small row-end"
                disabled={busy === c.id}
                onClick={() => void resolve(c.id)}
              >
                {busy === c.id ? t('resolving') : t('resolve')}
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  )
}

export function Live() {
  const { t, num, date } = useI18n()
  const calls = useLoad(() => api<CallRow[]>('/api/v1/calls?limit=30'), [], 3000)
  const active = (calls.data ?? []).filter((c) => c.status === 'in_progress')
  const recent = (calls.data ?? []).filter((c) => c.status !== 'in_progress').slice(0, 8)
  const last = recent[0]?.started_at

  return (
    <>
      <PageHeader title={t('liveTitle')} />
      <Callbacks />
      <h2>{t('inProgress')}</h2>
      {calls.error ? <ErrorNote error={calls.error} onRetry={calls.reload} /> : null}
      {calls.loading && !calls.data ? <Skeleton /> : null}
      {calls.data ? (
        <>
          <section aria-labelledby="active-h" aria-live="polite">
            <h2 id="active-h" className="visually-hidden">
              {t('liveTitle')}
            </h2>
            {active.length === 0 ? (
              <Empty
                title={t('noCallsNow')}
                hint={last ? t('lastCall', { when: date(last, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Dhaka' }) }) : t('noCallsYet')}
              />
            ) : (
              <ul className="rows">
                {active.map((c) => (
                  <li key={c.call_sid}>
                    <Link className="row" to={`/calls/${encodeURIComponent(c.call_sid)}`}>
                      <CallStatus call={c} />
                      <span>{c.direction === 'outbound' ? t('outbound') : t('inbound')}</span>
                      <span className="muted">
                        {c.started_at ? date(c.started_at, { timeStyle: 'short', timeZone: 'Asia/Dhaka' }) : ''}
                      </span>
                      <span className="row-end">{t('open')}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
          {recent.length > 0 ? (
            <section aria-labelledby="recent-h">
              <h2 id="recent-h">{t('recentTitle')}</h2>
              <ul className="rows">
                {recent.map((c) => (
                  <li key={c.call_sid}>
                    <Link className="row" to={`/calls/${encodeURIComponent(c.call_sid)}`}>
                      <CallStatus call={c} />
                      <span>{c.direction === 'outbound' ? t('outbound') : t('inbound')}</span>
                      <span className="muted">
                        {c.started_at ? date(c.started_at, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Dhaka' }) : ''}
                      </span>
                      <span className="row-end">{durationText(c.duration_seconds, t, num)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </>
      ) : null}
    </>
  )
}
