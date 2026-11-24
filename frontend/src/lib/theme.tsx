import { useRef, useState, useSyncExternalStore } from 'react'
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
  const tip = useRef<HTMLSpanElement>(null)
  const options: [Theme, string, typeof Sun][] = [
    ['auto', labels.auto, Monitor],
    ['light', labels.light, Sun],
    ['dark', labels.dark, Moon],
  ]

  // One tooltip shared by the three icons (transitions.dev "tooltip"): it appears after a short
  // delay, then travels between icons while it stays open, and leaves at once. Only for a mouse
  // or keyboard focus, never a touch tap (it would stay stuck on a phone). It repeats the
  // button's own hidden label, so screen readers are not told twice.
  function place(trigger: HTMLElement) {
    const el = tip.current
    const group = pill.current
    if (!el || !group) return
    const text = el.firstElementChild as HTMLElement
    const showing = el.dataset.show === 'true'
    text.textContent = trigger.dataset.tooltip ?? ''
    const cs = getComputedStyle(el)
    const width = Math.ceil(text.scrollWidth + parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight))
    const g = group.getBoundingClientRect()
    const r = trigger.getBoundingClientRect()
    const x = r.left - g.left + r.width / 2 - width / 2
    el.classList.toggle('t-tt-below', r.top < 96) // a header bar at the top: open downward
    if (!showing) {
      el.style.transition = 'none'
      el.style.width = `${width}px`
      el.style.setProperty('--tt-x', `${x}px`)
      void el.offsetWidth
      el.style.transition = ''
    } else {
      el.style.width = `${width}px`
      el.style.setProperty('--tt-x', `${x}px`)
    }
    el.dataset.show = 'true'
  }
  function hide() {
    if (tip.current) tip.current.dataset.show = 'false'
  }

  return (
    <div
      className="seg theme-switch t-tt-group"
      role="group"
      aria-label={labels.group}
      ref={pill}
      onPointerLeave={hide}
      onKeyDown={(e) => e.key === 'Escape' && hide()}
    >
      <span className="seg-pill" aria-hidden="true" />
      {options.map(([value, label, Icon]) => (
        <button
          key={value}
          type="button"
          aria-pressed={theme === value}
          data-tooltip={label}
          onPointerEnter={(e) => e.pointerType === 'mouse' && place(e.currentTarget)}
          onFocus={(e) => e.currentTarget.matches(':focus-visible') && place(e.currentTarget)}
          onBlur={hide}
          onClick={() => {
            setTheme(value)
            applyTheme(value)
          }}
        >
          <Icon size={16} strokeWidth={2} aria-hidden="true" />
          <span className="visually-hidden">{label}</span>
        </button>
      ))}
      <span className="t-tt" ref={tip} aria-hidden="true" data-show="false">
        <span className="t-tt-text" />
      </span>
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
