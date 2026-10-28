import axios from 'axios'

const ACCESS_KEY = 'wms_access'
const REFRESH_KEY = 'wms_refresh'

// Small helper around localStorage so the rest of the app never
// has to remember the key names.
export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS_KEY)
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY)
  },
  save(access, refresh) {
    localStorage.setItem(ACCESS_KEY, access)
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

// Every request made with `api` goes to /api/... (forwarded to Django by Vite)
const api = axios.create({ baseURL: '/api' })

// 1) Before each request: attach the access token
api.interceptors.request.use((config) => {
  const access = tokens.access
  if (access) config.headers.Authorization = `Bearer ${access}`
  return config
})

// 2) After each response: if the token expired (401), get a new one
//    with the refresh token and repeat the original request once.
let refreshPromise = null

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    const isLoginCall = original?.url?.includes('/login/')

    if (
      error.response?.status === 401 &&
      !original._retry &&
      !isLoginCall &&
      tokens.refresh
    ) {
      original._retry = true
      try {
        // If several requests fail at once, they all wait for ONE refresh
        refreshPromise ??= axios
          .post('/api/token/refresh/', { refresh: tokens.refresh })
          .finally(() => {
            refreshPromise = null
          })
        const { data } = await refreshPromise
        tokens.save(data.access)
        original.headers.Authorization = `Bearer ${data.access}`
        return api(original)
      } catch (refreshError) {
        // The refresh token expired too: the user must log in again
        tokens.clear()
        window.dispatchEvent(new Event('auth:logout'))
        return Promise.reject(refreshError)
      }
    }

    // The user's company was deactivated by EUCL: sign out and say why
    if (error.response?.status === 403 && error.response.data?.code === 'company_deactivated') {
      tokens.clear()
      signOutNotice.save(error.response.data.detail)
      window.dispatchEvent(new Event('auth:logout'))
    }

    return Promise.reject(error)
  },
)

// A message for the sign-in page after the app signed the user out
export const signOutNotice = {
  save(message) {
    try {
      sessionStorage.setItem('wms_notice', message)
    } catch {
      // storage blocked: the sign-in page still shows the message when they try again
    }
  },
  read() {
    try {
      return sessionStorage.getItem('wms_notice') ?? ''
    } catch {
      return ''
    }
  },
  clear() {
    try {
      sessionStorage.removeItem('wms_notice')
    } catch {
      // nothing to clear
    }
  },
}

// Turn a DRF error response into a message we can show on screen
export function errorMessage(error) {
  const data = error?.response?.data
  if (!data) return 'Cannot reach the server. Is Django running?'
  if (typeof data === 'string') return 'Server error. Check the Django terminal.'
  if (Array.isArray(data)) return data.join('\n') // e.g. ["Not allowed."]
  if (data.detail) return data.detail

  return Object.entries(data)
    .map(([field, messages]) => {
      const text = Array.isArray(messages) ? messages.join(' ') : String(messages)
      return field === 'non_field_errors' ? text : `${field}: ${text}`
    })
    .join('\n')
}

// Split a DRF error into { fieldName: "message", _general: "message" }
// so forms can show each message under the right input.
export function parseErrors(error) {
  const data = error?.response?.data
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    return { _general: errorMessage(error) }
  }

  const result = {}
  for (const [field, messages] of Object.entries(data)) {
    const text = Array.isArray(messages) ? messages.join(' ') : String(messages)
    const key = field === 'non_field_errors' || field === 'detail' ? '_general' : field
    result[key] = result[key] ? `${result[key]} ${text}` : text
  }
  return result
}

export default api