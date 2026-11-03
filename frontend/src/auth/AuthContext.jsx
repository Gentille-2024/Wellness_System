import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import api, { tokens } from '../api/client'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  // The logged-in user (the response of /api/me/), or null
  const [user, setUser] = useState(null)
  // True while we check a saved token when the page loads
  const [loading, setLoading] = useState(() => Boolean(tokens.access))

  const loadMe = useCallback(async () => {
    const { data } = await api.get('/me/')
    // Keep the same object when nothing changed, so pages don't re-render for nothing
    setUser((prev) => (prev && JSON.stringify(prev) === JSON.stringify(data) ? prev : data))
    return data
  }, [])

  // Permissions are switched on and off by the super admin while people are
  // signed in: read them again when the tab comes back into view and every
  // 30 seconds, so menus and pages follow the role without signing out.
  const signedIn = Boolean(user)
  useEffect(() => {
    if (!signedIn) return undefined
    const refresh = () => {
      if (document.visibilityState === 'visible' && tokens.access) loadMe().catch(() => {})
    }
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    const timer = window.setInterval(refresh, 30000)
    return () => {
      window.removeEventListener('focus', refresh)
      document.removeEventListener('visibilitychange', refresh)
      window.clearInterval(timer)
    }
  }, [signedIn, loadMe])

  // On page load/refresh: if we have a saved token, find out who we are
  useEffect(() => {
    if (!tokens.access) return
    api
      .get('/me/')
      .then(({ data }) => setUser(data))
      .catch(() => tokens.clear())
      .finally(() => setLoading(false))
  }, [])

  // The API client fires this event when the session can't be refreshed
  useEffect(() => {
    const onLogout = () => setUser(null)
    window.addEventListener('auth:logout', onLogout)
    return () => window.removeEventListener('auth:logout', onLogout)
  }, [])

  const login = async (username, password) => {
    const { data } = await api.post('/login/', { username, password })
    tokens.save(data.access, data.refresh)
    return loadMe()
  }

  const logout = () => {
    tokens.clear()
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, reloadUser: loadMe }}>
      {children}
    </AuthContext.Provider>
  )
}

// Any component can call useAuth() to get { user, login, logout, ... }
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  return useContext(AuthContext)
}