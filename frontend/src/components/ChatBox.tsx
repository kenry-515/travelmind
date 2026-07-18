import { useEffect, useRef } from 'react'
import { User, Bot } from 'lucide-react'

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  isStreaming?: boolean
}

interface ChatBoxProps {
  messages: Message[]
  loading?: boolean
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

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div
        className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
          isUser ? 'bg-blue-600 text-white' : 'bg-amber-100 text-amber-700'
        }`}
      >
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>

      {/* Bubble */}
      <div
        className={`max-w-[75%] rounded-xl px-4 py-2.5 text-sm leading-relaxed ${
          isUser
            ? 'bg-blue-600 text-white'
            : 'bg-white text-slate-700 shadow-sm border border-slate-100'
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
    <div className="flex gap-3">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-700">
        <Bot size={16} />
      </div>
      <div className="flex items-center gap-1 rounded-xl border border-slate-100 bg-white px-4 py-3 shadow-sm">
        <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:0ms]" />
        <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:150ms]" />
        <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400 [animation-delay:300ms]" />
      </div>
    </div>
  )
}

export function ChatBox({ messages, loading }: ChatBoxProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6">
      {messages.length === 0 && !loading && (
        <div className="flex h-full flex-col items-center justify-center text-center">
          <Bot size={48} className="mb-4 text-slate-300" />
          <h3 className="mb-2 text-lg font-medium text-slate-600">
            TravelMind 旅行助手
          </h3>
          <p className="max-w-sm text-sm text-slate-400">
            告诉我你的旅行需求，我会帮你规划完美的旅程。
            试试说"推荐适合情侣的三亚三日游"吧！
          </p>
        </div>
      )}

      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}
        {loading && <LoadingDots />}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
