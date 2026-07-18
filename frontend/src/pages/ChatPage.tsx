import { useState, useCallback, useRef, useEffect } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { ChatBox, type Message } from '../components/ChatBox'
import { ChatInput } from '../components/ChatInput'
import { api } from '../lib/api'

function genId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function ChatPage() {
  const [searchParams] = useSearchParams()
  const initialQuery = searchParams.get('q') || ''

  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const hasSentInitial = useRef(false)
  const messagesRef = useRef(messages)
  const sessionRef = useRef(sessionId)

  // Keep refs in sync for stable callback
  messagesRef.current = messages
  sessionRef.current = sessionId

  // Send the initial query once on mount
  useEffect(() => {
    if (initialQuery && !hasSentInitial.current) {
      hasSentInitial.current = true

      const userMsg: Message = {
        id: genId(),
        role: 'user',
        content: initialQuery,
      }
      setMessages([userMsg])
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
          setMessages([userMsg, aiMsg])
          setSessionId(data.session_id)
        })
        .catch(() => {
          setMessages([
            userMsg,
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
        <div>
          <h2 className="text-sm font-semibold text-slate-800">TravelMind 助手</h2>
          <p className="text-xs text-slate-400">
            {sessionId ? '会话已建立' : '正在连接...'}
          </p>
        </div>
      </header>

      {/* Messages */}
      <ChatBox messages={messages} loading={loading} />

      {/* Input */}
      <ChatInput onSend={handleSend} disabled={loading} />
    </div>
  )
}
