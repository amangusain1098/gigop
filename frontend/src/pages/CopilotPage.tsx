import ReactMarkdown from 'react-markdown'
import type { KeyboardEvent } from 'react'
import type { CopilotPageProps } from './shared'

export default function CopilotPage({
  messages,
  busy,
  waitingForFirstChunk,
  input,
  onInputChange,
  onSendMessage,
  onExportChat,
  onSendFeedback,
  quickPrompts,
}: CopilotPageProps) {
  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void onSendMessage()
    }
  }

  return (
    <article className="card assistant-full-page">
      <div className="card-head">
        <h2>Gig Copilot</h2>
        <button className="secondary" onClick={onExportChat} title="Export chat">Export chat</button>
      </div>

      <div className="assistant-quick-prompts">
        {quickPrompts.map((suggestion) => (
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

      <div className="assistant-log" style={{ minHeight: '400px', maxHeight: '600px', overflowY: 'auto' }}>
        {messages.length === 0 && !busy ? (
          <div className="chat-welcome">
            <div className="chat-welcome-avatar">✦</div>
            <h3>Gig Copilot</h3>
            <p>Your AI for Fiverr ranking, SEO audits, and content that converts.</p>
            <div className="chat-welcome-chips">
              {['Rewrite my gig title', 'Who are my top competitors?', 'Audit my website SEO', 'Write a LinkedIn post'].map((question) => (
                <button key={question} className="welcome-chip" onClick={() => void onSendMessage(question)} disabled={busy}>
                  {question}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {messages.map((entry, index) => (
          <div
            className={`assistant-bubble assistant-bubble--${entry.role}`}
            key={`${entry.role}-${index}`}
          >
            <span className="bubble-meta">
              {entry.role === 'assistant' ? 'Copilot' : 'You'}
            </span>
            <div className="bubble-body">
              <ReactMarkdown>{entry.text}</ReactMarkdown>
            </div>

            {/* Thumbs up / Thumbs down feedback logic */}
            {entry.role === 'assistant' && entry.id ? (
              <div className="assistant-feedback-row" style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
                <button
                  className={`feedback-button ${entry.feedbackRating === 1 ? 'feedback-button--active' : ''}`}
                  onClick={() => void onSendFeedback(entry.id as number, 1)}
                  disabled={busy}
                  style={{ fontSize: '11px', padding: '4px 8px', borderRadius: '4px', cursor: 'pointer', background: entry.feedbackRating === 1 ? '#dcfce7' : '#f1f5f9', border: '1px solid #cbd5e1' }}
                >
                  👍 Helpful
                </button>
                <button
                  className={`feedback-button ${entry.feedbackRating === -1 ? 'feedback-button--active' : ''}`}
                  onClick={() => void onSendFeedback(entry.id as number, -1)}
                  disabled={busy}
                  style={{ fontSize: '11px', padding: '4px 8px', borderRadius: '4px', cursor: 'pointer', background: entry.feedbackRating === -1 ? '#fee2e2' : '#f1f5f9', border: '1px solid #cbd5e1' }}
                >
                  👎 Needs work
                </button>
              </div>
            ) : null}

            {entry.suggestions?.length ? (
              <div className="assistant-suggestion-row">
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

        {waitingForFirstChunk ? (
          <div className="assistant-bubble assistant-bubble--assistant assistant-bubble--pending">
            <span className="bubble-meta">Copilot</span>
            <div className="bubble-body">
              <div className="typing-dots">
                <span /><span /><span />
              </div>
            </div>
          </div>
        ) : null}
      </div>

      <div className="assistant-compose">
        <div className="compose-inner" style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
          <textarea
            className="compose-textarea"
            rows={1}
            value={input}
            onChange={(event) => onInputChange(event.target.value)}
            onInput={(event) => {
              const element = event.currentTarget
              element.style.height = 'auto'
              element.style.height = `${Math.min(element.scrollHeight, 160)}px`
            }}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your gig, SEO, competitors..."
            style={{ flex: 1, padding: '10px', borderRadius: '8px', border: '1px solid #cbd5e1', resize: 'none' }}
          />
          <button
            className="compose-send-btn"
            onClick={() => void onSendMessage()}
            disabled={busy || !input.trim()}
            title="Send"
            style={{ background: '#3b82f6', color: '#fff', border: 'none', borderRadius: '8px', padding: '0 16px', cursor: 'pointer' }}
          >
            Send
          </button>
        </div>
        <p className="compose-hint" style={{ fontSize: '11px', color: '#64748b', marginTop: '6px' }}>Enter to send · Shift+Enter for new line</p>
      </div>
    </article>
  )
}
