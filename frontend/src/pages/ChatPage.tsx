import { useState, useCallback, useRef, useEffect } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { ArrowLeft, Trash2 } from 'lucide-react'
import { ChatBox, type Message } from '../components/ChatBox'
import { ChatInput } from '../components/ChatInput'
import { api } from '../lib/api'

function genId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

// 会话持久化（sessionStorage，按标签页隔离）：刷新/离开后再进入不丢历史。
// 后端 /chat 是无状态的（每次请求携带完整 messages），客户端恢复即可续聊。
const STORAGE_KEY = 'travelmind_chat'
const MAX_STORED = 30

interface StoredChat {
  messages: Message[]
  sessionId: string | null
}

function loadStoredChat(): StoredChat {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return {
        messages: Array.isArray(parsed.messages) ? parsed.messages : [],
        sessionId: parsed.sessionId || null,
      }
    }
  } catch {
    // corrupted storage — start fresh
  }
  return { messages: [], sessionId: null }
}

export function ChatPage() {
  const [searchParams] = useSearchParams()
  const initialQuery = searchParams.get('q') || ''

  const [stored] = useState<StoredChat>(loadStoredChat)
  const [messages, setMessages] = useState<Message[]>(stored.messages)
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(stored.sessionId)
  const hasSentInitial = useRef(false)
  const messagesRef = useRef(messages)
  const sessionRef = useRef(sessionId)

  // Keep refs in sync for stable callback
  messagesRef.current = messages
  sessionRef.current = sessionId

  // Persist chat on change (capped to keep storage small)
  useEffect(() => {
    try {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ messages: messages.slice(-MAX_STORED), sessionId })
      )
    } catch {
      // storage full or unavailable — non-fatal
    }
  }, [messages, sessionId])

  const clearChat = useCallback(() => {
    setMessages([])
    setSessionId(null)
    sessionStorage.removeItem(STORAGE_KEY)
  }, [])

  // Send the initial query once on mount
  useEffect(() => {
    if (initialQuery && !hasSentInitial.current) {
      hasSentInitial.current = true

      const userMsg: Message = {
        id: genId(),
        role: 'user',
        content: initialQuery,
      }
      setMessages((prev) => [...prev, userMsg])
      setLoading(true)

      api.post('/chat', {
        messages: [{ role: 'user', content: initialQuery }],
        session_id: null,
        stream: false,
      })
        .then(({ data }) => {
          const aiMsg: Message = {
            id: genId(),
            role: 'assistant',
            content: data.content,
          }
          setMessages((prev) => [...prev, aiMsg])
          setSessionId(data.session_id)
        })
        .catch(() => {
          setMessages((prev) => [
            ...prev,
            {
              id: genId(),
              role: 'assistant',
              content: '抱歉，连接 AI 服务时出现错误，请稍后重试。',
            },
          ])
        })
        .finally(() => setLoading(false))
    }
  }, [initialQuery])

  const handleSend = useCallback(async (text: string) => {
    const userMsg: Message = {
      id: genId(),
      role: 'user',
      content: text,
    }
    setMessages((prev) => [...prev, userMsg])
    setLoading(true)

    // Build API messages from the current state (via ref to avoid stale closure)
    const currentMessages = messagesRef.current
    const currentSession = sessionRef.current
    const apiMessages = [...currentMessages, userMsg]
      .slice(-30)
      .filter((m) => m.role !== 'system')
      .map((m) => ({ role: m.role, content: m.content }))

    try {
      const { data } = await api.post('/chat', {
        messages: apiMessages,
        session_id: currentSession,
        stream: false,
      })

      const aiMsg: Message = {
        id: genId(),
        role: 'assistant',
        content: data.content,
      }
      setMessages((prev) => [...prev, aiMsg])
      if (!currentSession) setSessionId(data.session_id)
    } catch (_err) {
      setMessages((prev) => [
        ...prev,
        {
          id: genId(),
          role: 'assistant',
          content: '抱歉，AI 服务暂时不可用，请稍后重试。',
        },
      ])
    } finally {
      setLoading(false)
    }
  }, []) // stable — uses refs instead of state

  return (
    <div className="flex h-screen flex-col bg-slate-50">
      {/* Header */}
      <header className="flex items-center gap-3 border-b border-slate-200 bg-white px-4 py-3 shadow-sm">
        <Link
          to="/"
          className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
          aria-label="返回首页"
        >
          <ArrowLeft size={20} />
        </Link>
        <div className="flex-1">
          <h2 className="text-sm font-semibold text-slate-800">TravelMind 助手</h2>
          <p className="text-xs text-slate-400">
            {messages.length > 0 ? `已进行 ${Math.ceil(messages.length / 2)} 轮对话` : '旅行问答 · 随时提问'}
          </p>
        </div>
        {messages.length > 0 && (
          <button
            onClick={clearChat}
            className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-slate-400 transition-colors hover:bg-slate-100 hover:text-red-500"
            aria-label="清空对话"
          >
            <Trash2 size={14} />
            清空
          </button>
        )}
      </header>

      {/* Messages */}
      <ChatBox messages={messages} loading={loading} />

      {/* Input */}
      <ChatInput onSend={handleSend} disabled={loading} />
    </div>
  )
}
