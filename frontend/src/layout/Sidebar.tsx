import Button from '../components/ui/Button'
import './layout.css'

export type AppPageKey =
  | 'dashboard'
  | 'optimizer'
  | 'competitors'
  | 'copilot'
  | 'brain'
  | 'metrics'
  | 'settings'

export interface SidebarItem {
  key: AppPageKey
  icon: string
  label: string
}

export const SIDEBAR_ITEMS: SidebarItem[] = [
  { key: 'dashboard', icon: '🏠', label: 'Dashboard' },
  { key: 'optimizer', icon: '🎯', label: 'Gig Optimizer' },
  { key: 'competitors', icon: '📊', label: 'Competitors' },
  { key: 'copilot', icon: '🤖', label: 'Copilot' },
  { key: 'brain', icon: '🧠', label: 'AI Brain' },
  { key: 'metrics', icon: '📈', label: 'Metrics' },
  { key: 'settings', icon: '⚙️', label: 'Settings' },
]

interface SidebarProps {
  activePage: AppPageKey
  onNavigate: (page: AppPageKey) => void
  username?: string
  onLogout?: () => void
  mobileOpen?: boolean
  onCloseMobile?: () => void
}

export default function Sidebar({
  activePage,
  onNavigate,
  username = 'Admin',
  onLogout,
  mobileOpen = false,
  onCloseMobile,
}: SidebarProps) {
  return (
    <>
      <button
        type="button"
        className={`sidebar-overlay ${mobileOpen ? 'sidebar-overlay--open' : ''}`}
        aria-label="Close navigation"
        onClick={onCloseMobile}
      />

      <aside className={`sidebar ${mobileOpen ? 'sidebar--open' : ''}`}>
        <div className="sidebar__brand">
          <span className="sidebar__brand-mark">GO</span>
          <div className="sidebar__brand-copy">
            <strong>GigOptimizer</strong>
            <span>Pro dashboard</span>
          </div>
        </div>

        <nav className="sidebar__nav" aria-label="Primary">
          {SIDEBAR_ITEMS.map((item) => (
            <button
              key={item.key}
              type="button"
              className={`sidebar__item ${activePage === item.key ? 'sidebar__item--active' : ''}`}
              onClick={() => {
                onNavigate(item.key)
                onCloseMobile?.()
              }}
            >
              <span className="sidebar__icon" aria-hidden="true">{item.icon}</span>
              <span className="nav-label">{item.label}</span>
            </button>
          ))}
        </nav>

        <div className="sidebar__footer">
          <div className="sidebar__user-chip">
            <span className="sidebar__user-dot" aria-hidden="true" />
            <span>{username}</span>
          </div>
          {onLogout ? (
            <Button variant="ghost" size="sm" onClick={onLogout}>
              Log out
            </Button>
          ) : null}
        </div>
      </aside>
    </>
  )
}
