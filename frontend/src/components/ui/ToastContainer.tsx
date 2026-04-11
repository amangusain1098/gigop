import Toast from './Toast'
import { useToastStore } from './useToast'
import './index.css'

export default function ToastContainer() {
  const { toasts, dismissToast } = useToastStore()

  return (
    <div className="toast-container" aria-live="polite" aria-atomic="true">
      {toasts.map((toast) => (
        <Toast key={toast.id} toast={toast} onClose={dismissToast} />
      ))}
    </div>
  )
}
