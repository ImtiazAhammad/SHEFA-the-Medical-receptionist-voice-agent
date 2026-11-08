import { useMemo, useState } from 'react'
import { api, type Department, type Doctor } from '../lib/api'
import { useI18n } from '../lib/i18n'
import { useLoad } from '../lib/useLoad'
import { languageName } from '../lib/labels'
import { Empty, ErrorNote, PageHeader, Skeleton } from '../components'

function matches(doc: Doctor, query: string): boolean {
  const q = query.trim().toLowerCase()
  if (!q) return true
  const hay = [
    doc.name,
    doc.name_bn,
    doc.department,
    doc.department_bn,
    doc.designation,
    ...(doc.conditions?.en ?? []),
    ...(doc.conditions?.bn ?? []),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return hay.includes(q)
}

function DoctorCard({ doc }: { doc: Doctor }) {
  const { t, pick, num, date, clock, lang } = useI18n()
  const conditions = (lang === 'bn' ? doc.conditions?.bn : doc.conditions?.en) ?? doc.conditions?.en ?? []
  const fee = doc.fees?.new ?? doc.visit_fee
  const next = doc.next_available
  return (
    <article className="doc">
      <h3>
        {t('doctor')} {pick(doc.name, doc.name_bn)}
      </h3>
      <p className="muted">
        {[doc.designation, doc.qualification].filter(Boolean).join(' · ')}
      </p>
      <dl className="facts">
        {doc.room ? (
          <>
            <dt>{t('room')}</dt>
            <dd>{doc.room}</dd>
          </>
        ) : null}
        {fee != null ? (
          <>
            <dt>{t('fee')}</dt>
            <dd>৳{num(fee)}</dd>
          </>
        ) : null}
        {doc.experience_years ? (
          <>
            <dt>{t('experienceLabel')}</dt>
            <dd>{t('experience', { n: num(doc.experience_years) })}</dd>
          </>
        ) : null}
        {doc.languages?.length ? (
          <>
            <dt>{t('speaks')}</dt>
            <dd>{doc.languages.map(languageName).join(', ')}</dd>
          </>
        ) : null}
        <dt>{t('nextFree')}</dt>
        <dd>{next ? `${date(next.date)} · ${clock(next.time)}` : t('noFreeTime')}</dd>
      </dl>
      {conditions.length > 0 ? (
        <p>
          <strong>{t('seesFor')}:</strong> {conditions.join(', ')}
        </p>
      ) : null}
      <details>
        <summary>{t('hours')}</summary>
        {doc.schedule.length ? (
          <ul className="plain">
            {doc.schedule.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
        ) : (
          <p className="muted">{t('noHours')}</p>
        )}
      </details>
    </article>
  )
}

export function Doctors() {
  const { t, pick } = useI18n()
  const [query, setQuery] = useState('')
  const dir = useLoad(() => api<Department[]>('/api/v1/directory'), [])
  const groups = useMemo(
    () =>
      (dir.data ?? [])
        .map((d) => ({ ...d, doctors: d.doctors.filter((doc) => matches(doc, query)) }))
        .filter((d) => d.doctors.length > 0),
    [dir.data, query],
  )

  return (
    <>
      <PageHeader title={t('doctorsTitle')}>
        <input
          type="search"
          className="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t('searchDoctors')}
          aria-label={t('searchDoctors')}
        />
      </PageHeader>
      {dir.error ? <ErrorNote error={dir.error} onRetry={dir.reload} /> : null}
      {dir.loading && !dir.data ? <Skeleton rows={5} /> : null}
      {dir.data && dir.data.length === 0 ? <Empty title={t('noDirectory')} /> : null}
      {dir.data && dir.data.length > 0 && groups.length === 0 ? <Empty title={t('noDoctors')} /> : null}
      {groups.map((g) => (
        <section key={g.name} aria-labelledby={`dep-${g.name}`}>
          <h2 id={`dep-${g.name}`}>{pick(g.name, g.name_bn)}</h2>
          <div className="doc-grid">
            {g.doctors.map((doc) => (
              <DoctorCard key={doc.name} doc={doc} />
            ))}
          </div>
        </section>
      ))}
    </>
  )
}
