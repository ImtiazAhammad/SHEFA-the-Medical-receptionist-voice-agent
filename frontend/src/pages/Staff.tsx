import { useState, type FormEvent } from 'react'
import { api, ApiError, type DoctorChoice, type StaffUser } from '../lib/api'
import { useAuth } from '../lib/auth'
import { useI18n, type Key } from '../lib/i18n'
import { useLoad } from '../lib/useLoad'
import { Empty, ErrorNote, PageHeader, Pill, Skeleton } from '../components'

const ROLES: [StaffUser['role'], Key][] = [
  ['desk', 'roleDesk'],
  ['owner', 'roleOwner'],
  ['doctor', 'roleDoctor'],
]

export function Staff() {
  const { t, pick } = useI18n()
  const { me } = useAuth()
  const users = useLoad(() => api<StaffUser[]>('/api/v1/staff'), [])
  const doctors = useLoad(() => api<DoctorChoice[]>('/api/v1/staff/doctors'), [])
  const [message, setMessage] = useState<{ tone: 'ok' | 'bad'; text: string } | null>(null)
  const [resetting, setResetting] = useState<string | null>(null)
  const [newPassword, setNewPassword] = useState('')
  const [form, setForm] = useState({ username: '', display_name: '', password: '', role: 'desk', doctor_id: '' })
  const [busy, setBusy] = useState(false)

  async function run(work: () => Promise<unknown>, okText: string) {
    setBusy(true)
    setMessage(null)
    try {
      await work()
      setMessage({ tone: 'ok', text: okText })
      users.reload()
      return true
    } catch (e) {
      if (!(e instanceof ApiError)) throw e
      setMessage({ tone: 'bad', text: t('staffError', { message: e.message }) })
      return false
    } finally {
      setBusy(false)
    }
  }

  async function add(e: FormEvent) {
    e.preventDefault()
    const ok = await run(
      () =>
        api('/api/v1/staff', {
          method: 'POST',
          body: JSON.stringify({
            ...form,
            doctor_id: form.role === 'doctor' && form.doctor_id ? Number(form.doctor_id) : null,
          }),
        }),
      t('accountAdded'),
    )
    if (ok) setForm({ username: '', display_name: '', password: '', role: 'desk', doctor_id: '' })
  }

  async function savePassword(username: string) {
    const ok = await run(
      () =>
        api(`/api/v1/staff/${encodeURIComponent(username)}/password`, {
          method: 'POST',
          body: JSON.stringify({ password: newPassword }),
        }),
      t('passwordChanged'),
    )
    if (ok) {
      setResetting(null)
      setNewPassword('')
    }
  }

  const roleName = (role: string) => t(ROLES.find(([r]) => r === role)?.[1] ?? 'roleDesk')
  const doctorName = (id: number | null) => {
    const d = doctors.data?.find((x) => x.id === id)
    return d ? pick(d.name, d.name_bn) : ''
  }

  return (
    <>
      <PageHeader title={t('staffTitle')} />
      <p className="muted meta">{t('staffIntro')}</p>
      {users.error ? <ErrorNote error={users.error} onRetry={users.reload} /> : null}
      {message ? (
        <div className={`note ${message.tone === 'bad' ? 'note-error' : ''}`} role={message.tone === 'bad' ? 'alert' : 'status'}>
          {message.text}
        </div>
      ) : null}
      {users.loading && !users.data ? <Skeleton rows={3} /> : null}
      {users.data && users.data.length === 0 ? <Empty title={t('staffTitle')} /> : null}
      {users.data && users.data.length > 0 ? (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">{t('displayName')}</th>
                <th scope="col">{t('roleLabel')}</th>
                <th scope="col">{t('status')}</th>
                <th scope="col">
                  <span className="visually-hidden">{t('open')}</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {users.data.map((u) => {
                const active = Boolean(u.active)
                return (
                  <tr key={u.username}>
                    <td>
                      {u.display_name}
                      <div className="muted small">{u.username}</div>
                    </td>
                    <td>
                      {roleName(u.role)}
                      {u.role === 'doctor' ? <div className="muted small">{doctorName(u.doctor_id)}</div> : null}
                    </td>
                    <td>
                      <Pill tone={active ? 'ok' : 'quiet'}>{t(active ? 'accountActive' : 'accountDisabled')}</Pill>
                    </td>
                    <td className="actions">
                      {resetting === u.username ? (
                        <span className="inline-field">
                          <input
                            type="password"
                            autoComplete="new-password"
                            aria-label={t('newPassword')}
                            value={newPassword}
                            minLength={10}
                            onChange={(e) => setNewPassword(e.target.value)}
                          />
                          <button type="button" className="btn btn-small btn-primary" disabled={busy || newPassword.length < 10} onClick={() => void savePassword(u.username)}>
                            {t('savePassword')}
                          </button>
                          <button type="button" className="btn btn-small" onClick={() => setResetting(null)}>
                            {t('cancel')}
                          </button>
                        </span>
                      ) : (
                        <>
                          <button type="button" className="btn btn-small" onClick={() => { setResetting(u.username); setNewPassword('') }}>
                            {t('resetPassword')}
                          </button>
                          {u.username !== me?.name ? (
                            <button
                              type="button"
                              className="btn btn-small"
                              disabled={busy}
                              onClick={() =>
                                void run(
                                  () =>
                                    api(`/api/v1/staff/${encodeURIComponent(u.username)}/active`, {
                                      method: 'POST',
                                      body: JSON.stringify({ active: !active }),
                                    }),
                                  t(active ? 'accountDisabled' : 'accountActive'),
                                )
                              }
                            >
                              {t(active ? 'disable' : 'enable')}
                            </button>
                          ) : null}
                        </>
                      )}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      ) : null}

      <h2 className="section-title">{t('addAccount')}</h2>
      <form className="stack" onSubmit={(e) => void add(e)}>
        <label className="inline-field">
          <span>{t('displayName')}</span>
          <input value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} required />
        </label>
        <label className="inline-field">
          <span>{t('username')}</span>
          <input value={form.username} autoComplete="off" onChange={(e) => setForm({ ...form, username: e.target.value })} required />
        </label>
        <label className="inline-field">
          <span>{t('roleLabel')}</span>
          <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
            {ROLES.map(([role, key]) => (
              <option key={role} value={role}>
                {t(key)}
              </option>
            ))}
          </select>
        </label>
        {form.role === 'doctor' ? (
          <label className="inline-field">
            <span>{t('linkedDoctor')}</span>
            <select value={form.doctor_id} onChange={(e) => setForm({ ...form, doctor_id: e.target.value })} required>
              <option value="" />
              {(doctors.data ?? []).map((d) => (
                <option key={d.id} value={d.id}>
                  {pick(d.name, d.name_bn)}
                </option>
              ))}
            </select>
          </label>
        ) : null}
        <label className="inline-field">
          <span>{t('password')}</span>
          <input type="password" autoComplete="new-password" minLength={10} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required aria-describedby="pw-help" />
        </label>
        <p id="pw-help" className="muted small">
          {t('passwordHelp')}
        </p>
        <button type="submit" className="btn btn-primary" disabled={busy}>
          {t('addAccount')}
        </button>
      </form>
    </>
  )
}
