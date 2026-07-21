import { useState, useCallback, useRef, useEffect } from 'react'
import { useSearchParams, Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, Trash2, List, Loader2, MapPin, Sparkles } from 'lucide-react'
import { ChatBox, type Message } from '../components/ChatBox'
import { ChatInput } from '../components/ChatInput'
import { IntentBar } from '../components/IntentBar'
import {
  sendDialogMessage,
  generateDialogPlan,
  type DialogSlots,
  type DialogStage,
  type DialogSuggestion,
  type TravelItinerary,
} from '../lib/api'

function genId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

// 会话持久化（sessionStorage）：刷新/离开后再进入不丢历史与意图槽位。
const STORAGE_KEY = 'travelmind_dialog'
const MAX_STORED = 30

interface DialogState {
  sessionId: string | null
  stage: DialogStage
  slots: DialogSlots
  itinerary: TravelItinerary | null
  suggestions: DialogSuggestion[] | null
  confirm: boolean
}

const EMPTY_SLOTS: DialogSlots = {
  city: null,
  days: null,
  date: '下周',
  companions: '不限',
  budget_level: '舒适',
  tags: [],
  pace: '休闲',
}

interface StoredDialog {
  messages: Message[]
  dialog: DialogState | null
}

function loadStored(): StoredDialog {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw)
      return {
        messages: Array.isArray(parsed.messages) ? parsed.messages : [],
        dialog: parsed.dialog || null,
      }
    }
  } catch {
    // corrupted — start fresh
  }
  return { messages: [], dialog: null }
}

export function ChatPage() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const initialQuery = searchParams.get('q') || ''

  const [stored] = useState<StoredDialog>(loadStored)
  const [messages, setMessages] = useState<Message[]>(stored.messages)
  const [loading, setLoading] = useState(false)
  const [dialog, setDialog] = useState<DialogState>(
    stored.dialog || {
      sessionId: null,
      stage: 'collecting',
      slots: EMPTY_SLOTS,
      itinerary: null,
      suggestions: null,
      confirm: false,
    }
  )
  const [generating, setGenerating] = useState(false)
  const hasSentInitial = useRef(false)

  // 持久化
  useEffect(() => {
    try {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ messages: messages.slice(-MAX_STORED), dialog })
      )
    } catch {
      // non-fatal
    }
  }, [messages, dialog])

  const applyResponse = useCallback((d: import('../lib/api').DialogResponse) => {
    setDialog((prev) => ({
      ...prev,
      sessionId: d.session_id,
      stage: d.stage,
      slots: d.slots,
      suggestions: d.suggestions || null,
      confirm: d.confirm,
      itinerary: d.itinerary ?? prev.itinerary,
    }))
    if (d.reply) {
      setMessages((prev) => [
        ...prev,
        { id: genId(), role: 'assistant', content: d.reply },
      ])
    }
  }, [])

  const sendText = useCallback(
    async (text: string) => {
      setMessages((prev) => [...prev, { id: genId(), role: 'user', content: text }])
      setLoading(true)
      try {
        const d = await sendDialogMessage({
          sessionId: dialog.sessionId || undefined,
          text,
        })
        applyResponse(d)
      } catch {
        setMessages((prev) => [
          ...prev,
          { id: genId(), role: 'assistant', content: '抱歉，服务暂时不可用，请稍后重试。' },
        ])
      } finally {
        setLoading(false)
      }
    },
    [dialog.sessionId, applyResponse]
  )

  // 首页带 q 进入
  useEffect(() => {
    if (initialQuery && !hasSentInitial.current) {
      hasSentInitial.current = true
      sendText(initialQuery)
    }
  }, [initialQuery, sendText])

  const handleSlotChange = useCallback(
    async (override: Partial<DialogSlots>) => {
      try {
        const d = await sendDialogMessage({
          sessionId: dialog.sessionId || undefined,
          slotOverride: override,
        })
        applyResponse(d)
      } catch {
        // 槽位编辑失败保持现状
      }
    },
    [dialog.sessionId, applyResponse]
  )

  const handleGenerate = useCallback(async () => {
    if (!dialog.sessionId || generating) return
    setGenerating(true)
    try {
      const d = await generateDialogPlan(dialog.sessionId)
      applyResponse(d)
    } catch {
      setMessages((prev) => [
        ...prev,
        { id: genId(), role: 'assistant', content: '生成失败了，请再点一次试试。' },
      ])
    } finally {
      setGenerating(false)
    }
  }, [dialog.sessionId, generating, applyResponse])

  const openItinerary = useCallback(() => {
    if (!dialog.itinerary) return
    sessionStorage.setItem('travelmind_itinerary', JSON.stringify(dialog.itinerary))
    navigate('/itinerary')
  }, [dialog.itinerary, navigate])

  const clearAll = useCallback(() => {
    setMessages([])
    setDialog({
      sessionId: null,
      stage: 'collecting',
      slots: EMPTY_SLOTS,
      itinerary: null,
      suggestions: null,
      confirm: false,
    })
    sessionStorage.removeItem(STORAGE_KEY)
  }, [])

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
          <h2 className="text-sm font-semibold text-slate-800">对话式规划</h2>
          <p className="text-xs text-slate-400">
            {dialog.stage === 'delivered'
              ? '行程已生成 · 直接说修改意见'
              : '多轮对话收敛意图，确认后生成行程卡片'}
          </p>
        </div>
        <Link
          to="/history"
          className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-slate-400 transition-colors hover:bg-slate-100 hover:text-blue-500"
          aria-label="我的行程"
        >
          <List size={14} />
          我的行程
        </Link>
        {(messages.length > 0 || dialog.sessionId) && (
          <button
            onClick={clearAll}
            className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-slate-400 transition-colors hover:bg-slate-100 hover:text-red-500"
            aria-label="清空对话"
          >
            <Trash2 size={14} />
            清空
          </button>
        )}
      </header>

      {/* 意图状态条 */}
      <IntentBar slots={dialog.slots} onSlotChange={handleSlotChange} disabled={loading || generating} />

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        <ChatBox messages={messages} loading={loading || generating} />

        {/* 对话流内嵌动作区 */}
        <div className="mx-auto max-w-3xl px-4 pb-4">
          {/* 组合建议 chips */}
          {dialog.suggestions && dialog.suggestions.length > 0 && !loading && (
            <div className="mb-3 flex flex-wrap gap-2">
              {dialog.suggestions.map((s, i) => (
                <button
                  key={i}
                  onClick={() => sendText(s.text || s.label)}
                  className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs text-blue-700 transition-colors hover:bg-blue-100"
                >
                  {s.label}
                </button>
              ))}
            </div>
          )}

          {/* 确认摘要 → 生成按钮 */}
          {dialog.stage === 'confirming' && dialog.confirm && !generating && (
            <button
              onClick={handleGenerate}
              className="mb-3 flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-5 py-3 text-sm font-medium text-white shadow-sm transition-colors hover:bg-blue-700"
            >
              <Sparkles size={16} />
              生成行程卡片
            </button>
          )}

          {/* 生成中 */}
          {generating && (
            <div className="mb-3 flex items-center justify-center gap-2 rounded-xl border border-blue-100 bg-blue-50 px-5 py-3 text-sm text-blue-600">
              <Loader2 size={16} className="animate-spin" />
              正在生成行程，约需 30-60 秒...
            </div>
          )}

          {/* 精简行程卡 */}
          {dialog.stage === 'delivered' && dialog.itinerary && (
            <button
              onClick={openItinerary}
              className="mb-3 w-full rounded-xl border border-slate-200 bg-white p-4 text-left shadow-sm transition-shadow hover:shadow-md"
            >
              <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
                <MapPin size={16} className="text-blue-500" />
                {dialog.itinerary.trip.title}
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                {dialog.itinerary.trip.stats.slice(0, 4).map((s, i) => (
                  <span key={i} className="rounded-md bg-slate-50 px-2 py-1 text-xs text-slate-600">
                    {s.value} · {s.label}
                  </span>
                ))}
              </div>
              <div className="mt-2 space-y-1">
                {dialog.itinerary.days.map((d) => (
                  <p key={d.day} className="text-xs text-slate-500">
                    <span className="font-medium text-slate-700">D{d.day}</span> {d.theme} · {d.title}
                  </p>
                ))}
              </div>
              <p className="mt-2 text-xs font-medium text-blue-600">点击查看完整行程 →</p>
            </button>
          )}
        </div>
      </div>

      {/* Input */}
      <ChatInput onSend={sendText} disabled={loading || generating} />
    </div>
  )
}
