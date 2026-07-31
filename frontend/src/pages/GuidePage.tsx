/**
 * TravelMind Agent — GuidePage (AI 虚拟导游)
 *
 * 广东智能体大赛主题页面：以"有温度的智能旅行体验"为核心，
 * 提供景点浏览/搜索 → AI 导游讲解 → 实用信息 → 周边推荐 → 追问对话的完整闭环。
 *
 * 布局：
 *  - 浏览态：搜索框 + 精选景点网格（2 列移动端 / 4 列桌面端）
 *  - 详情态：景点信息卡 + AI 讲解词 → 实用信息 + 周边推荐 → 追问对话区
 */

import { useState, useEffect, useCallback, useRef, type FormEvent, type KeyboardEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import {
  ArrowLeft,
  Search,
  Loader2,
  AlertCircle,
  MapPin,
  Ticket,
  Clock,
  Users,
  Navigation,
  Send,
  Bot,
  User,
  Sparkles,
  Compass,
  ChevronRight,
  RefreshCw,
} from 'lucide-react'
import {
  getFeaturedPOIs,
  searchGuidePOIs,
  getGuideNarration,
  chatWithGuide,
  type FeaturedPOI,
  type GuideNarration,
} from '../lib/api'

// ── 常量 ─────────────────────────────────────────────────

const DEFAULT_CITY = '广州'

/** 追问对话区显示的消息（含本地 id 用于 React key） */
interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
}

/** 生成唯一 id */
function genId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

// ── 子组件 ───────────────────────────────────────────────

/** 景点卡片（浏览态网格用） */
function POICard({ poi, onSelect }: { poi: FeaturedPOI; onSelect: (name: string) => void }) {
  return (
    <button
      onClick={() => onSelect(poi.name)}
      className="card card-glow group flex h-full flex-col overflow-hidden text-left"
    >
      {/* 缩略图 / 渐变占位 */}
      <div className="relative h-28 w-full overflow-hidden sm:h-32">
        {poi.thumbnail_url ? (
          <img
            src={poi.thumbnail_url}
            alt={poi.name}
            loading="lazy"
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-105"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-brand-100 to-accent-100 dark:from-slate-700 dark:to-slate-800">
            <Compass size={32} className="text-brand-400 dark:text-brand-500" />
          </div>
        )}
        {/* 人气角标 */}
        {poi.popularity_score > 0 && (
          <span className="absolute right-2 top-2 rounded-full bg-black/55 px-2 py-0.5 text-[10px] font-medium text-white backdrop-blur-sm">
            ★ {poi.popularity_score.toFixed(1)}
          </span>
        )}
      </div>
      {/* 文本区 */}
      <div className="flex flex-1 flex-col p-3">
        <h3 className="line-clamp-1 text-sm font-bold text-slate-900 dark:text-slate-100">
          {poi.name}
        </h3>
        <p className="mt-1 line-clamp-1 flex items-center gap-1 text-xs text-slate-400 dark:text-slate-500">
          <MapPin size={11} className="shrink-0" />
          {poi.address || '地址待补充'}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {poi.tags.slice(0, 2).map((tag) => (
            <span
              key={tag}
              className="rounded-md bg-brand-50 dark:bg-brand-900/30 px-1.5 py-0.5 text-[10px] font-medium text-brand-600 dark:text-brand-400"
            >
              {tag}
            </span>
          ))}
          <span className="ml-auto rounded-md bg-accent-50 dark:bg-accent-900/30 px-1.5 py-0.5 text-[10px] font-medium text-accent-600 dark:text-accent-400">
            {poi.price_level}
          </span>
        </div>
      </div>
    </button>
  )
}

/** 实用信息条目 */
function InfoRow({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof MapPin
  label: string
  value: string
}) {
  return (
    <div className="flex items-start gap-2.5">
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-brand-50 dark:bg-brand-900/30">
        <Icon size={14} className="text-brand-500" />
      </span>
      <div className="min-w-0">
        <p className="text-[11px] text-slate-400 dark:text-slate-500">{label}</p>
        <p className="text-sm font-medium text-slate-700 dark:text-slate-300">{value}</p>
      </div>
    </div>
  )
}

/** 聊天气泡 */
function ChatBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex gap-2.5 animate-fade-in-up ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full shadow-sm ${
          isUser
            ? 'bg-gradient-to-br from-brand-400 to-brand-600 text-white'
            : 'bg-gradient-to-br from-accent-100 to-brand-100 dark:from-slate-700 dark:to-slate-800 text-brand-500 dark:text-brand-400'
        }`}
      >
        {isUser ? <User size={14} /> : <Bot size={14} />}
      </div>
      <div
        className={`max-w-[78%] whitespace-pre-wrap break-words text-sm leading-relaxed ${
          isUser
            ? 'rounded-2xl rounded-tr-sm bg-gradient-to-br from-brand-500 to-brand-600 px-3.5 py-2 text-white shadow-sm'
            : 'glass rounded-2xl rounded-tl-sm border border-border-light px-3.5 py-2 text-slate-700 dark:text-slate-300 shadow-card'
        }`}
      >
        {msg.content}
      </div>
    </div>
  )
}

/** 骨架卡片 */
function CardSkeleton() {
  return (
    <div className="card overflow-hidden">
      <div className="skeleton-shimmer h-28 w-full sm:h-32" />
      <div className="space-y-2 p-3">
        <div className="skeleton-shimmer h-3.5 w-3/4 rounded" />
        <div className="skeleton-shimmer h-2.5 w-1/2 rounded" />
        <div className="flex gap-1.5">
          <div className="skeleton-shimmer h-3.5 w-10 rounded" />
          <div className="skeleton-shimmer h-3.5 w-10 rounded" />
        </div>
      </div>
    </div>
  )
}

// ── 主组件 ───────────────────────────────────────────────

export function GuidePage() {
  // 浏览态
  const [featuredPois, setFeaturedPois] = useState<FeaturedPOI[]>([])
  const [searchResults, setSearchResults] = useState<FeaturedPOI[] | null>(null)
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searching, setSearching] = useState(false)

  // 详情态
  const [selectedPoi, setSelectedPoi] = useState<string | null>(null)
  const [narration, setNarration] = useState<GuideNarration | null>(null)
  const [narrationLoading, setNarrationLoading] = useState(false)
  const [narrationError, setNarrationError] = useState<string | null>(null)

  // 追问对话
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([])
  const [chatInput, setChatInput] = useState('')
  const [chatLoading, setChatLoading] = useState(false)

  // refs
  const chatScrollRef = useRef<HTMLDivElement>(null)
  const detailTopRef = useRef<HTMLDivElement>(null)

  // URL ?q= 参数：来自 PlaceCard / ImagePage / HomePage 的联动跳转，自动加载该景点讲解
  const [searchParams] = useSearchParams()

  // ── 加载精选景点 ──────────────────────────────────────
  const loadFeatured = useCallback(async () => {
    setListLoading(true)
    setListError(null)
    try {
      const res = await getFeaturedPOIs(DEFAULT_CITY, 8)
      setFeaturedPois(res.pois || [])
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : '景点列表加载失败，请稍后重试。'
      setListError(msg)
    } finally {
      setListLoading(false)
    }
  }, [])

  useEffect(() => {
    loadFeatured()
  }, [loadFeatured])

  // ── 搜索景点 ──────────────────────────────────────────
  const handleSearch = useCallback(
    async (e: FormEvent) => {
      e.preventDefault()
      const q = searchQuery.trim()
      if (!q) {
        setSearchResults(null)
        return
      }
      setSearching(true)
      setListError(null)
      try {
        const results = await searchGuidePOIs(q, DEFAULT_CITY, 12)
        setSearchResults(results || [])
      } catch (err: unknown) {
        const msg =
          err instanceof Error ? err.message : '搜索失败，请稍后重试。'
        setListError(msg)
      } finally {
        setSearching(false)
      }
    },
    [searchQuery]
  )

  // ── 选中景点 → 加载讲解词 ────────────────────────────
  const handleSelectPoi = useCallback(async (poiName: string) => {
    setSelectedPoi(poiName)
    setNarration(null)
    setNarrationError(null)
    setChatMessages([])
    setChatInput('')
    setNarrationLoading(true)

    // 滚动到顶部
    window.scrollTo({ top: 0, behavior: 'smooth' })

    try {
      const data = await getGuideNarration(poiName, DEFAULT_CITY)
      setNarration(data)
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : '讲解词加载失败，请稍后重试。'
      setNarrationError(msg)
    } finally {
      setNarrationLoading(false)
    }
  }, [])

  // ── 从 URL ?q= 自动加载景点讲解（联动入口） ─────────
  useEffect(() => {
    const q = searchParams.get('q')
    if (q && q.trim()) {
      handleSelectPoi(q.trim())
    }
    // 仅在首次挂载或 q 变化时触发；handleSelectPoi 为 useCallback 稳定引用
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams])

  // ── 返回浏览态 ────────────────────────────────────────
  const handleBack = useCallback(() => {
    setSelectedPoi(null)
    setNarration(null)
    setNarrationError(null)
    setChatMessages([])
    setChatInput('')
  }, [])

  // ── 追问对话 ──────────────────────────────────────────
  const handleSendChat = useCallback(
    async (e?: FormEvent) => {
      e?.preventDefault()
      const text = chatInput.trim()
      if (!text || chatLoading || !selectedPoi) return

      const userMsg: ChatMessage = { id: genId(), role: 'user', content: text }
      // 构造传给后端的历史（不含本次 user 消息）
      const historyForApi = chatMessages.map((m) => ({
        role: m.role,
        content: m.content,
      }))

      setChatMessages((prev) => [...prev, userMsg])
      setChatInput('')
      setChatLoading(true)

      try {
        const res = await chatWithGuide(selectedPoi, text, DEFAULT_CITY, historyForApi)
        const assistantMsg: ChatMessage = {
          id: genId(),
          role: 'assistant',
          content: res.reply,
        }
        setChatMessages((prev) => [...prev, assistantMsg])
      } catch (err: unknown) {
        const fallback =
          err instanceof Error ? err.message : '导游暂时无法回答，请稍后再试。'
        setChatMessages((prev) => [
          ...prev,
          { id: genId(), role: 'assistant', content: `抱歉，${fallback}` },
        ])
      } finally {
        setChatLoading(false)
      }
    },
    [chatInput, chatLoading, selectedPoi, chatMessages]
  )

  // ── 聊天区自动滚动到底部 ──────────────────────────────
  useEffect(() => {
    const el = chatScrollRef.current
    if (el) {
      el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
    }
  }, [chatMessages, chatLoading])

  // ── 聊天输入框：Enter 发送 / Shift+Enter 换行 ──────────
  const handleChatKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendChat()
    }
  }

  // 当前展示的景点列表（搜索结果优先）
  const displayPois = searchResults ?? featuredPois
  const isBrowseMode = !selectedPoi

  // ── 渲染 ──────────────────────────────────────────────
  return (
    <div className="relative min-h-screen overflow-hidden bg-surface-secondary pb-20 sm:pb-8">
      {/* 弱化极光背景 */}
      <div aria-hidden className="aurora aurora-soft">
        <span />
        <span />
        <span />
      </div>

      {/* Header */}
      <header className="glass sticky top-0 z-10 border-b border-border-light">
        <div className="mx-auto flex max-w-5xl items-center gap-2 px-3 py-2.5 sm:gap-3 sm:px-4 sm:py-3">
          <Link
            to="/"
            className="rounded-xl p-1.5 text-slate-500 dark:text-slate-400 transition-colors hover:bg-brand-50 dark:hover:bg-brand-900/30 hover:text-brand-600 dark:hover:text-brand-400"
            aria-label="返回首页"
          >
            <ArrowLeft size={20} />
          </Link>
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
              AI 虚拟导游
            </h2>
            <p className="hidden text-xs text-slate-400 dark:text-slate-500 sm:block">
              广州智能旅行体验 · 有温度的智能旅行
            </p>
          </div>
          <span className="hidden items-center gap-1 rounded-full bg-brand-50 dark:bg-brand-900/30 px-2.5 py-1 text-xs font-medium text-brand-600 dark:text-brand-400 sm:inline-flex">
            <Sparkles size={12} />
            广东智能体大赛
          </span>
        </div>
      </header>

      <main className="relative mx-auto max-w-5xl px-4 py-6">
        {/* ════════ 浏览态：搜索 + 景点网格 ════════ */}
        {isBrowseMode && (
          <div className="animate-fade-in-up">
            {/* 标题区 */}
            <div className="mb-6 text-center">
              <div className="mb-3 inline-flex h-16 w-16 items-center justify-center rounded-3xl bg-gradient-to-br from-brand-100 to-accent-100 dark:from-slate-800 dark:to-slate-700 animate-float-slow">
                <Compass size={32} className="text-brand-500" />
              </div>
              <h1 className="display-lg mb-2">
                <span className="text-gradient">AI 虚拟导游</span>
              </h1>
              <p className="text-sm text-slate-500 dark:text-slate-400 sm:text-base">
                点选景点，聆听专属讲解 · 随时追问，懂你所想
              </p>
            </div>

            {/* 搜索框 */}
            <form onSubmit={handleSearch} className="mb-6">
              <div className="relative flex items-center">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="搜索广州景点，如：广州塔、陈家祠、白云山..."
                  className="w-full rounded-2xl border border-border bg-white dark:bg-slate-900 px-5 py-3.5 pr-14 text-base shadow-card transition-all placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-brand-400 focus:outline-none focus:ring-4 focus:ring-brand-100 dark:focus:ring-brand-900/40"
                  disabled={searching}
                />
                <button
                  type="submit"
                  disabled={searching || !searchQuery.trim()}
                  aria-label="搜索景点"
                  className="btn-primary absolute right-2 rounded-xl p-2"
                >
                  {searching ? (
                    <Loader2 size={22} className="animate-spin" />
                  ) : (
                    <Search size={22} />
                  )}
                </button>
              </div>
            </form>

            {/* 区块标题 */}
            <div className="mb-4 flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-base font-bold text-slate-800 dark:text-slate-200">
                <Sparkles size={18} className="text-brand-500" />
                {searchResults ? `搜索结果（${displayPois.length}）` : '广州精选景点'}
              </h3>
              {searchResults && (
                <button
                  onClick={() => {
                    setSearchResults(null)
                    setSearchQuery('')
                  }}
                  className="flex items-center gap-1 text-xs font-medium text-brand-600 dark:text-brand-400 hover:underline"
                >
                  <RefreshCw size={12} />
                  返回精选
                </button>
              )}
            </div>

            {/* 加载中 */}
            {listLoading && (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                {Array.from({ length: 8 }).map((_, i) => (
                  <CardSkeleton key={i} />
                ))}
              </div>
            )}

            {/* 错误 */}
            {listError && !listLoading && (
              <div className="mt-12 text-center">
                <AlertCircle size={40} className="mx-auto mb-3 text-amber-500" />
                <p className="text-slate-600 dark:text-slate-400">{listError}</p>
                <button
                  onClick={loadFeatured}
                  className="btn-secondary mt-4 px-4 py-2 text-sm"
                >
                  <RefreshCw size={14} />
                  重新加载
                </button>
              </div>
            )}

            {/* 空搜索结果 */}
            {!listLoading && !listError && displayPois.length === 0 && (
              <div className="mt-12 text-center">
                <Compass size={40} className="mx-auto mb-3 text-slate-300 dark:text-slate-600" />
                <p className="text-slate-600 dark:text-slate-400">
                  {searchResults
                    ? `未找到「${searchQuery}」相关景点，换个关键词试试？`
                    : '暂无精选景点数据'}
                </p>
              </div>
            )}

            {/* 景点网格 */}
            {!listLoading && !listError && displayPois.length > 0 && (
              <div className="stagger grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
                {displayPois.map((poi) => (
                  <POICard key={poi.name} poi={poi} onSelect={handleSelectPoi} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* ════════ 详情态：讲解 + 实用信息 + 周边 + 追问 ════════ */}
        {!isBrowseMode && (
          <div ref={detailTopRef} className="animate-fade-in-up space-y-5">
            {/* 返回按钮 */}
            <button
              onClick={handleBack}
              className="btn-secondary px-3 py-1.5 text-sm"
            >
              <ArrowLeft size={16} />
              返回景点列表
            </button>

            {/* 讲解词加载中 */}
            {narrationLoading && (
              <div className="card flex flex-col items-center justify-center gap-3 p-10 text-center">
                <Loader2 size={32} className="animate-spin text-brand-500" />
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  AI 导游正在为你准备讲解词…
                </p>
              </div>
            )}

            {/* 讲解词加载错误 */}
            {narrationError && !narrationLoading && (
              <div className="card p-8 text-center">
                <AlertCircle size={36} className="mx-auto mb-3 text-amber-500" />
                <p className="text-slate-600 dark:text-slate-400">{narrationError}</p>
                <button
                  onClick={() => selectedPoi && handleSelectPoi(selectedPoi)}
                  className="btn-secondary mt-4 px-4 py-2 text-sm"
                >
                  <RefreshCw size={14} />
                  重试
                </button>
              </div>
            )}

            {/* 讲解内容 */}
            {narration && !narrationLoading && (
              <>
                {/* ── 上半部分：景点信息卡 + AI 讲解词 ── */}
                <div className="grid gap-4 lg:grid-cols-5">
                  {/* 景点信息卡片 */}
                  <div className="card overflow-hidden lg:col-span-2">
                    {/* 头图 */}
                    <div className="relative h-40 w-full overflow-hidden">
                      {narration.poi?.thumbnail_url ? (
                        <img
                          src={narration.poi.thumbnail_url}
                          alt={narration.poi.name}
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-brand-200 to-accent-200 dark:from-slate-700 dark:to-slate-800">
                          <Compass size={48} className="text-white/70" />
                        </div>
                      )}
                      <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
                      <div className="absolute bottom-3 left-4 right-4">
                        <h2 className="text-xl font-bold text-white drop-shadow-md">
                          {narration.poi?.name || selectedPoi}
                        </h2>
                        {narration.poi?.name_en && (
                          <p className="text-xs text-white/80">{narration.poi.name_en}</p>
                        )}
                      </div>
                    </div>
                    {/* 标签 + 价格 */}
                    <div className="p-4">
                      {narration.poi?.tags && narration.poi.tags.length > 0 && (
                        <div className="mb-3 flex flex-wrap gap-1.5">
                          {narration.poi.tags.map((tag) => (
                            <span
                              key={tag}
                              className="rounded-md bg-brand-50 dark:bg-brand-900/30 px-2 py-0.5 text-xs font-medium text-brand-600 dark:text-brand-400"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                      <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
                        <MapPin size={13} className="shrink-0 text-brand-400" />
                        <span className="line-clamp-2">
                          {narration.poi?.address || narration.practical.address || '地址待补充'}
                        </span>
                      </div>
                      <div className="mt-3 flex items-center justify-between border-t border-border-light pt-3">
                        <span className="flex items-center gap-1.5 text-sm font-semibold text-accent-600 dark:text-accent-400">
                          <Ticket size={15} />
                          {formatPrice(narration)}
                        </span>
                        {narration.poi?.popularity_score != null &&
                          narration.poi.popularity_score > 0 && (
                            <span className="flex items-center gap-1 text-xs text-slate-400 dark:text-slate-500">
                              ★ {narration.poi.popularity_score.toFixed(1)}
                            </span>
                          )}
                      </div>
                    </div>
                  </div>

                  {/* AI 导游讲解词气泡 */}
                  <div className="card flex flex-col p-5 lg:col-span-3">
                    <div className="mb-3 flex items-center gap-2">
                      <span className="flex h-9 w-9 items-center justify-center rounded-full bg-gradient-to-br from-brand-100 to-accent-100 dark:from-slate-700 dark:to-slate-800">
                        <Bot size={18} className="text-brand-500" />
                      </span>
                      <div>
                        <p className="text-sm font-bold text-slate-800 dark:text-slate-200">
                          AI 导游讲解
                        </p>
                        <p className="text-[11px] text-slate-400 dark:text-slate-500">
                          带你走进{selectedPoi}的故事
                        </p>
                      </div>
                    </div>
                    <div className="glass flex-1 rounded-2xl rounded-tl-sm border border-border-light p-4">
                      <p className="whitespace-pre-wrap text-sm leading-7 text-slate-700 dark:text-slate-300">
                        {narration.narration}
                      </p>
                    </div>
                  </div>
                </div>

                {/* ── 中间：实用信息 + 周边推荐 ── */}
                <div className="grid gap-4 lg:grid-cols-2">
                  {/* 实用信息 */}
                  <div className="card p-5">
                    <h3 className="mb-4 flex items-center gap-2 text-sm font-bold text-slate-800 dark:text-slate-200">
                      <Navigation size={16} className="text-brand-500" />
                      实用信息
                    </h3>
                    <div className="grid grid-cols-2 gap-4">
                      <InfoRow
                        icon={Ticket}
                        label="门票价格"
                        value={formatPrice(narration)}
                      />
                      <InfoRow
                        icon={MapPin}
                        label="详细地址"
                        value={narration.practical.address || narration.poi?.address || '待补充'}
                      />
                      <InfoRow
                        icon={Clock}
                        label="最佳游览时间"
                        value={narration.practical.best_time || '四季皆宜'}
                      />
                      <InfoRow
                        icon={Users}
                        label="适合人群"
                        value={narration.practical.suitable_for || '所有人群'}
                      />
                    </div>
                  </div>

                  {/* 周边推荐 */}
                  <div className="card p-5">
                    <h3 className="mb-4 flex items-center gap-2 text-sm font-bold text-slate-800 dark:text-slate-200">
                      <Compass size={16} className="text-accent-500" />
                      周边推荐
                    </h3>
                    {narration.nearby && narration.nearby.length > 0 ? (
                      <div className="space-y-2">
                        {narration.nearby.map((np) => (
                          <button
                            key={np.name}
                            onClick={() => handleSelectPoi(np.name)}
                            className="hover-lift flex w-full items-center gap-3 rounded-xl border border-border-light bg-surface-secondary dark:bg-slate-800/40 p-3 text-left transition-colors hover:border-brand-300 dark:hover:border-brand-700 hover:bg-brand-50/50 dark:hover:bg-brand-900/20"
                          >
                            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-50 dark:bg-accent-900/30">
                              <MapPin size={15} className="text-accent-500" />
                            </span>
                            <div className="min-w-0 flex-1">
                              <p className="line-clamp-1 text-sm font-medium text-slate-800 dark:text-slate-200">
                                {np.name}
                              </p>
                              <p className="line-clamp-1 text-xs text-slate-400 dark:text-slate-500">
                                {np.address || np.tags.join(' · ')}
                              </p>
                            </div>
                            <div className="flex shrink-0 items-center gap-1.5">
                              <span className="rounded bg-accent-50 dark:bg-accent-900/30 px-1.5 py-0.5 text-[10px] font-medium text-accent-600 dark:text-accent-400">
                                {np.price_level}
                              </span>
                              <ChevronRight size={15} className="text-slate-300 dark:text-slate-600" />
                            </div>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <p className="py-6 text-center text-sm text-slate-400 dark:text-slate-500">
                        暂无周边推荐
                      </p>
                    )}
                  </div>
                </div>

                {/* ── 底部：追问对话区 ── */}
                <div className="card flex flex-col overflow-hidden">
                  {/* 对话区头部 */}
                  <div className="flex items-center gap-2 border-b border-border-light px-4 py-3">
                    <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-brand-100 to-accent-100 dark:from-slate-700 dark:to-slate-800">
                      <Bot size={16} className="text-brand-500" />
                    </span>
                    <div className="flex-1">
                      <p className="text-sm font-bold text-slate-800 dark:text-slate-200">
                        向 AI 导游追问
                      </p>
                      <p className="text-[11px] text-slate-400 dark:text-slate-500">
                        关于{selectedPoi}的任何问题，尽管问
                      </p>
                    </div>
                  </div>

                  {/* 消息列表 */}
                  <div
                    ref={chatScrollRef}
                    className="max-h-80 min-h-[160px] space-y-4 overflow-y-auto px-4 py-4"
                  >
                    {chatMessages.length === 0 && !chatLoading && (
                      <div className="flex flex-col items-center justify-center py-6 text-center">
                        <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-brand-100 to-accent-100 dark:from-slate-700 dark:to-slate-800">
                          <Bot size={20} className="text-brand-500" />
                        </div>
                        <p className="mb-1 text-sm font-medium text-slate-600 dark:text-slate-400">
                          有什么想深入了解的？
                        </p>
                        <p className="mb-3 text-xs text-slate-400 dark:text-slate-500">
                          比如：最佳拍照位置、游览路线、注意事项
                        </p>
                        {/* 快捷追问 */}
                        <div className="flex flex-wrap justify-center gap-2">
                          {[
                            '推荐最佳游览路线',
                            '有什么注意事项？',
                            '附近有什么美食？',
                          ].map((q) => (
                            <button
                              key={q}
                              onClick={() => setChatInput(q)}
                              className="rounded-full border border-brand-200 dark:border-brand-800 bg-brand-50 dark:bg-brand-900/30 px-3 py-1.5 text-xs font-medium text-brand-700 dark:text-brand-300 transition-all hover:bg-brand-100 dark:hover:bg-brand-900/50"
                            >
                              {q}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {chatMessages.map((msg) => (
                      <ChatBubble key={msg.id} msg={msg} />
                    ))}

                    {/* 加载指示器 */}
                    {chatLoading && (
                      <div className="flex gap-2.5">
                        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-accent-100 to-brand-100 dark:from-slate-700 dark:to-slate-800">
                          <Bot size={14} className="text-brand-500" />
                        </div>
                        <div className="glass flex items-center gap-1 rounded-2xl rounded-tl-sm border border-border-light px-4 py-3 shadow-card">
                          <span className="h-2 w-2 animate-bounce rounded-full bg-brand-400 [animation-delay:0ms]" />
                          <span className="h-2 w-2 animate-bounce rounded-full bg-brand-400 [animation-delay:150ms]" />
                          <span className="h-2 w-2 animate-bounce rounded-full bg-brand-400 [animation-delay:300ms]" />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* 输入框 */}
                  <form
                    onSubmit={handleSendChat}
                    className="flex items-end gap-2 border-t border-border-light px-3 py-3"
                  >
                    <textarea
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      onKeyDown={handleChatKeyDown}
                      disabled={chatLoading}
                      rows={1}
                      placeholder="向导游提问... (Enter 发送 / Shift+Enter 换行)"
                      className="max-h-32 flex-1 resize-none rounded-2xl border border-border bg-surface-secondary dark:bg-slate-800/60 px-4 py-2.5 text-sm text-slate-800 dark:text-slate-200 placeholder:text-slate-400 dark:placeholder:text-slate-500 transition-all focus:border-brand-400 dark:focus:border-brand-500 focus:bg-white dark:focus:bg-slate-900 focus:outline-none focus:ring-2 focus:ring-brand-100 dark:focus:ring-brand-900/40 disabled:opacity-50"
                      aria-label="向导游提问"
                    />
                    <button
                      type="submit"
                      disabled={chatLoading || !chatInput.trim()}
                      aria-label="发送"
                      className="btn-primary shrink-0 rounded-2xl p-2.5"
                    >
                      {chatLoading ? (
                        <Loader2 size={18} className="animate-spin" />
                      ) : (
                        <Send size={18} />
                      )}
                    </button>
                  </form>
                </div>
              </>
            )}
          </div>
        )}
      </main>
    </div>
  )
}

// ── 工具函数 ─────────────────────────────────────────────

/** 格式化价格显示 */
function formatPrice(narration: GuideNarration): string {
  const range = narration.poi?.price_range ?? narration.practical.price_range
  if (range && (range.min > 0 || range.max > 0)) {
    if (range.min === range.max) return `¥${range.min}`
    return `¥${range.min} - ${range.max}`
  }
  return narration.practical.price_level || narration.poi?.price_level || '免费'
}
