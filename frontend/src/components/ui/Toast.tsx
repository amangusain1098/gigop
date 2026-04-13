import type { ToastItem } from './useToast'
import './index.css'

const TONE_ICON: Record<ToastItem['tone'], string> = {
  success: '✓',
  error: '!',
  info: 'i',
  warning: '!',
}

export default function Toast({
  toast,
  onClose,
}: {
  toast: ToastItem
  onClose: (id: string) => void
}) {
  return (
    <div className={`toast toast--${toast.tone}`} role="status">
      <span className="toast__icon" aria-hidden="true">{TONE_ICON[toast.tone]}</span>
      <div className="toast__body">
        <p>{toast.message}</p>
      </div>
      <button
        type="button"
        className="toast__close"
        aria-label="Dismiss notification"
        onClick={() => onClose(toast.id)}
      >
        ×
      </button>
    </div>
  )
}
