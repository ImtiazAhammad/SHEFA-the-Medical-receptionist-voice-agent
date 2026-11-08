import { NavLink, Outlet } from 'react-router-dom'
import { CalendarDays, ChartNoAxesColumn, ClipboardList, LogOut, Mic, PhoneCall, Radio, Stethoscope } from 'lucide-react'
import { useAuth } from './lib/auth'
import { useI18n, type Lang } from './lib/i18n'

export function Logo() {
  return (
    <span className="logo" aria-hidden="true">
      <svg viewBox="0 0 32 32" width="28" height="28">
        <rect width="32" height="32" rx="8" fill="currentColor" />
        <path d="M16 8v16M8 16h16" stroke="var(--on-accent)" strokeWidth="4" strokeLinecap="round" />
      </svg>
    </span>
  )
}

export function LangSwitch() {
  const { lang, setLang, t } = useI18n()
  const options: [Lang, string][] = [
    ['bn', 'বাংলা'],
    ['en', 'English'],
  ]
  return (
    <div className="seg" role="group" aria-label={t('language')}>
      {options.map(([code, label]) => (
        <button
          key={code}
          type="button"
          lang={code}
          aria-pressed={lang === code}
          onClick={() => setLang(code)}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

export function Shell() {
  const { t } = useI18n()
  const { me, can, signOut } = useAuth()
  const items = [
    { to: '/live', label: t('navLive'), icon: Radio, show: can('records:read') },
    { to: '/overview', label: t('navOverview'), icon: ChartNoAxesColumn, show: can('overview:read') },
    { to: '/calls', label: t('navCalls'), icon: PhoneCall, show: can('records:read') },
    { to: '/appointments', label: t('navAppointments'), icon: CalendarDays, show: can('records:read') },
    { to: '/doctors', label: t('navDoctors'), icon: Stethoscope, show: can('records:read') },
    { to: '/my-day', label: t('navMyDay'), icon: ClipboardList, show: can('doctor:self') },
  ].filter((i) => i.show)

  return (
    <div className="shell">
      <a className="skip" href="#main">
        {t('skip')}
      </a>
      <aside className="side">
        <div className="brand">
          <Logo />
          <span className="brand-name">{t('appName')}</span>
        </div>
        <nav aria-label={t('navMain')}>
          {items.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
              <Icon size={20} aria-hidden="true" />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="side-foot">
          {can('calls:place') ? (
            <a className="nav-item" href="/console">
              <Mic size={20} aria-hidden="true" />
              <span>{t('consoleLink')}</span>
            </a>
          ) : null}
          <LangSwitch />
          <div className="who">
            <span className="who-name">{me?.name}</span>
            <button type="button" className="btn btn-quiet" onClick={() => void signOut()}>
              <LogOut size={16} aria-hidden="true" /> <span className="signout-label">{t('signOut')}</span>
            </button>
          </div>
        </div>
      </aside>
      <main id="main" className="main" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  )
}
