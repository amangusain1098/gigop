import { useCallback, useEffect, useState } from 'react'

import { loadBootstrap } from '../api'
import type { BootstrapPayload } from '../types'

interface UseCsrfResult {
  csrfToken: string
  refreshCsrf: () => Promise<string>
}

export function useCsrf(data: BootstrapPayload | null): UseCsrfResult {
  const [csrfToken, setCsrfToken] = useState(data?.state.auth.csrf_token ?? '')

  useEffect(() => {
    setCsrfToken(data?.state.auth.csrf_token ?? '')
  }, [data])

  const refreshCsrf = useCallback(async () => {
    const payload = await loadBootstrap()
    const nextToken = payload.state.auth.csrf_token ?? ''
    setCsrfToken(nextToken)
    return nextToken
  }, [])

  return { csrfToken, refreshCsrf }
}
