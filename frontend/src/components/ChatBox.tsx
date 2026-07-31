import { useEffect, useRef, memo } from 'react'
import { User, Bot } from 'lucide-react'

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  isStreaming?: boolean
  /** Phase 18 M5.1: 标记错误消息,带可重试状态与回调。 */
  isError?: boolean
  isRetryable?: boolean
  errorSuggestion?: string | null
  onRetry?: () => void
}

interface ChatBoxProps {
  messages: Message[]
  loading?: boolean
  /** 空状态时点击开场白 chips 直接发送（不传则不显示 chips） */
  onStarterSelect?: (text: string) => void
}

/** Escape HTML entities to prevent XSS before rendering LLM output as HTML. */
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

/** Simple bold/italic/heading markdown rendering without a library.
 *  Input is HTML-escaped first to prevent XSS injection. */
function formatContent(text: string): string {
  const escaped = escapeHtml(text)
  return escaped
    .replace(/### (.+)/g, '<strong>$1</strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/^\- (.+)/gm, '· $1')
    .replace(/^(\d+)\. (.+)/gm, '$1. $2')
}

function MessageBubble({ msg }: { msg: Message }) {
  const isUser = msg.role === 'user'

  // Phase 18 M5.1: 错误消息样式与重试按钮
  if (msg.isError) {
    return (
      <div className="flex gap-3 animate-fade-in-up">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-red-100 text-red-700 shadow-sm dark:bg-red-900/30 dark:text-red-300">
          <Bot size={16} />
        </div>
        <div className="max-w-[75%] rounded-2xl rounded-tl-sm border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-700 shadow-sm dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
          <div className="font-medium">{msg.content}</div>
          {msg.errorSuggestion && (
            <div className="mt-1.5 flex items-start gap-1.5 text-xs text-red-600 dark:text-red-400">
              <span>💡</span>
              <span>{msg.errorSuggestion}</span>
            </div>
          )}
          {msg.isRetryable && msg.onRetry && (
            <button
              onClick={() => msg.onRetry?.()}
              className="mt-2 inline-flex items-center gap-1 rounded-full bg-red-600 px-3 py-1 text-xs font-medium text-white transition-colors hover:bg-red-700"
            >
              ↻ 重试
            </button>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className={`flex gap-3 animate-fade-in-up ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full shadow-sm ${
          isUser
            ? 'bg-gradient-to-br from-brand-400 to-brand-600 text-white'
            : 'bg-accent-100 text-accent-700'
        }`}
      >
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>

      {/* Bubble */}
      <div
        className={`max-w-[75%] text-sm leading-relaxed ${
          isUser
            ? 'rounded-2xl rounded-tr-sm bg-gradient-to-br from-brand-500 to-brand-600 px-4 py-2.5 text-white shadow-sm'
            : 'glass rounded-2xl rounded-tl-sm border border-border-light px-4 py-2.5 text-slate-700 dark:text-slate-300 shadow-card'
        }`}
      >
        {isUser ? (
          <div className="whitespace-pre-wrap break-words">{msg.content}</div>
        ) : (
          <div
            className="whitespace-pre-wrap break-words"
            dangerouslySetInnerHTML={{ __html: formatContent(msg.content) }}
          />
        )}
        {msg.isStreaming && (
          <span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-current align-text-bottom" />
        )}
      </div>
    </div>
  )
}

function LoadingDots() {
  return (
    <div className="flex gap-3" role="status" aria-label="正在生成回复">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-accent-100 text-accent-700 shadow-sm">
        <Bot size={16} />
      </div>
      <div className="glass flex items-center gap-1 rounded-2xl rounded-tl-sm border border-border-light px-4 py-3 shadow-card">
        <span className="h-2 w-2 animate-bounce rounded-full bg-brand-400 [animation-delay:0ms]" />
        <span className="h-2 w-2 animate-bounce rounded-full bg-brand-400 [animation-delay:150ms]" />
        <span className="h-2 w-2 animate-bounce rounded-full bg-brand-400 [animation-delay:300ms]" />
      </div>
    </div>
  )
}

const STARTERS = [
  { icon: '🏮', text: '广州西关文化一日游，怎么安排？' },
  { icon: '🌃', text: '推荐广州情侣珠江夜游路线' },
  { icon: '📸', text: '广州适合拍照的小众景点有哪些？' },
  { icon: '🍵', text: '广州美食寻味，早茶文化攻略' },
]

const MessageBubbleMemo = memo(MessageBubble)

export function ChatBox({ messages, loading, onStarterSelect }: ChatBoxProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      {messages.length === 0 && !loading && (
        <div className="mx-auto flex h-full max-w-3xl flex-col justify-center">
          {/* 欢迎泡泡：像朋友先开口打招呼 */}
          <div className="flex gap-3 animate-fade-in-up">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-100 to-accent-100 dark:from-slate-700 dark:to-slate-800 shadow-sm">
              <Bot size={18} className="text-brand-500" />
            </div>
            <div className="glass max-w-[85%] rounded-2xl rounded-tl-sm border border-border-light px-4 py-3 text-sm leading-relaxed text-slate-700 dark:text-slate-300 shadow-card">
              嗨，我是小旅 👋 你的旅行搭子～想去哪儿玩、玩几天、喜欢什么，
              随便聊聊就行，剩下的交给我！不知道说啥的话，点下面随便一个👇
            </div>
          </div>
          {onStarterSelect && (
            <div className="mt-4 grid grid-cols-1 gap-2 pl-12 sm:grid-cols-2 animate-fade-in-up [animation-delay:120ms]">
              {STARTERS.map((s) => (
                <button
                  key={s.text}
                  onClick={() => onStarterSelect(s.text)}
                  className="hover-lift flex items-center gap-2.5 rounded-2xl border border-border bg-white dark:bg-slate-900 px-4 py-3 text-left text-sm text-slate-700 dark:text-slate-300 shadow-card hover:border-brand-300 dark:hover:border-brand-700 hover:bg-brand-50/50 dark:hover:bg-brand-900/30"
                >
                  <span className="text-lg">{s.icon}</span>
                  <span>{s.text}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {messages.map((msg) => (
          <MessageBubbleMemo key={msg.id} msg={msg} />
        ))}
        {loading && <LoadingDots />}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
