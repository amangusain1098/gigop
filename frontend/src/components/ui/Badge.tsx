import './index.css'

type Status = 'active' | 'ok' | 'error' | 'warning' | 'queued' | 'pending' | 'idle'

export interface BadgeProps {
  status: Status
  label?: string
  className?: string
}

export default function Badge({ status, label, className = '' }: BadgeProps) {
  const classes = ['badge', `badge--${status}`, className].filter(Boolean).join(' ')

  return (
    <span className={classes}>
      <span className="badge__dot" aria-hidden="true" />
      <span className="badge__label">{label ?? status}</span>
    </span>
  )
}
