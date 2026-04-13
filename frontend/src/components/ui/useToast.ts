import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

export type ToastTone = 'success' | 'error' | 'info' | 'warning'

export interface ToastItem {
  id: string
  tone: ToastTone
  message: string
  createdAt: number
}

interface ToastContextValue {
  toasts: ToastItem[]
  pushToast: (tone: ToastTone, message: string) => void
  dismissToast: (id: string) => void
  clearToasts: () => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

function makeToastId() {
  return `toast-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const timersRef = useRef<Map<string, number>>(new Map())

  const dismissToast = useCallback((id: string) => {
    const timer = timersRef.current.get(id)
    if (timer) {
      window.clearTimeout(timer)
      timersRef.current.delete(id)
    }
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const pushToast = useCallback((tone: ToastTone, message: string) => {
    const id = makeToastId()
    const createdAt = Date.now()
    setToasts((current) => [...current, { id, tone, message, createdAt }].slice(-3))

    const timeout = window.setTimeout(() => {
      dismissToast(id)
    }, 4000)

    timersRef.current.set(id, timeout)
  }, [dismissToast])

  const clearToasts = useCallback(() => {
    for (const timer of timersRef.current.values()) {
      window.clearTimeout(timer)
    }
    timersRef.current.clear()
    setToasts([])
  }, [])

  const value = useMemo<ToastContextValue>(() => ({
    toasts,
    pushToast,
    dismissToast,
    clearToasts,
  }), [clearToasts, dismissToast, pushToast, toasts])

  return createElement(ToastContext.Provider, { value }, children)
}

function useToastContext() {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider')
  }
  return context
}

export function useToastStore() {
  return useToastContext()
}

export function useToast() {
  const { pushToast, dismissToast, clearToasts } = useToastContext()

  return useMemo(() => ({
    success: (message: string) => pushToast('success', message),
    error: (message: string) => pushToast('error', message),
    info: (message: string) => pushToast('info', message),
    warning: (message: string) => pushToast('warning', message),
    dismiss: dismissToast,
    clear: clearToasts,
  }), [clearToasts, dismissToast, pushToast])
}
