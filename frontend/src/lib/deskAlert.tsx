import { useEffect, useRef, useState } from 'react'
import { api, type Callback } from './api'

// The desk hears when SHEFA needs a person. A hand-over used to appear only in a list somebody had
// to be looking at; in a busy reception that means it is missed. Every staff page polls the open
// call-backs; a new one plays a short chime (on by default, switchable, remembered per browser),
// puts the count in the tab title and shows a banner until it is seen.

const POLL_MS = 10_000
const SOUND_KEY = 'shefa.deskSound'

function chime() {
  try {
    const ctx = new AudioContext()
    const now = ctx.currentTime
    for (const [i, freq] of [880, 660].entries()) {
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.frequency.value = freq
      gain.gain.setValueAtTime(0.0001, now + i * 0.25)
      gain.gain.exponentialRampToValueAtTime(0.3, now + i * 0.25 + 0.02)
      gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.25 + 0.22)
      osc.connect(gain).connect(ctx.destination)
      osc.start(now + i * 0.25)
      osc.stop(now + i * 0.25 + 0.25)
    }
    setTimeout(() => void ctx.close(), 800)
  } catch {
    /* no sound on this browser: the banner and title still show */
  }
}

export function soundOn(): boolean {
  try {
    return localStorage.getItem(SOUND_KEY) !== 'off'
  } catch {
    return true
  }
}

export function setSound(on: boolean) {
  try {
    localStorage.setItem(SOUND_KEY, on ? 'on' : 'off')
  } catch {
    /* a convenience only */
  }
}

/** New call-backs since this page opened (the ones already waiting are not "new"). */
export function useDeskAlert(enabled: boolean) {
  const seen = useRef<Set<number> | null>(null)
  const [fresh, setFresh] = useState<Callback[]>([])
  const [open, setOpen] = useState(0)
  const baseTitle = useRef(document.title)

  useEffect(() => {
    if (!enabled) return
    let stop = false
    async function tick() {
      try {
        const rows = await api<Callback[]>('/api/v1/callbacks')
        if (stop) return
        setOpen(rows.length)
        if (seen.current === null) {
          seen.current = new Set(rows.map((r) => r.id))
          return
        }
        const added = rows.filter((r) => !seen.current!.has(r.id))
        if (added.length) {
          added.forEach((r) => seen.current!.add(r.id))
          setFresh((f) => [...added, ...f].slice(0, 5))
          if (soundOn()) chime()
        }
      } catch {
        /* offline or signed out: try again next tick */
      }
    }
    void tick()
    const timer = setInterval(() => void tick(), POLL_MS)
    return () => {
      stop = true
      clearInterval(timer)
    }
  }, [enabled])

  useEffect(() => {
    document.title = open ? `(${open}) ${baseTitle.current}` : baseTitle.current
  }, [open])

  return { fresh, open, dismiss: () => setFresh([]) }
}
