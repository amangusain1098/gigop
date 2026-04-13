import { useEffect, useState } from 'react'

import { fetchAssistantSessionsCount } from '../api'
import Button from '../components/ui/Button'
import './layout.css'

interface SessionCountPayload {
  active_sessions: number
  total_sessions: number
}

interface TopBarProps {
  pageTitle: string
  wsLive: boolean
  onToggleMobileNav?: () => void
}

export default function TopBar({ pageTitle, wsLive, onToggleMobileNav }: TopBarProps) {
  const [sessions, setSessions] = useState<SessionCountPayload | null>(null)

  useEffect(() => {
    let active = true

    async function loadSessionCounts() {
      try {
        const payload = await fetchAssistantSessionsCount()
        if (active) {
          setSessions(payload)
        }
      } catch {
        if (active) {
          setSessions(null)
        }
      }
    }

    void loadSessionCounts()
    const timer = window.setInterval(() => {
      void loadSessionCounts()
    }, 60000)

    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [])

  return (
    <header className="topbar">
      <div className="topbar__left">
        {onToggleMobileNav ? (
          <Button className="topbar__menu" variant="ghost" size="sm" onClick={onToggleMobileNav}>
            ☰
          </Button>
        ) : null}
        <div>
          <h1 className="topbar__title">{pageTitle}</h1>
          <p className="topbar__subtitle">Live SaaS workspace for Fiverr growth</p>
        </div>
      </div>

      <div className="topbar__right">
        <span className={`topbar-chip ${wsLive ? 'topbar-chip--ok' : 'topbar-chip--offline'}`}>
          <span className="topbar-chip__dot" aria-hidden="true" />
          {wsLive ? '● Live' : '○ Offline'}
        </span>
        <span className={`topbar-chip ${sessions ? 'topbar-chip--ok' : 'topbar-chip--idle'}`}>
          💬 {sessions ? `${sessions.active_sessions} active` : '-- active'}
        </span>
      </div>
    </header>
  )
}
