import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider, useAuth } from './lib/auth'
import { I18nProvider, useI18n } from './lib/i18n'
import { Shell } from './Shell'
import { SignIn } from './pages/SignIn'
import { Live } from './pages/Live'
import { Calls, CallPage } from './pages/Calls'
import { Appointments } from './pages/Appointments'
import { Doctors } from './pages/Doctors'
import { Skeleton } from './components'

function Gate() {
  const { me } = useAuth()
  const { t } = useI18n()
  if (me === null)
    return (
      <main className="boot" aria-busy="true">
        <p className="muted">{t('loading')}</p>
        <Skeleton rows={2} />
      </main>
    )
  if (!me.signed_in) return <SignIn />
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Navigate to="/live" replace />} />
        <Route path="live" element={<Live />} />
        <Route path="calls" element={<Calls />} />
        <Route path="calls/:sid" element={<CallPage />} />
        <Route path="appointments" element={<Appointments />} />
        <Route path="doctors" element={<Doctors />} />
        <Route path="*" element={<Navigate to="/live" replace />} />
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
