import { useCallback, useEffect, useState } from 'react'
import api, { errorMessage } from '../api/client'

/**
 * Load data from the API and keep it in state.
 *
 *   const { data, loading, error, reload, setData } = useApi('/companies/', { status: 'active' })
 *
 * It fetches again whenever the url or params change, or when reload() is called.
 * Pass url = null to skip loading.
 */
export default function useApi(url, params) {
  const [state, setState] = useState({ data: null, loading: true, error: '' })
  const [version, setVersion] = useState(0)

  // Objects are new on every render, so compare params by their text form
  const paramsKey = JSON.stringify(params ?? {})

  useEffect(() => {
    if (!url) return undefined
    let cancelled = false // ignore answers that arrive after the page moved on

    api
      .get(url, { params: JSON.parse(paramsKey) })
      .then(({ data }) => {
        if (!cancelled) setState({ data, loading: false, error: '' })
      })
      .catch((err) => {
        if (!cancelled) setState((prev) => ({ ...prev, loading: false, error: errorMessage(err) }))
      })

    return () => {
      cancelled = true
    }
  }, [url, paramsKey, version])

  const reload = useCallback(() => setVersion((value) => value + 1), [])

  // Change the loaded data locally (e.g. after a save) without refetching
  const setData = useCallback(
    (updater) =>
      setState((prev) => ({
        ...prev,
        data: typeof updater === 'function' ? updater(prev.data) : updater,
      })),
    [],
  )

  return { ...state, reload, setData }
}
