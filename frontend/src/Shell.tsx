import { useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { CalendarDays, ChartNoAxesColumn, ClipboardList, FileText, LogOut, Mic, PhoneCall, Radio, Settings2, Stethoscope, Users } from 'lucide-react'
import { useAuth } from './lib/auth'
import { setSound, soundOn, useDeskAlert } from './lib/deskAlert'
import { useI18n, type Lang } from './lib/i18n'

/** SHEFA's mark: a capsule on a pharma-green box, half white, half SHEFA blue.
 * Drawn, not lettered, so it reads the same in Bangla and English. */
export function Logo({ size = 30 }: { size?: number }) {
  return (
    <span className="logo" aria-hidden="true">
      <svg viewBox="0 0 32 32" width={size} height={size}>
        <rect width="32" height="32" rx="8" fill="var(--rail)" />
        <rect x="0.75" y="0.75" width="30.5" height="30.5" rx="7.25" fill="none" stroke="oklch(1 0 0 / 0.35)" strokeWidth="1.5" />
        <g transform="rotate(-38 16 16)">
          <rect x="6" y="11.5" width="20" height="9" rx="4.5" fill="#fff" />
          <path d="M16 11.5h5.5a4.5 4.5 0 0 1 0 9H16z" fill="var(--shefa)" />
        </g>
      </svg>
    </span>
  )
}

/** The colour legend: one colour, one meaning, everywhere. */
export function Legend({ className }: { className: string }) {
  const { t } = useI18n()
  return (
    <dl className={className} aria-label={t('legendTitle')}>
      <div className="lg-urgent"><dt /><dd>{t('legendUrgent')}</dd></div>
      <div className="lg-waiting"><dt /><dd>{t('legendWaiting')}</dd></div>
      <div className="lg-done"><dt /><dd>{t('legendDone')}</dd></div>
      <div className="lg-shefa"><dt /><dd>{t('legendShefa')}</dd></div>
    </dl>
  )
}

export function Wordmark() {
  const { lang } = useI18n()
  return (
    <span className="brand">
      <Logo />
      <span className="brand-name" aria-hidden="true">
        <span className="brand-en" lang="en">SHEFA</span>
        <span className="brand-bn" lang="bn">শেফা</span>
      </span>
      <span className="visually-hidden">{lang === 'bn' ? 'শেফা' : 'SHEFA'}</span>
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
  const alert = useDeskAlert(can('records:read'))
  const [sound, setSoundState] = useState(soundOn)
  const items = [
    { to: '/live', label: t('navLive'), icon: Radio, show: can('records:read') },
    { to: '/overview', label: t('navOverview'), icon: ChartNoAxesColumn, show: can('overview:read') },
    { to: '/report', label: t('navReport'), icon: FileText, show: can('overview:read') },
    { to: '/calls', label: t('navCalls'), icon: PhoneCall, show: can('records:read') },
    { to: '/appointments', label: t('navAppointments'), icon: CalendarDays, show: can('records:read') },
    { to: '/doctors', label: t('navDoctors'), icon: Stethoscope, show: can('records:read') },
    { to: '/setup', label: t('navSetup'), icon: Settings2, show: can('directory:write') },
    { to: '/staff', label: t('navStaff'), icon: Users, show: can('staff:manage') },
    { to: '/my-day', label: t('navMyDay'), icon: ClipboardList, show: can('doctor:self') },
  ].filter((i) => i.show)

  return (
    <div className="shell">
      <a className="skip" href="#main">
        {t('skip')}
      </a>
      <aside className="side">
        <Wordmark />
        <nav aria-label={t('navMain')}>
          {items.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) => `nav-item${isActive ? " active" : ""}`}>
              <span className="nav-icon" aria-hidden="true">
                <Icon size={16} strokeWidth={2} />
              </span>
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <Legend className="rail-legend" />
        <div className="side-foot">
          {can('calls:place') ? (
            <a className="nav-item" href="/console">
              <Mic size={18} strokeWidth={1.75} aria-hidden="true" />
              <span>{t('consoleLink')}</span>
            </a>
          ) : null}
          {can('records:read') ? (
            <label className="nav-item sound-toggle">
              <input type="checkbox" checked={sound} onChange={(e) => { setSound(e.target.checked); setSoundState(e.target.checked) }} />
              <span>{t('alertSound')}</span>
            </label>
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
        {alert.fresh.length ? (
          <div className="desk-alert" role="alert">
            <strong>{t('needsPerson')}</strong>
            <span>{alert.fresh.map((c) => c.reason || c.phone || '').filter(Boolean).join(' · ')}</span>
            <Link className="btn btn-small btn-urgent" to="/live" onClick={alert.dismiss}>
              {t('openCallbacks')}
            </Link>
            <button type="button" className="btn btn-small" onClick={alert.dismiss}>
              {t('dismiss')}
            </button>
          </div>
        ) : null}
        <Outlet />
      </main>
    </div>
  )
}
