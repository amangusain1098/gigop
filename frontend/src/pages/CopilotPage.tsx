import { useEffect, useRef, type KeyboardEvent } from 'react'
import { useState } from 'react'

interface AssistantMessage {
  id: string
  role: 'user' | 'assistant'
  text: string
  suggestions?: string[]
  pending?: boolean
  provider?: string
}

interface CopilotPageProps {
  messages: AssistantMessage[]
  busy: boolean
  input: string
  onInputChange: (value: string) => void
  onSendMessage: (prefill?: string) => Promise<void>
  onPositiveFeedback: (message: AssistantMessage) => Promise<void>
  onNegativeFeedback: (message: AssistantMessage, reason: string) => Promise<void>
  onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void
  assistantStarterPrompts: string[]
  assistantQuickPrompts: string[]
}

function resizeAssistantTextarea(element: HTMLTextAreaElement | null) {
  if (!element) return
  element.style.height = 'auto'
  element.style.height = `${Math.min(element.scrollHeight, 160)}px`
}

function TypingDots() {
  return (
    <div className="typing-dots" aria-hidden="true">
      <span />
      <span />
      <span />
    </div>
  )
}

function renderMarkdownContent(text: string) {
  const lines = text.split('\n').filter((line) => line.trim())
  if (!lines.length) return <p />
  return <>{lines.map((line, index) => <p key={`${index}-${line.slice(0, 16)}`}>{line}</p>)}</>
}

export default function CopilotPage({
  messages,
  busy,
  input,
  onInputChange,
  onSendMessage,
  onPositiveFeedback,
  onNegativeFeedback,
  onKeyDown,
  assistantStarterPrompts,
  assistantQuickPrompts,
}: CopilotPageProps) {
  const assistantLogRef = useRef<HTMLDivElement | null>(null)
  const assistantInputRef = useRef<HTMLTextAreaElement | null>(null)
  const hasAssistantConversation = messages.length > 0
  const [feedbackTarget, setFeedbackTarget] = useState<string | null>(null)
  const [feedbackReason, setFeedbackReason] = useState('')
  const [feedbackBusyId, setFeedbackBusyId] = useState('')

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      assistantLogRef.current?.scrollTo({
        top: assistantLogRef.current.scrollHeight,
        behavior: 'smooth',
      })
      assistantInputRef.current?.focus()
    })
    return () => window.cancelAnimationFrame(frame)
  }, [messages.length, busy])

  useEffect(() => {
    resizeAssistantTextarea(assistantInputRef.current)
  }, [input])

  return (
    <section className="copilot-page">
      <article className="card copilot-card">
        <div className="assistant-head">
          <div className="assistant-identity">
            <div className="assistant-avatar" aria-hidden="true">AI</div>
            <div>
              <p className="eyebrow">Gig Copilot</p>
              <strong>Ask from live app data</strong>
              <p className="assistant-subtitle">Online · live gig data</p>
            </div>
          </div>
        </div>

        {hasAssistantConversation ? (
          <div className="pill-row assistant-quick-prompts">
            {assistantQuickPrompts.map((suggestion) => (
              <button
                className="quick-prompt-chip"
                key={suggestion}
                onClick={() => void onSendMessage(suggestion)}
                disabled={busy}
              >
                {suggestion}
              </button>
            ))}
          </div>
        ) : null}

        <div className="assistant-log assistant-log--page" ref={assistantLogRef}>
          {!hasAssistantConversation && !busy ? (
            <div className="assistant-welcome">
              <div className="assistant-avatar assistant-avatar--large" aria-hidden="true">AI</div>
              <strong>Gig Copilot is ready</strong>
              <p>Optimize your gig, audit your site, generate content, and ask from live market data.</p>
              <div className="assistant-welcome-chips">
                {assistantStarterPrompts.map((suggestion) => (
                  <button
                    className="suggestion-chip"
                    key={suggestion}
                    onClick={() => void onSendMessage(suggestion)}
                    disabled={busy}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          {messages.map((entry) => (
            <div className={`assistant-bubble assistant-bubble--${entry.role}`} key={entry.id}>
              <div className="assistant-bubble-meta">
                <strong>{entry.role === 'assistant' ? 'Copilot' : 'You'}</strong>
                {entry.provider ? <span className="assistant-provider-badge">{entry.provider}</span> : null}
              </div>
              <div className="bubble-body">
                {entry.pending && !entry.text.trim() ? <TypingDots /> : renderMarkdownContent(entry.text)}
              </div>
              {entry.role === 'assistant' && !entry.pending ? (
                <div className="assistant-feedback">
                  <button
                    className="quick-prompt-chip"
                    onClick={() => {
                      setFeedbackBusyId(entry.id)
                      void onPositiveFeedback(entry).finally(() => setFeedbackBusyId(''))
                    }}
                    disabled={busy || feedbackBusyId === entry.id}
                  >
                    👍
                  </button>
                  <button
                    className="quick-prompt-chip"
                    onClick={() => {
                      setFeedbackTarget((current) => current === entry.id ? null : entry.id)
                      setFeedbackReason('')
                    }}
                    disabled={busy}
                  >
                    👎
                  </button>
                </div>
              ) : null}
              {feedbackTarget === entry.id ? (
                <div className="assistant-feedback-form">
                  <input
                    value={feedbackReason}
                    onChange={(event) => setFeedbackReason(event.target.value)}
                    placeholder="What was wrong?"
                  />
                  <button
                    className="secondary"
                    disabled={!feedbackReason.trim() || feedbackBusyId === entry.id}
                    onClick={() => {
                      setFeedbackBusyId(entry.id)
                      void onNegativeFeedback(entry, feedbackReason.trim())
                        .then(() => {
                          setFeedbackTarget(null)
                          setFeedbackReason('')
                        })
                        .finally(() => setFeedbackBusyId(''))
                    }}
                  >
                    Submit
                  </button>
                </div>
              ) : null}
              {entry.suggestions?.length ? (
                <div className="pill-row assistant-suggestion-row">
                  {entry.suggestions.map((suggestion) => (
                    <button
                      className="suggestion-chip"
                      key={suggestion}
                      onClick={() => void onSendMessage(suggestion)}
                      disabled={busy}
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>

        <div className="assistant-compose compose-bar">
          <div className="compose-inner">
            <textarea
              ref={assistantInputRef}
              rows={1}
              value={input}
              onChange={(event) => onInputChange(event.target.value)}
              onInput={(event) => resizeAssistantTextarea(event.currentTarget)}
              onKeyDown={onKeyDown}
              placeholder="Ask anything about your gig, page-one competitors, title, pricing, trust, keywords, or what to change next..."
            />
            <button
              className="compose-send-btn"
              onClick={() => void onSendMessage()}
              disabled={busy || !input.trim()}
            >
              {busy ? 'Thinking...' : 'Send'}
            </button>
          </div>
          <p className="compose-hint">Enter to send. Shift + Enter for a new line.</p>
        </div>
      </article>
    </section>
  )
}
