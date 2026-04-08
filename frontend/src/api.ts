import type { BootstrapPayload, DashboardEvent } from './types'

function buildHeaders(csrfToken?: string) {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (csrfToken) {
    headers['X-CSRF-Token'] = csrfToken
  }
  return headers
}

export async function fetchJson<T>(url: string, options: RequestInit = {}, csrfToken?: string): Promise<T> {
  const response = await fetch(url, {
    credentials: 'same-origin',
    ...options,
    headers: {
      ...buildHeaders(csrfToken),
      ...(options.headers ?? {}),
    },
  })

  if (response.status === 401) {
    window.location.href = '/login'
    throw new Error('Authentication required.')
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const payload = await response.json()
      detail = payload.detail ?? JSON.stringify(payload)
    } catch {
      detail = await response.text()
    }
    throw new Error(detail || `Request failed with status ${response.status}`)
  }

  return response.json() as Promise<T>
}

export function loadBootstrap() {
  return fetchJson<BootstrapPayload>('/api/v2/bootstrap', { method: 'GET' })
}

export function createDashboardSocket(onEvent: (event: DashboardEvent) => void) {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const socket = new WebSocket(`${protocol}://${window.location.host}/ws/dashboard`)
  socket.onmessage = (message) => {
    try {
      onEvent(JSON.parse(message.data) as DashboardEvent)
    } catch {
      return
    }
  }
  return socket
}
