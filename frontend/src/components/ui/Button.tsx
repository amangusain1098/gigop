import type { ReactNode } from 'react'

import './index.css'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'
type Size = 'sm' | 'md' | 'lg'

export interface ButtonProps {
  variant?: Variant
  size?: Size
  loading?: boolean
  disabled?: boolean
  onClick?: () => void
  children: ReactNode
  type?: 'button' | 'submit'
  className?: string
}

export default function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  disabled = false,
  onClick,
  children,
  type = 'button',
  className = '',
}: ButtonProps) {
  const classes = [
    'btn',
    `btn--${variant}`,
    size !== 'md' ? `btn--${size}` : '',
    loading ? 'btn--loading' : '',
    className,
  ]
    .filter(Boolean)
    .join(' ')

  return (
    <button
      type={type}
      className={classes}
      onClick={onClick}
      disabled={disabled || loading}
      aria-busy={loading}
    >
      {loading ? <span className="btn__spinner" aria-hidden="true" /> : null}
      <span className="btn__label">{children}</span>
    </button>
  )
}
