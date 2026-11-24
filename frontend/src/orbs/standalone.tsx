// SHEFA's orbs for pages that are not React: the voice console (static/console.html) and the
// voice-collection site. One small ES module, built by `npm run build:orbs` into
// static/world/orbs/shefa-orbs.js, that the pages load with a dynamic import() only when an orb is
// first shown. It wraps the same two Libraries.dev components the React app uses:
//   mountOrb(el, { state, size })  a thinking orb (thinking-orbs): listening, composing, connecting…
//   mountRing(el, { size, state, level })  the voice ring (voice-ring) around an assistant's orb;
//                                          level is a getter read every frame, 0..1
// Both return { set(...), destroy() }. Both follow the page's theme on their own (an ancestor's
// data-theme, else the device), and both are decoration: the canvas is hidden from screen readers
// and the page says the state in words.
import { createRoot } from 'react-dom/client'
import { ThinkingOrb, type OrbState } from 'thinking-orbs'
import { VoiceRing } from 'voice-ring'

type RingState = 'idle' | 'listening' | 'speaking' | 'processing'
const calm = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

export function mountOrb(el: HTMLElement, opts: { state?: OrbState; size?: 20 | 64; theme?: 'auto' | 'light' | 'dark' } = {}) {
  const root = createRoot(el)
  let state: OrbState = opts.state ?? 'working'
  const size = opts.size ?? 20
  // theme pins the ink when the orb sits on a solid fill (a violet banner) rather than the page
  const theme = opts.theme ?? 'auto'
  const draw = () => root.render(<ThinkingOrb state={state} size={size} theme={theme} aria-hidden="true" />)
  draw()
  return {
    set(next: OrbState) {
      if (next === state) return
      state = next
      draw()
    },
    destroy() {
      root.unmount()
    },
  }
}

export function mountRing(el: HTMLElement, opts: { size?: number; state?: RingState; level?: () => number; hoverBend?: boolean } = {}) {
  const root = createRoot(el)
  let state: RingState = opts.state ?? 'idle'
  const size = opts.size ?? 220
  const level = opts.level ?? (() => 0)
  // the ring has no motion setting of its own beyond its hover bend; reduced motion pauses it
  // hoverBend: when the ring is itself the button, it bends toward a nearing cursor while it
  // waits (desktop pointers only; the library turns it off with reduced motion)
  const hoverBend = opts.hoverBend ?? false
  const draw = () => root.render(<VoiceRing size={size} state={state} level={level} paused={calm()} hoverBend={hoverBend} />)
  draw()
  return {
    set(next: { state?: RingState }) {
      if (next.state && next.state !== state) {
        state = next.state
        draw()
      }
    },
    destroy() {
      root.unmount()
    },
  }
}
