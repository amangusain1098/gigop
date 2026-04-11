import { useCallback, useEffect, useState } from 'react'

import { loadBootstrap } from '../api'
import type { BootstrapPayload } from '../types'

interface UseBootstrapResult {
  data: BootstrapPayload | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}

export function useBootstrap(): UseBootstrapResult {
  const [data, setData] = useState<BootstrapPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    try {
      const payload = await loadBootstrap()
      setData(payload)
      setError(null)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Unable to load dashboard data.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let active = true

    async function runRefresh() {
      try {
        const payload = await loadBootstrap()
        if (!active) return
        setData(payload)
        setError(null)
      } catch (reason) {
        if (!active) return
        setError(reason instanceof Error ? reason.message : 'Unable to load dashboard data.')
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    void runRefresh()
    const timer = window.setInterval(() => {
      void runRefresh()
    }, 30000)

    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [])

  return { data, loading, error, refresh }
}
