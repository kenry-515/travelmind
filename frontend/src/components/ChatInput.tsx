import { useState, useRef, type FormEvent, type KeyboardEvent } from 'react'
import { Send } from 'lucide-react'

interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
  placeholder?: string
}

export function ChatInput({ onSend, disabled, placeholder }: ChatInputProps) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const submit = () => {
    const trimmed = value.trim()
    if (trimmed && !disabled) {
      onSend(trimmed)
      setValue('')
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto'
      }
    }
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    submit()
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter to send, Shift+Enter for newline
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const handleInput = () => {
    const el = textareaRef.current
    if (el) {
      el.style.height = 'auto'
      el.style.height = `${Math.min(el.scrollHeight, 160)}px`
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="glass flex items-end gap-2 border-t border-border-light px-4 py-3 pb-16 sm:pb-3"
    >
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={handleKeyDown}
        onInput={handleInput}
        disabled={disabled}
        rows={1}
        placeholder={placeholder || '输入你的旅行需求... (Shift+Enter 换行)'}
        className="flex-1 resize-none rounded-2xl border border-border bg-surface-secondary dark:bg-slate-800/60 px-4 py-2.5 text-sm text-slate-800 dark:text-slate-200 placeholder:text-slate-400 dark:placeholder:text-slate-500 transition-all focus:border-brand-400 dark:focus:border-brand-500 focus:bg-white dark:focus:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-100 dark:focus:ring-brand-900/40 disabled:opacity-50"
        aria-label="输入消息"
      />
      <button
        type="submit"
        disabled={disabled || !value.trim()}
        aria-label="发送"
        className="btn-primary shrink-0 rounded-2xl p-2.5"
      >
        <Send size={18} />
      </button>
    </form>
  )
}
