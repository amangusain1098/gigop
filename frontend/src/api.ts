import type { BootstrapPayload, DashboardEvent } from './types'

interface SessionCountPayload {
  active_sessions: number
  total_sessions: number
}

export interface TrainingDashboardPayload {
  stats?: Record<string, number>
  top_words?: Array<Record<string, unknown>>
  recent_activity?: Array<Record<string, unknown>>
  schedule?: Record<string, unknown>
  test_results?: Record<string, unknown>
}

export interface TrainingPredictionPayload {
  predictions?: Array<Record<string, unknown> | string>
}

function buildHeaders(body?: BodyInit | null, csrfToken?: string) {
  const headers: Record<string, string> = {
  }
  if (!(body instanceof FormData)) {
    headers['Content-Type'] = 'application/json'
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
      ...buildHeaders(options.body ?? null, csrfToken),
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

export function fetchAssistantSessionsCount() {
  return fetchJson<SessionCountPayload>('/api/assistant/sessions/count', { method: 'GET' })
}

export function fetchTrainingDashboard() {
  return fetchJson<TrainingDashboardPayload>('/api/copilot/training-dashboard', { method: 'GET' })
}

export function fetchTrainingPredictions(query: string, topN = 8) {
  const params = new URLSearchParams({ q: query, top_n: String(topN) })
  return fetchJson<TrainingPredictionPayload>(`/api/copilot/training-dashboard/predict?${params.toString()}`, { method: 'GET' })
}

export function runTrainingCycle(csrfToken: string) {
  return fetchJson<Record<string, unknown>>('/api/copilot/training-dashboard/train', { method: 'POST', body: JSON.stringify({}) }, csrfToken)
}

export function runTrainingDashboardTests(csrfToken: string) {
  return fetchJson<Record<string, unknown>>('/api/copilot/training-dashboard/run-tests', { method: 'POST', body: JSON.stringify({}) }, csrfToken)
}

export interface TrainingIngestPayload {
  content: string
  source_type?: string
  source?: string
  message_id?: string
  context?: string
}

export function ingestTrainingText(payload: TrainingIngestPayload, csrfToken: string) {
  return fetchJson<Record<string, unknown>>('/api/copilot/training-dashboard/ingest', { method: 'POST', body: JSON.stringify(payload) }, csrfToken)
}

export function updateTrainingSchedule(payload: Record<string, unknown>, csrfToken: string) {
  return fetchJson<Record<string, unknown>>('/api/copilot/training-dashboard/schedule', { method: 'PUT', body: JSON.stringify(payload) }, csrfToken)
}

export interface AssistantStreamHandlers {
  onMeta?: (payload: Record<string, any>) => void
  onChunk?: (chunk: string) => void
  onDone?: (payload: Record<string, any>) => void
  onError?: (message: string) => void
  onSuggestions?: (suggestions: string[]) => void
}

export async function streamAssistantReply(
  url: string,
  payload: Record<string, unknown>,
  handlers: AssistantStreamHandlers,
  csrfToken?: string,
) {
  const response = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: {
      ...buildHeaders(JSON.stringify(payload), csrfToken),
      Accept: 'text/event-stream',
    },
    body: JSON.stringify(payload),
  })

  if (response.status === 401) {
    window.location.href = '/login'
    throw new Error('Authentication required.')
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const contentType = response.headers.get('content-type') ?? ''
      if (contentType.includes('application/json')) {
        const body = await response.json()
        detail = body.detail ?? JSON.stringify(body)
      } else {
        detail = await response.text()
      }
    } catch {
      detail = await response.text()
    }
    throw new Error(detail || `Request failed with status ${response.status}`)
  }

  if (!response.body) {
    throw new Error('Streaming is not available in this browser.')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  const processEventBlock = (block: string) => {
    const lines = block.split('\n')
    let eventName = 'message'
    const dataLines: string[] = []

    for (const line of lines) {
      if (line.startsWith('event:')) {
        eventName = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trim())
      }
    }

    if (!dataLines.length) return

    let payload: any = dataLines.join('\n')
    try {
      payload = JSON.parse(payload)
    } catch {
      payload = { text: payload }
    }

    if (eventName === 'meta') {
      handlers.onMeta?.(payload)
    } else if (eventName === 'suggestions') {
      const suggestions = Array.isArray(payload.suggestions)
        ? payload.suggestions.filter((item: unknown): item is string => typeof item === 'string')
        : []
      handlers.onSuggestions?.(suggestions)
    } else if (eventName === 'delta') {
      handlers.onChunk?.(String(payload.text ?? ''))
    } else if (eventName === 'done') {
      handlers.onDone?.(payload)
    } else if (eventName === 'error') {
      handlers.onError?.(String(payload.detail ?? payload.text ?? 'Streaming failed.'))
    } else if (typeof payload.text === 'string' && payload.text.startsWith('[SUGGESTIONS]')) {
      const suggestions = payload.text
        .replace('[SUGGESTIONS]', '')
        .split('|')
        .map((item: string) => item.trim())
        .filter(Boolean)
      handlers.onSuggestions?.(suggestions)
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done })

    let boundaryIndex = buffer.indexOf('\n\n')
    while (boundaryIndex >= 0) {
      const eventBlock = buffer.slice(0, boundaryIndex).trim()
      buffer = buffer.slice(boundaryIndex + 2)
      if (eventBlock) {
        processEventBlock(eventBlock)
      }
      boundaryIndex = buffer.indexOf('\n\n')
    }

    if (done) {
      break
    }
  }
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
