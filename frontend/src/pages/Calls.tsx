import { Link, Outlet, useNavigate, useParams } from 'react-router-dom'
import { Languages } from 'lucide-react'
import { api, type CallDetail, type CallRow } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useLoad } from '../lib/useLoad'
import { Empty, ErrorNote, PageHeader, Pill, Sheet, Skeleton, durationText } from '../components'
import { useAuth } from '../lib/auth'
import { CallStatus } from './Live'
import { actionLabel, dispositionLabel } from '../lib/labels'
import { summaryText, type Formatters } from '../lib/summary'

const LOW_CONFIDENCE = 0.6

/** Day and clock words in the staff member's language, for the one-line call summary. */
function useFormatters(): Formatters {
  const { date, clock } = useI18n()
  return {
    day: (iso) => date(iso, { dateStyle: 'medium', timeZone: 'Asia/Dhaka' }),
    clock,
  }
}

export function Calls() {
  const { t, num, date, lang } = useI18n()
  const calls = useLoad(() => api<CallRow[]>('/api/v1/calls?limit=200'), [], 10000)
  const fmt = useFormatters()
  return (
    <>
      <PageHeader title={t('callsTitle')} />
      {calls.error ? <ErrorNote error={calls.error} onRetry={calls.reload} /> : null}
      {calls.loading && !calls.data ? <Skeleton rows={6} /> : null}
      {calls.data && calls.data.length === 0 ? <Empty title={t('noCallsYet')} /> : null}
      {calls.data && calls.data.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t('started')}</th>
                <th scope="col">{t('direction')}</th>
                <th scope="col">{t('status')}</th>
                <th scope="col">{t('whatHappened')}</th>
                <th scope="col" className="num">
                  {t('duration')}
                </th>
                <th scope="col">
                  <span className="visually-hidden">{t('open')}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {calls.data.map((c) => (
                <tr key={c.call_sid}>
                  <td className="num">
                    <Link to={encodeURIComponent(c.call_sid)}>
                      {c.started_at ? date(c.started_at, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Dhaka' }) : '—'}
                    </Link>
                  </td>
                  <td>{c.direction === 'outbound' ? t('outbound') : t('inbound')}</td>
                  <td>
                    <CallStatus call={c} />
                  </td>
                  <td>
                    {(() => {
                      const line = summaryText(c.summary, lang, fmt)
                      return line ? (
                        <>
                          <Pill tone={line.tone}>{dispositionLabel(c.disposition, lang)}</Pill>
                          <div className="call-summary">{line.text}</div>
                        </>
                      ) : (
                        dispositionLabel(c.disposition, lang)
                      )
                    })()}
                  </td>
                  <td className="num">{durationText(c.duration_seconds, t, num)}</td>
                  <td>
                    <Link className="btn btn-small btn-quiet" to={encodeURIComponent(c.call_sid)}>
                      {t('open')}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
      <Outlet />
    </>
  )
}

/** One call, laid over the list it was opened from: the list stays where it was. */
export function CallSheet({ back }: { back: string }) {
  const { sid = '' } = useParams()
  const { t, num, date, lang } = useI18n()
  const call = useLoad(() => api<CallDetail>(`/api/v1/calls/${encodeURIComponent(sid)}`), [sid], 3000)
  const d = call.data
  const fmt = useFormatters()
  const { can } = useAuth()
  const navigate = useNavigate()
  const close = () => navigate(back)
  const prefix = back === '/live' ? '/live/call/' : '/calls/'

  async function erase() {
    if (!window.confirm(t('deleteConfirm'))) return
    await api(`/api/v1/calls/${encodeURIComponent(sid)}`, { method: 'DELETE' })
    close()
  }

  return (
    <Sheet label={t('callSheet')} onClose={close}>
      <header className="page-head">
        <h2 className="display sheet-title">{t('transcript')}</h2>
        {d ? <CallStatus call={d} /> : null}
      </header>
      {call.error ? <ErrorNote error={call.error} onRetry={call.reload} /> : null}
      {call.loading && !d ? <Skeleton rows={5} /> : null}
      {d ? (
        <>
          <p className="muted meta">
            {d.started_at ? date(d.started_at, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Dhaka' }) : ''} ·{' '}
            {durationText(d.duration_seconds, t, num)}
            {d.disposition ? ` · ${dispositionLabel(d.disposition, lang)}` : ''}
          </p>
          {(() => {
            const line = summaryText(d.summary, lang, fmt)
            return line ? (
              <section className="summary-card" aria-label={t('whatHappened')}>
                <h2>{t('whatHappened')}</h2>
                <p>
                  <Pill tone={line.tone}>{dispositionLabel(d.disposition, lang)}</Pill> {line.text}
                </p>
              </section>
            ) : null
          })()}
          {d.earlier_calls && d.earlier_calls.length > 0 ? (
            <section className="summary-card" aria-label={t('earlierCalls')}>
              <h2>{t('earlierCalls')}</h2>
              <ul className="earlier">
                {d.earlier_calls.map((e) => (
                  <li key={e.call_sid}>
                    <Link to={`${prefix}${encodeURIComponent(e.call_sid)}`}>
                      {e.started_at ? date(e.started_at, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Dhaka' }) : '—'}
                    </Link>{' '}
                    <span className="muted">{summaryText(e.summary, lang, fmt)?.text ?? dispositionLabel(e.disposition, lang)}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
          {d.turns.length === 0 ? (
            <Empty title={t('noTurns')} />
          ) : (
            <ol className="turns">
              {d.turns.map((turn) => {
                const low = turn.role === 'user' && turn.confidence != null && turn.confidence < LOW_CONFIDENCE
                return (
                  <li key={turn.idx} className={`turn turn-${turn.role}`}>
                    <div className="turn-who">
                      {turn.role === 'user' ? t('caller') : t('agent')}
                      <span className="muted">
                        {date(turn.at, { timeStyle: 'medium', timeZone: 'Asia/Dhaka' })}
                      </span>
                    </div>
                    <p className="turn-text" lang={turn.language === 'en' ? 'en' : 'bn'}>
                      {turn.text}
                    </p>
                    <div className="turn-meta">
                      {turn.language ? (
                        <span className="chip">
                          <Languages size={14} aria-hidden="true" /> {turn.language === 'bn' ? 'বাংলা' : 'English'}
                        </span>
                      ) : null}
                      {turn.confidence != null ? (
                        <span className="chip">{t('heardAt', { pct: `${num(Math.round(turn.confidence * 100))}%` })}</span>
                      ) : null}
                      {low ? <Pill tone="warn">{t('lowConfidence')}</Pill> : null}
                      {turn.actions.map((a) => (
                        <Pill key={a} tone="shefa">
                          {actionLabel(a, lang)}
                        </Pill>
                      ))}
                      {turn.note ? <span className="chip" lang="en">{turn.note}</span> : null}
                    </div>
                  </li>
                )
              })}
            </ol>
          )}
          {can('records:write') ? (
            <div className="danger-zone">
              <button type="button" className="btn btn-small btn-danger" onClick={() => void erase()}>
                {t('deleteCall')}
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </Sheet>
  )
}
