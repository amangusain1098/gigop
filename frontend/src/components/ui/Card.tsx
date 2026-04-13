import type { ReactNode } from 'react'

import Skeleton from './Skeleton'
import './index.css'

export interface CardProps {
  title?: string
  subtitle?: string
  action?: ReactNode
  children: ReactNode
  className?: string
  loading?: boolean
}

export default function Card({
  title,
  subtitle,
  action,
  children,
  className = '',
  loading = false,
}: CardProps) {
  return (
    <section className={['ui-card', className].filter(Boolean).join(' ')}>
      {(title || subtitle || action) ? (
        <header className="ui-card__head">
          <div className="ui-card__titles">
            {title ? <h3 className="ui-card__title">{title}</h3> : null}
            {subtitle ? <p className="ui-card__subtitle">{subtitle}</p> : null}
          </div>
          {action ? <div className="ui-card__action">{action}</div> : null}
        </header>
      ) : null}
      <div className="ui-card__body">{children}</div>
      {loading ? (
        <div className="ui-card__loading">
          <Skeleton height="1.1rem" width="48%" />
          <Skeleton height="0.9rem" width="72%" />
          <Skeleton height="5rem" width="100%" />
        </div>
      ) : null}
    </section>
  )
}
