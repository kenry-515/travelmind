import { useEffect, useState, useCallback, type ReactNode } from 'react'
import { X } from 'lucide-react'

interface ToastItem {
  id: number
  message: ReactNode
  type: 'info' | 'success' | 'warning' | 'error'
}

let nextId = 0
let addToastFn: ((message: ReactNode, type?: ToastItem['type']) => void) | null = null

/**
 * Programmatic toast helper — call from anywhere without React context.
 * Usage: toast('消息内容')  or  toast.error('错误信息')
 */
export const toast = (message: ReactNode, type: ToastItem['type'] = 'info') => {
  addToastFn?.(message, type)
}
toast.info = (m: ReactNode) => toast(m, 'info')
toast.success = (m: ReactNode) => toast(m, 'success')
toast.warning = (m: ReactNode) => toast(m, 'warning')
toast.error = (m: ReactNode) => toast(m, 'error')

export function ToastContainer() {
  const [toasts, setToasts] = useState<ToastItem[]>([])

  const addToast = useCallback((message: ReactNode, type: ToastItem['type'] = 'info') => {
    const id = nextId++
    setToasts((prev) => [...prev, { id, message, type }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 3500)
  }, [])

  useEffect(() => {
    addToastFn = addToast
    return () => {
      addToastFn = null
    }
  }, [addToast])

  if (toasts.length === 0) return null

  const colors: Record<ToastItem['type'], string> = {
    info: 'bg-slate-800 text-white',
    success: 'bg-green-600 text-white',
    warning: 'bg-yellow-500 text-white',
    error: 'bg-red-600 text-white',
  }

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`flex items-center gap-3 rounded-lg px-4 py-3 shadow-lg animate-toast-in ${colors[t.type]} min-w-[280px] max-w-md`}
        >
          <span className="flex-1 text-sm">{t.message}</span>
          <button
            onClick={() => setToasts((prev) => prev.filter((x) => x.id !== t.id))}
            className="shrink-0 rounded p-0.5 opacity-60 transition-opacity hover:opacity-100"
            aria-label="关闭通知"
          >
            <X size={16} />
          </button>
        </div>
      ))}
    </div>
  )
}
