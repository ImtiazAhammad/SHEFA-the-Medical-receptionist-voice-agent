import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, ApiError, type Me } from './api'

interface Auth {
  me: Me | null // null while the first check runs
  can: (permission: string) => boolean
  signIn: (credentials: { token: string } | { username: string; password: string }) => Promise<boolean>
  signOut: () => Promise<void>
  expire: () => void
}

const Ctx = createContext<Auth | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)

  useEffect(() => {
    api<Me>('/api/v1/me')
      .then(setMe)
      .catch(() => setMe({ signed_in: false })) // a 401 is the answer "signed out"
  }, [])

  const signIn = useCallback(async (credentials: object) => {
    try {
      await api('/api/v1/login', { method: 'POST', body: JSON.stringify(credentials) })
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) return false
      throw error
    }
    setMe(await api<Me>('/api/v1/me'))
    return true
  }, [])

  const signOut = useCallback(async () => {
    await api('/api/v1/logout', { method: 'POST' }).catch(() => undefined)
    setMe({ signed_in: false })
  }, [])

  const expire = useCallback(() => setMe({ signed_in: false }), [])
  const can = useCallback((p: string) => !!me?.permissions?.includes(p), [me])

  return <Ctx.Provider value={{ me, can, signIn, signOut, expire }}>{children}</Ctx.Provider>
}

export function useAuth(): Auth {
  const value = useContext(Ctx)
  if (!value) throw new Error('useAuth outside AuthProvider')
  return value
}
