import '@fontsource-variable/inter'
import '@fontsource-variable/noto-sans-bengali'
import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'

// Two apps share one build: the staff app at /app and the public booking page at /book. Each is
// its own chunk, so a patient on a slow phone never downloads the staff app.
const patient = window.location.pathname.startsWith('/book')
const Staff = lazy(() => import('./App'))
const Patient = lazy(() => import('./patient/PatientApp'))

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Suspense fallback={null}>{patient ? <Patient /> : <Staff />}</Suspense>
  </StrictMode>,
)
