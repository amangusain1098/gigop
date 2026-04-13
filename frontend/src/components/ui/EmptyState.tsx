import type { ReactNode } from 'react'

import './index.css'

interface EmptyStateProps {
  icon: string
  title: string
  hint?: string
  action?: ReactNode
  className?: string
}

export default function EmptyState({ icon, title, hint, action, className = '' }: EmptyStateProps) {
  return (
    <div className={['empty-state', className].filter(Boolean).join(' ')}>
      <div className="empty-state__icon" aria-hidden="true">{icon}</div>
      <strong className="empty-state__title">{title}</strong>
      {hint ? <p className="empty-state__hint">{hint}</p> : null}
      {action ? <div className="empty-state__action">{action}</div> : null}
    </div>
  )
}
