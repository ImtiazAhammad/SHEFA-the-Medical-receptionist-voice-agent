import { useState, type FormEvent } from 'react'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { LangSwitch, Logo } from '../Shell'

export function SignIn() {
  const { signIn } = useAuth()
  const { t } = useI18n()
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const [offline, setOffline] = useState(false)

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setFailed(false)
    setOffline(false)
    try {
      setFailed(!(await signIn(token.trim())))
    } catch {
      setOffline(true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <main className="signin">
      <div className="signin-top">
        <LangSwitch />
      </div>
      <form className="signin-card" onSubmit={submit}>
        <Logo />
        <h1>{t('signIn')}</h1>
        <p className="muted">{t('signInIntro')}</p>
        <label htmlFor="token">{t('token')}</label>
        <input
          id="token"
          type="password"
          autoComplete="current-password"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          aria-describedby="token-help token-error"
          aria-invalid={failed}
          required
        />
        <p id="token-help" className="hint">
          {t('tokenHelp')}
        </p>
        <p id="token-error" className="field-error" role="alert">
          {failed ? t('wrongToken') : offline ? t('offline') : ''}
        </p>
        <button className="btn btn-primary" type="submit" disabled={busy || !token.trim()}>
          {busy ? t('signingIn') : t('signIn')}
        </button>
      </form>
    </main>
  )
}
