import { useState, useCallback, useRef, useEffect } from 'react'
import { useSearchParams, Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, Trash2, List, Loader2, MapPin, Sparkles, Check } from 'lucide-react'
import { ChatBox, type Message } from '../components/ChatBox'
import { ChatInput } from '../components/ChatInput'
import { IntentBar } from '../components/IntentBar'
import { getDeviceId } from '../lib/deviceId'
import {
  sendDialogMessage,
  generateDialogPlan,
  type DialogSlots,
  type DialogStage,
  type DialogSuggestion,
  type TravelItinerary,
} from '../lib/api'
import { useSavedPlaces } from '../lib/savedPlaces'

// 生成管线阶段（与后端 orchestrator progress 事件一致）
const PLAN_STEPS = [
  { step: 'profile_extraction', label: '提取用户画像' },
  { step: 'trend_analysis', label: '分析热门趋势' },
  { step: 'weather_fetch', label: '获取天气数据' },
  { step: 'rag_retrieval', label: '检索知识库' },
  { step: 'recommendation', label: '评分和排序' },
  { step: 'planning', label: '生成行程规划' },
] as const

type StepStatus = 'pending' | 'running' | 'done'
interface PlanStep {
  step: string
  label: string
  status: StepStatus
  message?: string
}

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
  itineraryId: string | null
  suggestions: DialogSuggestion[] | null
  confirm: boolean
  // Phase 8.1
  refused?: boolean
  refuse_reason?: string | null
  coverage_warning?: string | null
}

const EMPTY_SLOTS: DialogSlots = {
  city: '广州',
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

  // SSR-safe: initialize empty, load from sessionStorage in useEffect (avoid hydration mismatch)
  const [storedLoaded, setStoredLoaded] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(false)
  const [dialog, setDialog] = useState<DialogState>({
    sessionId: null,
    stage: 'collecting',
    slots: EMPTY_SLOTS,
    itinerary: null,
    itineraryId: null,
    suggestions: null,
    confirm: false,
  })
  const [generating, setGenerating] = useState(false)
  const [planSteps, setPlanSteps] = useState<PlanStep[]>([])
  const hasSentInitial = useRef(false)
  const abortRef = useRef<AbortController | null>(null)

  // Hydrate state from sessionStorage on client-side only (SSR-safe)
  useEffect(() => {
    if (storedLoaded) return
    const stored = loadStored()
    if (stored.messages.length > 0) setMessages(stored.messages)
    if (stored.dialog) setDialog(stored.dialog)
    setStoredLoaded(true)
  }, [storedLoaded])

  // 持久化
  useEffect(() => {
    if (!storedLoaded) return // don't persist until initial load is complete
    try {
      sessionStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({ messages: messages.slice(-MAX_STORED), dialog })
      )
    } catch {
      // non-fatal
    }
  }, [messages, dialog, storedLoaded])

  // 组件卸载时取消 SSE 请求，防止 unmount 后继续更新状态
  useEffect(() => {
    return () => {
      if (abortRef.current && generating) {
        abortRef.current.abort()
      }
      abortRef.current = null
    }
  }, [generating])

  const applyResponse = useCallback((d: import('../lib/api').DialogResponse) => {
    setDialog((prev) => ({
      ...prev,
      sessionId: d.session_id,
      stage: d.stage,
      slots: d.slots,
      suggestions: d.suggestions || null,
      confirm: d.confirm,
      itinerary: d.itinerary ?? prev.itinerary,
      itineraryId: d.itinerary_id ?? prev.itineraryId,
      // Phase 8.1
      refused: d.refused || false,
      refuse_reason: d.refuse_reason || null,
      coverage_warning: d.coverage_warning || null,
    }))
    if (d.reply) {
      setMessages((prev) => [
        ...prev,
        { id: genId(), role: 'assistant', content: d.reply },
      ])
    }
  }, [])

  const { getPlacesForPrompt } = useSavedPlaces()
  const getPlacesForPromptRef = useRef(getPlacesForPrompt)
  useEffect(() => { getPlacesForPromptRef.current = getPlacesForPrompt }, [getPlacesForPrompt])

  const sendText = useCallback(
      async (text: string) => {
        const userMsg = { id: genId(), role: 'user' as const, content: text }
        const errorMsgId = genId()
        setMessages((prev) => [...prev, userMsg])
        setLoading(true)
        // Phase 15.4: Only send saved places that match current city context
        const savedPrompt = getPlacesForPromptRef.current(dialog.slots?.city ?? undefined)
        const enrichedText = savedPrompt ? `${text}\n\n${savedPrompt}` : text
        try {
          const d = await sendDialogMessage({
            sessionId: dialog.sessionId || undefined,
            text: enrichedText,
          })
          applyResponse(d)
        } catch (err) {
                // Phase 18 M5.1: 用 APIError 显示后端 suggestion + retryable
                const apiErr = err && typeof err === 'object' && 'code' in err
                  ? (err as { code: unknown; message?: string; suggestion?: string | null; retryable?: boolean })
                  : null
                const message = apiErr?.message || '抱歉,服务暂时不可用'
                const suggestion = apiErr?.suggestion ?? '请稍后重试'
                const retryable = apiErr?.retryable ?? true
          setMessages((prev) => [
            ...prev,
            {
              id: errorMsgId,
              role: 'assistant',
              content: message,
              isError: true,
              isRetryable: retryable,
              errorSuggestion: suggestion,
              onRetry: retryable
                ? () => {
                    // 移除错误消息并重发同一文本
                    setMessages((prev) => prev.filter((m) => m.id !== errorMsgId))
                    sendText(text)
                  }
                : undefined,
            },
          ])
        } finally {
          setLoading(false)
        }
      },
      [dialog.sessionId, dialog.slots?.city, applyResponse]
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
    const steps: PlanStep[] = PLAN_STEPS.map((s) => ({ ...s, status: 'pending' }))
    setPlanSteps([...steps])
    let errorMsg: string | null = null
    try {
      // Phase 14: append saved places before generating
      const savedPrompt = getPlacesForPromptRef.current()
      if (savedPrompt && dialog.sessionId) {
        // Send a dialog message with saved places to set context before generating
        try {
          await sendDialogMessage({ sessionId: dialog.sessionId, text: savedPrompt })
        } catch { /* non-fatal */ }
      }
      // Phase 12.29b: 创建新的 AbortController，组件卸载时自动中止
      abortRef.current = new AbortController()
      // SSE 真实阶段进度（Phase 12.24）——与 /agent/plan/stream 同一事件源
      const res = await fetch('/api/v1/dialog/generate/stream', {
        signal: abortRef.current.signal,
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Device-ID': getDeviceId(),
        },
        body: JSON.stringify({ session_id: dialog.sessionId }),
      })
      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      for (;;) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const event = JSON.parse(line.slice(6))
            if (event.event === 'progress') {
              const idx = steps.findIndex((s) => s.step === event.step)
              if (idx !== -1) {
                for (let i = 0; i < idx; i++) steps[i] = { ...steps[i], status: 'done' }
                steps[idx] = {
                  ...steps[idx],
                  status: event.status === 'done' ? 'done' : 'running',
                  message: event.message,
                }
                setPlanSteps([...steps])
              }
            } else if (event.event === 'done') {
              applyResponse(event.data)
            } else if (event.event === 'error') {
              errorMsg = event.message || '生成失败'
            }
          } catch {
            // skip unparseable lines
          }
        }
      }
      if (errorMsg) {
        setMessages((prev) => [
          ...prev,
          { id: genId(), role: 'assistant', content: `生成失败了：${errorMsg}，请再点一次试试。` },
        ])
      }
    } catch (e: unknown) {
      // Phase 12.29b: 组件卸载时中止SSE请求，不更新状态
      if (e instanceof DOMException && e.name === 'AbortError') {
        return
      }
      // SSE 不可用时回退阻塞式接口（旧后端兼容）
      try {
        const d = await generateDialogPlan(dialog.sessionId)
        applyResponse(d)
      } catch {
        setMessages((prev) => [
          ...prev,
          { id: genId(), role: 'assistant', content: '生成失败了，请再点一次试试。' },
        ])
      }
    } finally {
      abortRef.current = null
      setGenerating(false)
      setPlanSteps([])
    }
  }, [dialog.sessionId, generating, applyResponse])

  const openItinerary = useCallback(() => {
    if (!dialog.itinerary) return
    sessionStorage.setItem('travelmind_itinerary', JSON.stringify(dialog.itinerary))
    const params = dialog.itineraryId ? `?id=${encodeURIComponent(dialog.itineraryId)}` : ''
    navigate(`/itinerary${params}`)
  }, [dialog.itinerary, dialog.itineraryId, navigate])

  const clearAll = useCallback(() => {
    setMessages([])
    setDialog({
      sessionId: null,
      stage: 'collecting',
      slots: EMPTY_SLOTS,
      itinerary: null,
      itineraryId: null,
      suggestions: null,
      confirm: false,
    })
    sessionStorage.removeItem(STORAGE_KEY)
  }, [])

  return (
    <div className="relative flex h-screen flex-col overflow-hidden bg-surface-secondary sm:pb-0">
      {/* 弱化极光背景（Phase 12.24） */}
      <div aria-hidden className="aurora aurora-soft">
        <span /><span /><span />
      </div>
      {/* Header */}
      <header className="glass relative flex items-center gap-2 border-b border-border-light px-3 py-2.5 sm:gap-3 sm:px-4 sm:py-3">
        <Link
          to="/"
          className="rounded-xl p-1.5 text-slate-500 dark:text-slate-400 transition-colors hover:bg-brand-50 dark:hover:bg-brand-900/30 hover:text-brand-600 dark:hover:text-brand-400"
          aria-label="返回首页"
        >
          <ArrowLeft size={20} />
        </Link>
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200">对话式规划</h2>
          <p className="hidden text-xs text-slate-400 dark:text-slate-500 sm:block">
            {dialog.stage === 'delivered'
              ? '行程已生成 · 直接说修改意见'
              : dialog.stage === 'refused'
              ? '该目的地暂不支持 · 请选择其他城市'
              : '多轮对话收敛意图，确认后生成行程卡片'}
          </p>
        </div>
        <Link
          to="/history"
          className="flex items-center gap-1 rounded-xl px-2 py-1.5 text-xs text-slate-400 dark:text-slate-500 transition-colors hover:bg-brand-50 dark:hover:bg-brand-900/30 hover:text-brand-600 dark:hover:text-brand-400"
          aria-label="我的行程"
        >
          <List size={14} />
          <span className="hidden sm:inline">我的行程</span>
        </Link>
        {(messages.length > 0 || dialog.sessionId) && (
          <button
            onClick={clearAll}
            className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-slate-400 dark:text-slate-500 transition-colors hover:bg-slate-100 dark:bg-slate-800 hover:text-red-500"
            aria-label="清空对话"
          >
            <Trash2 size={14} />
            <span className="hidden sm:inline">清空</span>
          </button>
        )}
      </header>

      {/* 意图状态条 */}
      <div className="relative">
        <IntentBar slots={dialog.slots} onSlotChange={handleSlotChange} disabled={loading || generating} />
      </div>

      {/* Messages */}
      <div className="relative flex-1 overflow-y-auto">
        <ChatBox messages={messages} loading={loading || generating} onStarterSelect={sendText} />

        {/* 对话流内嵌动作区 */}
        <div className="mx-auto max-w-3xl px-4 pb-4">
          {/* 组合建议 chips */}
          {dialog.suggestions && dialog.suggestions.length > 0 && !loading && (
            <div className="mb-3 flex flex-wrap gap-2">
              {dialog.suggestions.map((s) => (
                <button
                  key={s.label || s.text}
                  onClick={() => sendText(s.text || s.label)}
                  className="rounded-full border border-brand-200 dark:border-brand-800 bg-brand-50 dark:bg-brand-900/30 px-3 py-1.5 text-xs font-medium text-brand-700 dark:text-brand-300 transition-all hover:bg-brand-100 dark:hover:bg-brand-900/50 hover:shadow-sm"
                >
                  {s.label}
                </button>
              ))}
            </div>
          )}

          {/* Phase 8.1: 拒答卡片 — KB外城市 */}
          {dialog.refused && (
            <div className="mb-3 rounded-2xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 p-4">
              <p className="text-sm font-medium text-amber-800 dark:text-amber-300">⚠️ 暂不支持该目的地</p>
              <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
                {dialog.refuse_reason || '该城市暂不在知识库覆盖范围内，建议选择以下支持的城市。'}
              </p>
              {dialog.suggestions && dialog.suggestions.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {dialog.suggestions.map((s, i) => (
                    <button
                      key={i}
                      onClick={() => sendText(s.text || s.label || `我想去${s.city}玩${s.days}天`)}
                      className="rounded-full border border-amber-300 dark:border-amber-700 bg-white dark:bg-slate-900 px-3 py-1.5 text-xs font-medium text-amber-700 dark:text-amber-400 transition-colors hover:bg-amber-100 dark:hover:bg-amber-900/30"
                    >
                      {s.label || s.city}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Phase 8.1: 覆盖降级提示条 */}
          {dialog.coverage_warning && dialog.itinerary && (
            <div className="mb-3 rounded-lg border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 px-4 py-2 text-xs text-amber-700 dark:text-amber-400">
              ⚠️ {dialog.coverage_warning}
            </div>
          )}

          {/* 确认摘要 → 生成按钮 */}
          {dialog.stage === 'confirming' && dialog.confirm && !generating && (
            <button
              onClick={handleGenerate}
              className="btn-primary mb-3 flex w-full gap-2 rounded-2xl px-5 py-3 text-sm"
            >
              <Sparkles size={16} />
              生成行程卡片
            </button>
          )}

          {/* 生成中：真实管线阶段进度（SSE） */}
          {generating && (
            <div className="card mb-3 p-4">
              <div className="flex items-center gap-2 text-sm font-semibold text-brand-600 dark:text-brand-400">
                <Loader2 size={16} className="animate-spin" />
                正在生成行程，约需 30-60 秒
              </div>
              <ol className="mt-3 space-y-2">
                {planSteps.map((s) => (
                  <li key={s.step} className="flex items-center gap-2.5 text-xs">
                    {s.status === 'done' ? (
                      <span className="flex h-4.5 w-4.5 items-center justify-center rounded-full bg-success-100">
                        <Check size={12} className="text-success-600" />
                      </span>
                    ) : s.status === 'running' ? (
                      <Loader2 size={16} className="animate-spin text-brand-500" />
                    ) : (
                      <span className="h-4 w-4 rounded-full border border-border" />
                    )}
                    <span
                      className={
                        s.status === 'pending'
                          ? 'text-slate-300 dark:text-slate-600'
                          : s.status === 'running'
                          ? 'font-medium text-slate-800 dark:text-slate-200'
                          : 'text-slate-500 dark:text-slate-400'
                      }
                    >
                      {s.label}
                    </span>
                    {s.status === 'running' && s.message && (
                      <span className="truncate text-slate-400 dark:text-slate-500">{s.message}</span>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          )}

          {/* 精简行程卡 + 节奏模板 */}
          {dialog.stage === 'delivered' && dialog.itinerary && (
            <>
              <button onClick={openItinerary} className="card hover-lift mb-2 w-full p-4 text-left">
                <div className="flex items-center gap-2 text-sm font-bold text-slate-900 dark:text-slate-100">
                  <MapPin size={16} className="text-brand-500" />
                  {dialog.itinerary.trip.title}
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {dialog.itinerary.trip.stats.slice(0, 4).map((s, i) => (
                    <span key={i} className="rounded-lg bg-surface-secondary px-2 py-1 text-xs text-slate-600 dark:text-slate-400">
                      {s.value} · {s.label}
                    </span>
                  ))}
                </div>
                <div className="mt-2 space-y-1">
                  {dialog.itinerary.days.map((d) => (
                    <p key={d.day} className="text-xs text-slate-500 dark:text-slate-400">
                      <span className="font-medium text-slate-700 dark:text-slate-300">{d.theme}</span> · {d.title}
                    </p>
                  ))}
                </div>
                <p className="mt-2 text-xs font-semibold text-brand-600 dark:text-brand-400">点击查看完整行程 →</p>
              </button>

              {/* Phase 14.4: 节奏模板快速调整 */}
              <div className="mb-3 flex gap-1.5">
                {[
                  { id: '休闲', icon: '🌿', label: '休闲慢游', msg: '行程太赶了，节奏放慢一点，每天少去几个地方，多留自由活动时间' },
                  { id: '适中', icon: '⚖️', label: '适中节奏', msg: '行程节奏调到适中，每天安排合理的景点数量' },
                  { id: '紧凑', icon: '🚀', label: '紧凑充实', msg: '行程太松了，每天再多安排一些景点，节奏紧凑一些' },
                ].map((t) => (
                  <button
                    key={t.id}
                    onClick={() => sendText(t.msg)}
                    className="flex-1 rounded-xl border border-border-light bg-white dark:bg-slate-900 px-2 py-2 text-center text-xs transition-all hover:border-brand-200 dark:hover:border-brand-700 hover:bg-brand-50 dark:hover:bg-brand-900/30"
                  >
                    <span className="block text-sm">{t.icon}</span>
                    <span className="mt-0.5 block font-medium text-slate-600 dark:text-slate-400">{t.label}</span>
                  </button>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Input */}
      <div className="relative">
        <ChatInput onSend={sendText} disabled={loading || generating} />
      </div>
    </div>
  )
}
