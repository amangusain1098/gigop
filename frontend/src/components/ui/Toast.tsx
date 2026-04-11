import type { ToastItem } from './useToast'

import './index.css'

const TOAST_ICONS: Record<ToastItem['tone'], string> = {
  success: '✓',
  error: '!',
  info: 'i',
  warning: '!',
}

interface ToastProps {
  toast: ToastItem
  onClose: (id: string) => void
}

export default function Toast({ toast, onClose }: ToastProps) {
  return (
    <div className={`toast toast--${toast.tone}`} role="status" aria-live="polite">
      <span className="toast__icon" aria-hidden="true">
        {TOAST_ICONS[toast.tone]}
      </span>
      <p className="toast__message">{toast.message}</p>
      <button
        type="button"
        className="toast__close"
        onClick={() => onClose(toast.id)}
        aria-label="Dismiss notification"
      >
        ×
      </button>
    </div>
  )
}
