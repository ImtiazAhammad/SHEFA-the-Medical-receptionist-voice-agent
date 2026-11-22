import { useState } from 'react'
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
  const options: [Theme, string, typeof Sun][] = [
    ['auto', labels.auto, Monitor],
    ['light', labels.light, Sun],
    ['dark', labels.dark, Moon],
  ]
  return (
    <div className="seg theme-switch" role="group" aria-label={labels.group}>
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
