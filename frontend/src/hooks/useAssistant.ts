import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { fetchJson, streamAssistantReply } from '../api'

interface AssistantHistoryMessage {
  id?: string
  role: 'user' | 'assistant'
  text: string
  suggestions?: string[]
  pending?: boolean
  provider?: string
}

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
      id: String(item.id ?? `${item.role ?? 'assistant'}-${item.created_at ?? Math.random().toString(36).slice(2, 8)}`),
      role: (item.role === 'user' ? 'user' : 'assistant') as 'user' | 'assistant',
      text: String(item.content ?? '').trim(),
      suggestions: item.role === 'assistant' ? (Array.isArray((item.metadata as { suggestions?: unknown } | undefined)?.suggestions)
        ? ((item.metadata as { suggestions?: string[] } | undefined)?.suggestions ?? [])
        : []) : undefined,
      provider: item.role === 'assistant' ? String((item.metadata as { provider?: unknown } | undefined)?.provider ?? '') || undefined : undefined,
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
    const response = await withCsrfRetry((token) =>
      fetchJson<{
        assistant: { reply: string; suggestions?: string[]; provider?: string }
        assistant_history?: Array<Record<string, unknown>>
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
        id: `assistant-${Date.now().toString(36)}`,
        role: 'assistant',
        text: response.assistant.reply,
        suggestions: response.assistant.suggestions ?? [],
        provider: response.assistant.provider,
      },
    ])
  }, [withCsrfRetry])

  const sendMessage = useCallback(async (text: string) => {
    const question = text.trim()
    if (!question) return

    const userMessageId = `user-${Date.now().toString(36)}`
    const assistantMessageId = `assistant-${Date.now().toString(36)}`

    setBusy(true)
    setWaitingForFirstChunk(true)
    setMessages((current) => [
      ...current,
      { id: userMessageId, role: 'user', text: question },
      { id: assistantMessageId, role: 'assistant', text: '', suggestions: [], pending: true },
    ])

    try {
      let streamError = ''
      let streamedText = ''
      let streamFinished = false
      let streamedSuggestions: string[] = []

      await withCsrfRetry((token) =>
        streamAssistantReply(
          '/api/assistant/chat/stream',
          { message: question, session_id: sessionIdRef.current },
          {
            onChunk: (chunk) => {
              streamedText += chunk
              setWaitingForFirstChunk(false)
              setMessages((current) => current.map((entry) => (
                entry.id === assistantMessageId
                  ? { ...entry, text: streamedText, pending: true, suggestions: streamedSuggestions }
                  : entry
              )))
            },
            onSuggestions: (suggestions) => {
              streamedSuggestions = suggestions
              setMessages((current) => current.map((entry) => (
                entry.id === assistantMessageId
                  ? { ...entry, suggestions }
                  : entry
              )))
            },
            onDone: (payload) => {
              streamFinished = true
              const nextMessages = mapAssistantHistory(Array.isArray(payload.assistant_history) ? payload.assistant_history : [])
              if (nextMessages.length) {
                setMessages(nextMessages)
                return
              }
              const assistant = payload.assistant as { reply?: unknown; suggestions?: unknown; provider?: unknown } | undefined
              setMessages((current) => current.map((entry) => (
                entry.id === assistantMessageId
                  ? {
                    ...entry,
                    text: String(assistant?.reply ?? streamedText).trim(),
                    suggestions: Array.isArray(assistant?.suggestions) ? assistant?.suggestions as string[] : streamedSuggestions,
                    pending: false,
                    provider: String(assistant?.provider ?? '') || undefined,
                  }
                  : entry
              )))
            },
            onError: (detail) => {
              streamError = detail
            },
          },
          token,
        ),
      )

      if (streamError) {
        throw new Error(streamError)
      }

      if (!streamFinished) {
        await sendMessageFallback(question)
      }
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
