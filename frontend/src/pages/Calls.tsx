import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Languages } from 'lucide-react'
import { api, type CallDetail, type CallRow } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useLoad } from '../lib/useLoad'
import { Empty, ErrorNote, PageHeader, Pill, Skeleton, durationText } from '../components'
import { CallStatus } from './Live'
import { actionLabel, dispositionLabel } from '../lib/labels'

const LOW_CONFIDENCE = 0.6

export function Calls() {
  const { t, num, date, lang } = useI18n()
  const calls = useLoad(() => api<CallRow[]>('/api/v1/calls?limit=200'), [], 10000)
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
                <th scope="col">{t('disposition')}</th>
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
                  <td>
                    {c.started_at ? date(c.started_at, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Dhaka' }) : '—'}
                  </td>
                  <td>{c.direction === 'outbound' ? t('outbound') : t('inbound')}</td>
                  <td>
                    <CallStatus call={c} />
                  </td>
                  <td>{dispositionLabel(c.disposition, lang)}</td>
                  <td className="num">{durationText(c.duration_seconds, t, num)}</td>
                  <td>
                    <Link to={`/calls/${encodeURIComponent(c.call_sid)}`}>{t('open')}</Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </>
  )
}

export function CallPage() {
  const { sid = '' } = useParams()
  const { t, num, date, lang } = useI18n()
  const call = useLoad(() => api<CallDetail>(`/api/v1/calls/${encodeURIComponent(sid)}`), [sid], 3000)
  const d = call.data

  return (
    <>
      <Link className="back" to="/calls">
        <ArrowLeft size={16} aria-hidden="true" /> {t('back')}
      </Link>
      <PageHeader title={t('transcript')}>{d ? <CallStatus call={d} /> : null}</PageHeader>
      {call.error ? <ErrorNote error={call.error} onRetry={call.reload} /> : null}
      {call.loading && !d ? <Skeleton rows={5} /> : null}
      {d ? (
        <>
          <p className="muted meta">
            {d.started_at ? date(d.started_at, { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Dhaka' }) : ''} ·{' '}
            {durationText(d.duration_seconds, t, num)}
            {d.disposition ? ` · ${dispositionLabel(d.disposition, lang)}` : ''}
          </p>
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
                        {' '}
                        · {date(turn.at, { timeStyle: 'medium', timeZone: 'Asia/Dhaka' })}
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
                        <Pill key={a} tone="info">
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
        </>
      ) : null}
    </>
  )
}
