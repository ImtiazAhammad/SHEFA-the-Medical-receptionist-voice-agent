import { useId, useLayoutEffect, useRef, useState, type CSSProperties, type InputHTMLAttributes, type ReactNode } from 'react'

// the text-swap-soft timings live in CSS (styles.css); read them so the cleanup matches
const cssMs = (name: string) => parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name)) || 0

/**
 * The sliding pill under a segmented switch (language, theme, report period). Timing from
 * transitions.dev's "tabs sliding": 250ms on the shared ease-out. The pill is placed from the
 * pressed button's box, re-measured when the switch resizes and once the web fonts land (a font
 * swap changes button widths). It only slides after the first placement, so it never flies in
 * from the left edge on mount. The buttons keep aria-pressed; the pill is decoration.
 */
export function useSegPill<T extends HTMLElement>(selected: unknown) {
  const ref = useRef<T>(null)
  useLayoutEffect(() => {
    const seg = ref.current
    if (!seg) return
    const place = () => {
      const pill = seg.querySelector<HTMLElement>(':scope > .seg-pill')
      const on = seg.querySelector<HTMLElement>(':scope > button[aria-pressed="true"]')
      if (!pill) return
      if (!on) {
        pill.style.opacity = '0'
        return
      }
      pill.style.opacity = ''
      pill.style.width = `${on.offsetWidth}px`
      pill.style.transform = `translateX(${on.offsetLeft}px)`
    }
    place()
    // the first placement is instant; slides start from the next frame
    const frame = requestAnimationFrame(() => seg.setAttribute('data-ready', ''))
    const resize = new ResizeObserver(place)
    resize.observe(seg)
    let live = true
    void document.fonts?.ready.then(() => live && place())
    return () => {
      live = false
      cancelAnimationFrame(frame)
      resize.disconnect()
    }
  }, [selected])
  return ref
}

/**
 * A count that updates while the page is open (callers waiting, calls in progress). When it
 * changes, the new figure rolls in from the direction of change (up when it grows) with a hint
 * of blur: transitions.dev's "number subtle change", trimmed to 300ms. Never on first render,
 * never when a poll returns the same figure.
 */
export function LiveCount({ value, className }: { value: number; className?: string }) {
  // the direction is held for as long as the figure stands, so an unrelated re-render does not
  // strip the class mid-roll; the keyed span only replays it when the figure changes again
  const [shown, setShown] = useState({ value, dir: 0 })
  if (shown.value !== value) setShown({ value, dir: value > shown.value ? 1 : -1 })
  const dir = shown.value === value ? shown.dir : value > shown.value ? 1 : -1
  return (
    <span className={className}>
      <span key={value} className={dir ? 'count-roll' : undefined} style={dir ? ({ '--dir': dir } as CSSProperties) : undefined}>
        {value}
      </span>
    </span>
  )
}

/**
 * A value that, when it changes in place (a summary figure after the period switch), cross-blurs
 * from the old text to the new one in the same spot while its width eases: transitions.dev's
 * "text swap soft". React never renders the span's children; the swap is done on the DOM so
 * the two texts can share one cell for the moment of the change. The first render is instant.
 */
export function SoftText({ text, className }: { text: string; className?: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  useLayoutEffect(() => {
    const el = ref.current as (HTMLSpanElement & { softTimer?: number }) | null
    if (!el) return
    const prev = el.dataset.text
    if (prev === undefined) {
      el.dataset.text = text
      el.textContent = text
      return
    }
    if (prev === text) return
    el.dataset.text = text
    window.clearTimeout(el.softTimer)
    const out = document.createElement('span')
    out.className = 't-text-soft-old'
    out.setAttribute('aria-hidden', 'true')
    out.textContent = prev
    const inn = document.createElement('span')
    inn.className = 't-text-soft-new'
    inn.textContent = text
    const w0 = el.getBoundingClientRect().width
    el.classList.remove('is-swapping')
    el.replaceChildren(out, inn)
    const w1 = inn.getBoundingClientRect().width
    el.style.width = `${w0}px`
    void el.offsetWidth // reflow, so every transition runs
    el.classList.add('is-swapping')
    el.style.width = `${w1}px`
    el.softTimer = window.setTimeout(
      () => {
        el.classList.remove('is-swapping')
        el.style.removeProperty('width')
        el.textContent = text
      },
      Math.max(cssMs('--text-soft-dur'), cssMs('--text-soft-resize-dur')) + 40,
    )
  }, [text])
  return <span ref={ref} className={`t-text-soft${className ? ` ${className}` : ''}`} />
}

// Bangla letters are clusters (a consonant, its vowel sign, a conjunct): split by grapheme so a
// shared start or end never cuts one in half.
const graphemes = (s: string): string[] => {
  const Seg = (Intl as unknown as { Segmenter?: new (l?: string, o?: { granularity: string }) => { segment(s: string): Iterable<{ segment: string }> } }).Segmenter
  return Seg ? Array.from(new Seg(undefined, { granularity: 'grapheme' }).segment(s), (x) => x.segment) : Array.from(s)
}

/**
 * A button label that changes in place ("Copy" to "Copied", "Book" to "Booking…"). When the two
 * labels share letters at the start or end, only the part that differs cross-blurs while its
 * width eases (transitions.dev "text morph"); when they share nothing, the label exits up and the
 * new one rises in (transitions.dev "text states swap"). First render is instant; React never
 * renders the children, the swap is done on the DOM.
 */
export function MorphText({ text }: { text: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  useLayoutEffect(() => {
    const el = ref.current as (HTMLSpanElement & { morphTimer?: number }) | null
    if (!el) return
    const prev = el.dataset.text
    if (prev === undefined) {
      el.dataset.text = text
      el.textContent = text
      return
    }
    if (prev === text) return
    el.dataset.text = text
    window.clearTimeout(el.morphTimer)
    el.classList.remove('t-text-swap', 'is-exit', 'is-enter-start')
    const p = graphemes(prev)
    const n = graphemes(text)
    let a = 0
    while (a < p.length && a < n.length && p[a] === n[a]) a++
    let b = 0
    while (b < p.length - a && b < n.length - a && p[p.length - 1 - b] === n[n.length - 1 - b]) b++
    if (a === 0 && b === 0) {
      // nothing shared: the three-phase text swap
      const dur = cssMs('--text-swap-dur') || 150
      el.textContent = prev
      el.classList.add('t-text-swap', 'is-exit')
      el.morphTimer = window.setTimeout(() => {
        el.textContent = text
        el.classList.remove('is-exit')
        el.classList.add('is-enter-start')
        void el.offsetHeight // reflow, so the entrance transitions
        el.classList.remove('is-enter-start')
      }, dur)
      return
    }
    const swap = document.createElement('span')
    swap.className = 't-morph-swap'
    const out = document.createElement('span')
    out.className = 't-morph-old'
    out.setAttribute('aria-hidden', 'true')
    out.textContent = p.slice(a, p.length - b).join('')
    const inn = document.createElement('span')
    inn.className = 't-morph-new'
    inn.textContent = n.slice(a, n.length - b).join('')
    swap.append(out, inn)
    el.textContent = ''
    el.append(n.slice(0, a).join(''), swap, n.slice(n.length - b).join(''))
    swap.style.width = `${out.getBoundingClientRect().width}px`
    void swap.offsetWidth // reflow, so the width transitions
    swap.classList.add('is-morphing')
    swap.style.width = `${inn.getBoundingClientRect().width}px`
    el.morphTimer = window.setTimeout(
      () => {
        el.textContent = text
      },
      Math.max(cssMs('--text-morph-dur'), cssMs('--text-morph-resize-dur')) + 40,
    )
  }, [text])
  return <span ref={ref} className="t-morph" />
}

/**
 * A real checkbox whose tick draws itself (transitions.dev "checkbox check"). The recipe uses a
 * button with role="checkbox"; this keeps the native input (keyboard, forms, labels, screen
 * readers all as before) and draws the box and tick over it.
 */
export function TickBox(props: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <span className="t-check-box">
      <input type="checkbox" className="t-check" {...props} />
      <svg viewBox="0 0 10.1668 10.1668" aria-hidden="true">
        <path d="M1 5.52L3.92 9.17L9.17 1" />
      </svg>
    </span>
  )
}

/**
 * A disclosure that grows open and shut (transitions.dev "accordion expand": grid rows 0fr to 1fr,
 * the chevron flipping). A real button carries aria-expanded and aria-controls; the closed panel
 * is inert, so it leaves the tab order and the accessibility tree like a closed <details>.
 */
export function Disclosure({ summary, children }: { summary: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const id = useId()
  return (
    <div className="t-acc" data-open={open}>
      <button type="button" className="t-acc-head" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        {summary}
        <AccChevron />
      </button>
      <div className="t-acc-panel" id={id} inert={!open}>
        <div className="t-acc-panel-inner">{children}</div>
      </div>
    </div>
  )
}

export function AccChevron() {
  return (
    <span className="t-acc-chevron" aria-hidden="true">
      <svg viewBox="0 0 16 16" width="16" height="16">
        <path d="M4 6.5L8 10.5L12 6.5" />
      </svg>
    </span>
  )
}
