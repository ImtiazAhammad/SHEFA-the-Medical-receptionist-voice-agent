import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './lib/auth'
import { I18nProvider, useI18n } from './lib/i18n'
import { Shell } from './Shell'
import { SignIn } from './pages/SignIn'
import { Live } from './pages/Live'
import { Calls, CallPage } from './pages/Calls'
import { Appointments } from './pages/Appointments'
import { Doctors } from './pages/Doctors'
import { Overview } from './pages/Overview'
import { MyDay } from './pages/MyDay'
import { Staff } from './pages/Staff'
import { Setup } from './pages/Setup'
import { Skeleton } from './components'

/** A page the signed-in role may not open sends them to their own home instead. */
function Need({ permission, home }: { permission: string; home: string }) {
  const { can } = useAuth()
  return can(permission) ? <Outlet /> : <Navigate to={home} replace />
}

function Gate() {
  const { me, can } = useAuth()
  const { t } = useI18n()
  if (me === null)
    return (
      <main className="boot" aria-busy="true">
        <p className="muted">{t('loading')}</p>
        <Skeleton rows={2} />
      </main>
    )
  if (!me.signed_in) return <SignIn />
  const home = can('records:read') ? '/live' : '/my-day'
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Navigate to={home} replace />} />
        <Route element={<Need permission="doctor:self" home={home} />}>
          <Route path="my-day" element={<MyDay />} />
        </Route>
        <Route element={<Need permission="records:read" home={home} />}>
          <Route path="live" element={<Live />} />
          <Route path="calls" element={<Calls />} />
          <Route path="calls/:sid" element={<CallPage />} />
          <Route path="appointments" element={<Appointments />} />
          <Route path="doctors" element={<Doctors />} />
        </Route>
        <Route element={<Need permission="overview:read" home={home} />}>
          <Route path="overview" element={<Overview />} />
        </Route>
        <Route element={<Need permission="staff:manage" home={home} />}>
          <Route path="staff" element={<Staff />} />
        </Route>
        <Route element={<Need permission="directory:write" home={home} />}>
          <Route path="setup" element={<Setup />} />
        </Route>
        <Route path="*" element={<Navigate to={home} replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <I18nProvider>
      <AuthProvider>
        <BrowserRouter basename="/app">
          <Gate />
        </BrowserRouter>
      </AuthProvider>
    </I18nProvider>
  )
}
