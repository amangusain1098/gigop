import { useState, type ReactNode } from 'react'

import Sidebar, { type AppPageKey } from './Sidebar'
import TopBar from './TopBar'
import './layout.css'

interface LayoutProps {
  children: ReactNode
  activePage: AppPageKey
  pageTitle: string
  wsLive: boolean
  username?: string
  onNavigate: (page: AppPageKey) => void
  onLogout?: () => void
}

export default function Layout({
  children,
  activePage,
  pageTitle,
  wsLive,
  username,
  onNavigate,
  onLogout,
}: LayoutProps) {
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className="layout">
      <Sidebar
        activePage={activePage}
        onNavigate={onNavigate}
        username={username}
        onLogout={onLogout}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />
      <div className="layout__body">
        <TopBar
          pageTitle={pageTitle}
          wsLive={wsLive}
          onToggleMobileNav={() => setMobileOpen((current) => !current)}
        />
        <main className="layout__content">{children}</main>
      </div>
    </div>
  )
}
