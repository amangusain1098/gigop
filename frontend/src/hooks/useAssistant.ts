import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { fetchJson } from '../api'
import type { AssistantHistoryMessage, CopilotTrainingStatus } from '../types'

interface UseAssistantResult {
  messages: AssistantHistoryMessage[]
  busy: boolean
  waitingForFirstChunk: boolean
  sendMessage: (text: string) => Promise<void>
  clearHistory: () => void
  initialized: boolean
  sessionId: string | null
}

function buildSessionId() {
  return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

function getAssistantSessionId(storageKey: string) {
  try {
    const stored = sessionStorage.getItem(storageKey)
    if (stored && stored.length > 4) return stored
  } catch {
    // ignore storage failures and fall back to ephemeral ids
  }

  const id = buildSessionId()

  try {
    sessionStorage.setItem(storageKey, id)
  } catch {
    // ignore storage failures and keep the in-memory id
  }

  return id
}

function mapAssistantHistory(items: Array<Record<string, unknown>>): AssistantHistoryMessage[] {
  return [...items]
    .sort((left, right) => {
      const leftTime = Date.parse(String(left.created_at ?? ''))
      const rightTime = Date.parse(String(right.created_at ?? ''))
      if (!Number.isNaN(leftTime) && !Number.isNaN(rightTime) && leftTime !== rightTime) {
        return leftTime - rightTime
      }
      return Number(left.id ?? 0) - Number(right.id ?? 0)
    })
    .map((item) => ({
      id: typeof item.id === 'number' ? item.id : Number(item.id ?? 0) || undefined,
      role: (item.role === 'user' ? 'user' : 'assistant') as 'user' | 'assistant',
      text: String(item.content ?? '').trim(),
      suggestions: item.role === 'assistant' ? ((item.metadata as { suggestions?: string[] } | undefined)?.suggestions ?? []) : undefined,
      feedbackRating: item.role === 'assistant'
        ? (Number((item.metadata as { feedback?: { rating?: number } } | undefined)?.feedback?.rating ?? 0) || undefined)
        : undefined,
      createdAt: String(item.created_at ?? '').trim() || undefined,
    }))
    .filter((item) => item.text)
}

export function useAssistant(
  csrfToken: string,
  refreshCsrf: () => Promise<string>,
): UseAssistantResult {
  const sessionStorageKey = 'gigoptimizer-assistant-session-id'
  const sessionIdRef = useRef<string | null>(getAssistantSessionId(sessionStorageKey))
  const [messages, setMessages] = useState<AssistantHistoryMessage[]>([])
  const [busy, setBusy] = useState(false)
  const [waitingForFirstChunk, setWaitingForFirstChunk] = useState(false)
  const [initialized, setInitialized] = useState(false)

  useEffect(() => {
    setInitialized(true)
  }, [])

  const withCsrfRetry = useCallback(async <T,>(operation: (token: string) => Promise<T>) => {
    try {
      return await operation(csrfToken)
    } catch (reason) {
      const detail = reason instanceof Error ? reason.message : 'Request failed.'
      if (!/csrf/i.test(detail)) {
        throw reason
      }
      const nextToken = await refreshCsrf()
      return operation(nextToken)
    }
  }, [csrfToken, refreshCsrf])

  const sendMessageFallback = useCallback(async (question: string) => {
    setWaitingForFirstChunk(true)

    const response = await withCsrfRetry((token) =>
      fetchJson<{
        assistant: { reply: string; suggestions?: string[] }
        assistant_history?: Array<Record<string, unknown>>
        copilot_training?: CopilotTrainingStatus
      }>(
        '/api/assistant/chat',
        {
          method: 'POST',
          body: JSON.stringify({
            message: question,
            session_id: sessionIdRef.current,
          }),
        },
        token,
      ),
    )

    const nextMessages = mapAssistantHistory(response.assistant_history ?? [])
    if (nextMessages.length) {
      setMessages(nextMessages)
      return
    }

    setMessages((current) => [
      ...current,
      {
        role: 'assistant',
        text: response.assistant.reply,
        suggestions: response.assistant.suggestions ?? [],
        createdAt: new Date().toISOString(),
      },
    ])
  }, [withCsrfRetry])

  const sendMessage = useCallback(async (text: string) => {
    const question = text.trim()
    if (!question) return

    setBusy(true)
    setWaitingForFirstChunk(true)
    setMessages((current) => [...current, { role: 'user', text: question, createdAt: new Date().toISOString() }])

    try {
      if (typeof ReadableStream === 'undefined') {
        await sendMessageFallback(question)
        return
      }

      await withCsrfRetry(async (token) => {
        const response = await fetch('/api/assistant/stream', {
          method: 'POST',
          credentials: 'same-origin',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': token,
          },
          body: JSON.stringify({
            message: question,
            session_id: sessionIdRef.current,
          }),
        })

        if (response.status === 401) {
          window.location.href = '/login'
          throw new Error('Authentication required.')
        }

        if (!response.ok) {
          let detail = response.statusText
          try {
            const payload = await response.json()
            detail = payload.error ?? payload.detail ?? payload.message ?? JSON.stringify(payload)
          } catch {
            detail = await response.text()
          }
          throw new Error(detail || `Request failed with status ${response.status}`)
        }

        if (!response.body) {
          throw new Error('Streaming response body is unavailable.')
        }

        const reader = response.body.getReader()
        const decoder = new TextDecoder()
        let buffer = ''
        let reply = ''
        let createdAssistantBubble = false

        while (true) {
          const { value, done } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const chunks = buffer.split('\n\n')
          buffer = chunks.pop() ?? ''

          for (const chunk of chunks) {
            const line = chunk.trim()
            if (!line.startsWith('data:')) continue

            const tokenValue = line.slice(5).trim()
            if (tokenValue === '[DONE]') {
              setWaitingForFirstChunk(false)
              continue
            }

            if (tokenValue.startsWith('[SUGGESTIONS]')) {
              try {
                const suggestions: string[] = JSON.parse(tokenValue.slice(13))
                setMessages((current) => {
                  const next = [...current]
                  const lastIndex = next.length - 1
                  const lastEntry = next[lastIndex]
                  if (lastEntry && lastEntry.role === 'assistant') {
                    next[lastIndex] = { ...lastEntry, suggestions }
                  }
                  return next
                })
              } catch { /* ignore */ }
              continue
            }

            if (!createdAssistantBubble) {
              createdAssistantBubble = true
              setWaitingForFirstChunk(false)
              setMessages((current) => [
                ...current,
                { role: 'assistant', text: tokenValue, createdAt: new Date().toISOString() },
              ])
              reply += tokenValue
              continue
            }

            reply += tokenValue
            setMessages((current) => {
              const next = [...current]
              const lastIndex = next.length - 1
              const lastEntry = next[lastIndex]
              if (!lastEntry || lastEntry.role !== 'assistant') {
                next.push({ role: 'assistant', text: reply, createdAt: new Date().toISOString() })
                return next
              }

              next[lastIndex] = { ...lastEntry, text: reply }
              return next
            })
          }
        }
      })
    } catch {
      await sendMessageFallback(question)
    } finally {
      setBusy(false)
      setWaitingForFirstChunk(false)
    }
  }, [sendMessageFallback, withCsrfRetry])

  const clearHistory = useCallback(() => {
    setMessages([])
    const nextSessionId = buildSessionId()
    sessionIdRef.current = nextSessionId
    try {
      sessionStorage.setItem(sessionStorageKey, nextSessionId)
    } catch {
      // ignore storage failures and keep in-memory value
    }
  }, [])

  return useMemo(() => ({
    messages,
    busy,
    waitingForFirstChunk,
    sendMessage,
    clearHistory,
    initialized,
    sessionId: sessionIdRef.current,
  }), [busy, clearHistory, initialized, messages, sendMessage, waitingForFirstChunk])
}
