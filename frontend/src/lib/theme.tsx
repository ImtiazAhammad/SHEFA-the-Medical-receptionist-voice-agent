import { useState, useSyncExternalStore } from 'react'
import { useSegPill } from './motion'
import { Monitor, Moon, Sun } from 'lucide-react'

export type Theme = 'auto' | 'light' | 'dark'
const KEY = 'shefa.theme'

export function readTheme(): Theme {
  try {
    const v = localStorage.getItem(KEY)
    if (v === 'light' || v === 'dark') return v
  } catch {
    /* storage blocked */
  }
  return 'auto'
}

/** Light, dark, or follow the device. The tokens read :root[data-theme]; "auto" removes it. */
export function applyTheme(theme: Theme) {
  const root = document.documentElement
  /* one repaint for the whole page: without this, controls with a colour transition fade on their own clock */
  root.classList.add('theme-changing')
  if (theme === 'auto') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
  requestAnimationFrame(() => requestAnimationFrame(() => root.classList.remove('theme-changing')))
  try {
    if (theme === 'auto') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, theme)
  } catch {
    /* storage blocked: the choice lasts for this page only */
  }
}

/** A three-way switch. Labels come from the page's own dictionary (staff app, patient, demo). */
export function ThemeSwitch({ labels }: { labels: { group: string; auto: string; light: string; dark: string } }) {
  const [theme, setTheme] = useState<Theme>(readTheme)
  const pill = useSegPill<HTMLDivElement>(theme)
  const options: [Theme, string, typeof Sun][] = [
    ['auto', labels.auto, Monitor],
    ['light', labels.light, Sun],
    ['dark', labels.dark, Moon],
  ]
  return (
    <div className="seg theme-switch" role="group" aria-label={labels.group} ref={pill}>
      <span className="seg-pill" aria-hidden="true" />
      {options.map(([value, label, Icon]) => (
        <button
          key={value}
          type="button"
          aria-pressed={theme === value}
          title={label}
          onClick={() => {
            setTheme(value)
            applyTheme(value)
          }}
        >
          <Icon size={16} strokeWidth={2} aria-hidden="true" />
          <span className="visually-hidden">{label}</span>
        </button>
      ))}
    </div>
  )
}

/** Subscribe to a media query; for drawing code that cannot read CSS (canvas). */
function mediaStore(query: string) {
  return {
    subscribe(change: () => void) {
      const list = window.matchMedia(query)
      list.addEventListener('change', change)
      return () => list.removeEventListener('change', change)
    },
    read: () => window.matchMedia(query).matches,
  }
}
const darkDevice = mediaStore('(prefers-color-scheme: dark)')
const calmDevice = mediaStore('(prefers-reduced-motion: reduce)')

function subscribeRootTheme(change: () => void) {
  const watch = new MutationObserver(change)
  watch.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  const stopDevice = darkDevice.subscribe(change)
  return () => {
    watch.disconnect()
    stopDevice()
  }
}

/** The theme actually on screen, light or dark, after the switch and the device are both applied. */
export function useShownTheme(): 'light' | 'dark' {
  return useSyncExternalStore(subscribeRootTheme, () => {
    const forced = document.documentElement.getAttribute('data-theme')
    if (forced === 'light' || forced === 'dark') return forced
    return darkDevice.read() ? 'dark' : 'light'
  })
}

/** True when the viewer asked their device for less motion. */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(calmDevice.subscribe, calmDevice.read)
}
