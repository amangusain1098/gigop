import './index.css'

type Status = 'active' | 'ok' | 'error' | 'warning' | 'queued' | 'pending' | 'idle'

export interface BadgeProps {
  status: Status
  label?: string
}

export default function Badge({ status, label }: BadgeProps) {
  return (
    <span className={`ui-badge ui-badge--${status}`}>
      <span className="ui-badge__dot" aria-hidden="true" />
      {label ?? status}
    </span>
  )
}
