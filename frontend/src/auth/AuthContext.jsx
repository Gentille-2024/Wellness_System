import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import api, { setActingCompany, tokens } from '../api/client'

const ACTING_KEY = 'wms_acting_company'

function readChosen() {
  try {
    return localStorage.getItem(ACTING_KEY)
  } catch {
    return null
  }
}

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  // The logged-in user (the response of /api/me/), or null
  const [user, setUser] = useState(null)
  // True while we check a saved token when the page loads
  const [loading, setLoading] = useState(() => Boolean(tokens.access))
  // The company chosen for the company pages by someone not linked to one
  const [chosenCompanyId, setChosenCompanyId] = useState(readChosen)

  const loadMe = useCallback(async () => {
    const { data } = await api.get('/me/')
    // Keep the same object when nothing changed, so pages don't re-render for nothing
    setUser((prev) => (prev && JSON.stringify(prev) === JSON.stringify(data) ? prev : data))
    return data
  }, [])

  // Permissions are switched on and off by the super admin while people are
  // signed in: read them again when the tab comes back into view and every
  // 15 seconds, so menus and pages follow the role without signing out.
  const signedIn = Boolean(user)
  useEffect(() => {
    if (!signedIn) return undefined
    const refresh = () => {
      if (document.visibilityState === 'visible' && tokens.access) loadMe().catch(() => {})
    }
    window.addEventListener('focus', refresh)
    document.addEventListener('visibilitychange', refresh)
    const timer = window.setInterval(refresh, 15000)
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

  // Any role may have company permissions. Someone not linked to a company
  // (e.g. HR) works on the company pages of the company they choose: for the
  // pages, `user.company` is that company and `user.acting_company` is true.
  const effectiveUser = useMemo(() => {
    const choices = user?.company_choices ?? []
    if (!user || user.company || choices.length === 0) {
      setActingCompany(null)
      return user
    }
    const company = choices.find((c) => String(c.id) === String(chosenCompanyId)) ?? choices[0]
    setActingCompany(company.id) // before any page sends its first request
    return { ...user, company, acting_company: true }
  }, [user, chosenCompanyId])

  const chooseCompany = useCallback((id) => {
    try {
      localStorage.setItem(ACTING_KEY, String(id))
    } catch {
      // private window: the choice lasts until the page is reloaded
    }
    setChosenCompanyId(String(id))
  }, [])

  return (
    <AuthContext.Provider value={{ user: effectiveUser, loading, login, logout, reloadUser: loadMe, chooseCompany }}>
      {children}
    </AuthContext.Provider>
  )
}

// Any component can call useAuth() to get { user, login, logout, ... }
// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  return useContext(AuthContext)
}