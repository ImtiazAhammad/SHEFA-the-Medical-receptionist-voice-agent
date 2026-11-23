import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from './api'
import { useAuth } from './auth'

export interface Loaded<T> {
  data: T | null
  error: ApiError | null
  loading: boolean
  refreshedAt: number | null
  reload: () => void
}

/** Load once, then (optionally) keep fresh. Stops polling while the tab is hidden.
 * When the inputs change the old data is dropped, so one record never shows another's details;
 * `keep` holds it on screen until the new data lands instead, for views where the same figures
 * simply move (the summary's period switch, whose values cross-blur into the new ones). */
export function useLoad<T>(load: () => Promise<T>, deps: unknown[], pollMs = 0, keep = false): Loaded<T> {
  const { expire } = useAuth()
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshedAt, setRefreshedAt] = useState<number | null>(null)
  const loader = useRef(load)
  loader.current = load

  const run = useCallback(
    async (quiet: boolean) => {
      if (!quiet) setLoading(true)
      try {
        setData(await loader.current())
        setError(null)
        setRefreshedAt(Date.now() / 1000)
      } catch (e) {
        const err = e instanceof ApiError ? e : new ApiError(0, 'network')
        if (err.status === 401) expire()
        setError(err)
      } finally {
        setLoading(false)
      }
    },
    [expire],
  )

  useEffect(() => {
    if (!keep) setData(null)
    void run(false)
    if (!pollMs) return
    const id = setInterval(() => {
      if (!document.hidden) void run(true)
    }, pollMs)
    return () => clearInterval(id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run, pollMs, keep, ...deps])

  return { data, error, loading, refreshedAt, reload: () => void run(false) }
}
