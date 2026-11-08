import { useState, type FormEvent } from 'react'
import { useAuth } from '../lib/auth'
import { useI18n } from '../lib/i18n'
import { LangSwitch, Logo } from '../Shell'

export function SignIn() {
  const { signIn } = useAuth()
  const { t } = useI18n()
  const [useToken, setUseToken] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [token, setToken] = useState('')
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)
  const [offline, setOffline] = useState(false)

  const ready = useToken ? token.trim() : username.trim() && password

  async function submit(event: FormEvent) {
    event.preventDefault()
    setBusy(true)
    setFailed(false)
    setOffline(false)
    try {
      const ok = await signIn(useToken ? { token: token.trim() } : { username: username.trim(), password })
      setFailed(!ok)
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
        {useToken ? (
          <>
            <p className="muted">{t('signInIntro')}</p>
            <label htmlFor="token">{t('token')}</label>
            <input
              id="token"
              type="password"
              autoComplete="off"
              value={token}
              onChange={(e) => setToken(e.target.value)}
              aria-describedby="token-help login-error"
              aria-invalid={failed}
            />
            <p id="token-help" className="hint">
              {t('tokenHelp')}
            </p>
          </>
        ) : (
          <>
            <label htmlFor="username">{t('username')}</label>
            <input
              id="username"
              autoComplete="username"
              autoCapitalize="none"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              aria-invalid={failed}
            />
            <label htmlFor="password">{t('password')}</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-describedby="login-error"
              aria-invalid={failed}
            />
          </>
        )}
        <p id="login-error" className="field-error" role="alert">
          {failed ? (useToken ? t('wrongToken') : t('wrongLogin')) : offline ? t('offline') : ''}
        </p>
        <button className="btn btn-primary" type="submit" disabled={busy || !ready}>
          {busy ? t('signingIn') : t('signIn')}
        </button>
        <button
          type="button"
          className="btn btn-quiet"
          onClick={() => {
            setUseToken(!useToken)
            setFailed(false)
          }}
        >
          {useToken ? t('usePassword') : t('useToken')}
        </button>
      </form>
    </main>
  )
}
