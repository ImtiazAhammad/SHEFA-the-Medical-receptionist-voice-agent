import { useLayoutEffect, useRef, useState, type CSSProperties } from 'react'

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
