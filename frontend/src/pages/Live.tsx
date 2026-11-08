import { Link } from 'react-router-dom'
import { api, type CallRow } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useLoad } from '../lib/useLoad'
import { Empty, ErrorNote, PageHeader, Pill, Skeleton, durationText } from '../components'

export function CallStatus({ call }: { call: CallRow }) {
  const { t } = useI18n()
  return call.status === 'in_progress' ? <Pill tone="info">{t('inProgress')}</Pill> : <Pill tone="quiet">{t('completed')}</Pill>
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
