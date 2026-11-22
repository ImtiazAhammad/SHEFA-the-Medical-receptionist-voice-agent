import { lazy, StrictMode, Suspense } from 'react'
import { createRoot } from 'react-dom/client'
// The shared SHEFA world (tokens, controls, state marks). Each app adds its own fonts and layout.
import '@world/world.css'

// Three apps share one build: the staff app at /app, the public booking page at /book and the
// public demo at /demo. Each is its own chunk, so a patient on a slow phone never downloads the
// staff app.
const path = window.location.pathname
const Staff = lazy(() => import('./App'))
const Patient = lazy(() => import('./patient/PatientApp'))
const Demo = lazy(() => import('./demo/DemoApp'))
const Page = path.startsWith('/demo') ? Demo : path.startsWith('/book') ? Patient : Staff

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Suspense fallback={null}><Page /></Suspense>
  </StrictMode>,
)
