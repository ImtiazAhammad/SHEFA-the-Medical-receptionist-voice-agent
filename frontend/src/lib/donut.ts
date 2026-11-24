// Donut chart from transitions.dev ("donut chart", recipe 35), typed: ring sectors with even gaps
// and rounded corners that morph to new values. Angles run clockwise from the top. The tween reads
// --chart-morph-dur and --chart-morph-ease, and is skipped with reduced motion.
const root = document.documentElement
const token = (name: string) => getComputedStyle(root).getPropertyValue(name).trim()

// The CSS cubic-bezier, for the JS tween.
function bezier(x1: number, y1: number, x2: number, y2: number) {
  return (t: number) => {
    let lo = 0,
      hi = 1,
      u = t
    for (let i = 0; i < 24; i++) {
      u = (lo + hi) / 2
      const x = 3 * u * (1 - u) * (1 - u) * x1 + 3 * u * u * (1 - u) * x2 + u * u * u
      if (x < t) lo = u
      else hi = u
    }
    return 3 * u * (1 - u) * (1 - u) * y1 + 3 * u * u * (1 - u) * y2 + u * u * u
  }
}
function easeOf(value: string) {
  const m = /cubic-bezier\(([^)]+)\)/.exec(value)
  if (!m) return (t: number) => t
  const [a, b, c, d] = m[1].split(',').map(parseFloat)
  return bezier(a, b, c, d)
}

// One ring sector from angle a0 to a1, inset by the corner radius (the round-joined stroke adds
// it back) and by half the gap measured straight across, so both gap edges stay parallel.
function ringPath(cx: number, cy: number, ro: number, ri: number, a0: number, a1: number, gap: number, cr: number) {
  const Ro = ro - cr,
    Ri = ri + cr,
    h = gap / 2 + cr
  if (Ro <= Ri) return ''
  const dO = Math.asin(Math.min(1, h / Ro)),
    dI = Math.asin(Math.min(1, h / Ri))
  const o0 = a0 + dO,
    o1 = a1 - dO,
    i0 = a0 + dI,
    i1 = a1 - dI
  if (i1 - i0 <= 0 || o1 - o0 <= 0) return '' // too small to draw
  const pt = (r: number, a: number) => (cx + r * Math.sin(a)).toFixed(3) + ' ' + (cy - r * Math.cos(a)).toFixed(3)
  const lo = o1 - o0 > Math.PI ? 1 : 0,
    li = i1 - i0 > Math.PI ? 1 : 0
  return (
    'M' + pt(Ro, o0) + 'A' + Ro + ' ' + Ro + ' 0 ' + lo + ' 1 ' + pt(Ro, o1) +
    'L' + pt(Ri, i1) + 'A' + Ri + ' ' + Ri + ' 0 ' + li + ' 0 ' + pt(Ri, i0) + 'Z'
  )
}

export function donut(el: HTMLElement, colors: string[]) {
  const svg = el.querySelector('svg') as SVGSVGElement
  const vb = svg.viewBox.baseVal,
    cx = vb.width / 2,
    cy = vb.height / 2
  const ro = Math.min(cx, cy),
    ri = ro - (parseFloat(el.dataset.thickness ?? '') || 14)
  const segs = colors.map((color) => {
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path')
    p.setAttribute('class', 't-donut-seg')
    p.style.fill = color
    p.style.stroke = color
    svg.appendChild(p)
    return p
  })
  let current: number[] | null = null,
    raf = 0
  function draw(values: number[]) {
    const total = values.reduce((a, b) => a + b, 0) || 1
    const gap = parseFloat(token('--chart-gap')) || 0
    const cr = parseFloat(token('--chart-corner')) || 0
    let a = 0
    values.forEach((v, k) => {
      const span = (v / total) * Math.PI * 2
      segs[k].setAttribute('d', ringPath(cx, cy, ro, ri, a, a + span, gap, cr))
      segs[k].style.strokeWidth = String(2 * cr)
      a += span
    })
  }
  return function set(values: number[]) {
    cancelAnimationFrame(raf)
    const from = current,
      to = values.slice()
    current = to
    const dur = parseFloat(token('--chart-morph-dur')) || 0
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches
    if (!from || !dur || reduce) {
      draw(to)
      return
    }
    const ease = easeOf(token('--chart-morph-ease'))
    const t0 = performance.now()
    ;(function step(now: number) {
      const t = Math.min(1, (now - t0) / dur),
        e = ease(t)
      draw(from.map((f, k) => f + (to[k] - f) * e))
      if (t < 1) raf = requestAnimationFrame(step)
    })(t0)
  }
}
