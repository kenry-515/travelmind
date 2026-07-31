/**
 * TravelMind Agent — ItineraryPage
 *
 * Renders contract-valid itineraries (docs/itinerary.schema.json).
 * No content-generation logic — pure rendering + data-fetching.
 *
 * Blocks: 概览统计条 / 每天一栏 / 预算进度条 / 可打勾行前清单 / tips chips
 * Extras: weather widget, per-day partial regeneration,
 *         friendly empty state when opened without ?q / stored itinerary.
 */

import { useState, useEffect, useMemo } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import {
  ArrowLeft,
  FileDown,
  Heart,
  History,
  List,
  Loader2,
  AlertCircle,
  Sun,
  Lightbulb,
  RotateCcw,
  Wallet,
  ClipboardCheck,
  Check,
  RefreshCw,
  X,
  Map,
  MoreHorizontal,
  Umbrella,
  Share2,
} from 'lucide-react'
import {
  fetchItineraryDetail,
  fetchWeather,
  regenerateDay,
  addFavorite,
  removeFavorite,
  fetchFavorites,
  fetchVersions,
  restoreVersion,
  removeItineraryItem,
  type TravelItinerary,
  type WeatherForecast,
  type VersionSummary,
  type PriceSummary,
} from '../lib/api'
import { toast } from '../components/Toast'
import { ValidationReportCard } from '../components/ValidationReportCard'
import { DayCard } from '../components/DayCard'
import { PriceSummaryCard } from '../components/PriceBadge'
import { SkeletonItinerary } from '../components/Skeleton'
import { usePlanStream, type StreamState } from '../hooks/usePlanStream'
import { ShareModal } from '../components/ShareModal'

// ── Helpers ───────────────────────────────────────────────

const dayIcons: Record<string, string> = {
  老城: '🏙️', 历史: '🏛️', 文化: '🏛️', 自然: '🏔️', 美食: '🍜',
  休闲: '🏖️', 亲子: '🎠', 文艺: '🎨', 探险: '🧗', 海: '🌊',
  古镇: '🏘️', 夜: '🌃',
}

function getDayIcon(theme: string): string {
  for (const [key, emoji] of Object.entries(dayIcons)) {
    if (theme.includes(key)) return emoji
  }
  return '📍'
}

// ── Loading: Progress Stepper ─────────────────────────────

function LoadingView({ state }: { state: Extract<StreamState, { stage: 'loading' }> }) {
  return (
    <div className="mt-16 mx-auto max-w-sm">
      <div className="text-center mb-8">
        <Loader2 size={40} className="mx-auto mb-4 animate-spin text-brand-500" />
        <p className="text-slate-500 dark:text-slate-400">{state.message}</p>
        <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">完整规划约需 30-60 秒</p>
      </div>
      {/* Step progress */}
      <div className="space-y-1">
        {state.progress.map((step) => (
          <div key={step.step} className="flex items-center gap-3 px-4 py-2">
            <span
              className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold transition-colors ${
                step.status === 'done'
                  ? 'bg-green-500 text-white dark:bg-green-500'
                  : step.status === 'running'
                  ? 'bg-brand-500 text-white dark:bg-brand-500 animate-pulse'
                  : 'bg-slate-200 dark:bg-slate-700 text-slate-400 dark:text-slate-500'
              }`}
            >
              {step.status === 'done' ? <Check size={10} /> : '·'}
            </span>
            <span
              className={`text-xs transition-colors ${
                step.status === 'done'
                  ? 'text-green-600 font-medium'
                  : step.status === 'running'
                  ? 'text-brand-600 font-medium'
                  : 'text-slate-400 dark:text-slate-500'
              }`}
            >
              {step.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Error ─────────────────────────────────────────────────

function ErrorView({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="mt-12 text-center">
      <AlertCircle size={40} className="mx-auto mb-3 text-red-500" />
      <p className="text-slate-600 dark:text-slate-400">{message}</p>
      <div className="mt-4 flex items-center justify-center gap-3">
        {onRetry && (
          <button
            onClick={onRetry}
            className="btn-primary inline-flex items-center gap-1.5 px-4 py-2 text-sm"
          >
            <RefreshCw size={14} />
            重试
          </button>
        )}
        <Link
          to="/recommend"
          className="text-sm font-medium text-brand-600 hover:underline"
        >
          返回推荐页
        </Link>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────

export function ItineraryPage() {
  const [searchParams] = useSearchParams()
  const query = searchParams.get('q') || ''

  // Stream hook for SSE-based pipeline
  const { state, start, setState } = usePlanStream()

  // Local state: initialized in useEffect (SSR-safe — no sessionStorage/window access during render)
  const [localReady, setLocalReady] = useState<Extract<StreamState, { stage: 'ready' }> | null>(null)
  const [localReadyInit, setLocalReadyInit] = useState(false)

  // Initialize localReady on client-side only (sessionStorage)
  useEffect(() => {
    if (localReadyInit || query) return
    setLocalReadyInit(true)
    try {
      const raw = sessionStorage.getItem('travelmind_itinerary')
      if (raw) {
        const stored = JSON.parse(raw) as TravelItinerary
        setLocalReady({ stage: 'ready', itinerary: stored, weather: null, error: null, preview: false, itineraryId: null })
        return
      }
    } catch { /* fall through */ }
    const idParam = searchParams.get('id')
    if (idParam) return // will be loaded by loadItineraryById effect
    // No fixture fallback — show empty state instead
  }, [query, localReadyInit, searchParams])

  const [weather, setWeather] = useState<WeatherForecast | null>(null)
  const [checked, setChecked] = useState<boolean[]>([])
  const [regenIndex, setRegenIndex] = useState<number | null>(null)
  const [regenText, setRegenText] = useState('')
  const [regenBusy, setRegenBusy] = useState(false)
  const [favorited, setFavorited] = useState(false)
  const [favoriteId, setFavoriteId] = useState<string | null>(null)
  const [favBusy, setFavBusy] = useState(false)
  const [versionPanelOpen, setVersionPanelOpen] = useState(false)
  const [versions, setVersions] = useState<VersionSummary[]>([])
  const [versionsLoading, setVersionsLoading] = useState(false)
  const [restoreBusy, setRestoreBusy] = useState<string | null>(null)
  const [pdfExporting, setPdfExporting] = useState(false)
  const [hasRun, setHasRun] = useState(false)
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [shareModalOpen, setShareModalOpen] = useState(false)
  // Phase 16.4: 拖放高亮状态（替代旧的 DOM style 操作）
  const [dragOverDay, setDragOverDay] = useState<number | null>(null)

  // Derive the effective itinerary — from SSE stream or local
  const effectiveState: StreamState | null = state ?? localReady

  // ── Side effects ────────────────────────────────────────

  // Kick off SSE pipeline when ?q is present
  useEffect(() => {
    if (!query || hasRun) return
    setHasRun(true)
    start(query)
  }, [query, hasRun, start])

  // Load itinerary by ID (from /history page)
  const idParam = searchParams.get('id')
  useEffect(() => {
    if (!idParam || query || hasRun) return
    setHasRun(true)
    loadItineraryById(idParam)
  }, [idParam, query, hasRun])

  // Fetch weather once we have a ready itinerary (non-preview, no weather yet)
  useEffect(() => {
    const ready = effectiveState
    if (!ready || ready.stage !== 'ready' || ready.preview) return
    if (weather) return
    const city = ready.itinerary.trip.city
    if (!city) return
    let cancelled = false
    fetchWeather(city, ready.itinerary.trip.daysCount)
      .then((w) => { if (!cancelled) setWeather(w) })
      .catch(() => { console.warn('Weather fetch failed — weather widget hidden'); })
    return () => { cancelled = true }
  }, [effectiveState, weather])

  // Reset checklist when itinerary changes
  useEffect(() => {
    const ready = effectiveState
    if (ready?.stage === 'ready') {
      setChecked(ready.itinerary.checklist.map(() => false))
    }
  }, [effectiveState])

  // Show save notification when itinerary is auto-saved by backend
  useEffect(() => {
    const ready = effectiveState
    if (ready?.stage === 'ready' && ready.itineraryId && !ready.preview) {
      const shownKey = `saved-notif-${ready.itineraryId}`
      if (!sessionStorage.getItem(shownKey)) {
        toast.success('行程已自动保存到「我的行程」', { duration: 4000 })
        sessionStorage.setItem(shownKey, '1')
      }
    }
  }, [effectiveState])

  // Check favorite status (works for both DB-saved and stream-generated itineraries)
  useEffect(() => {
    const ready = effectiveState
    if (!ready || ready.stage !== 'ready' || ready.preview) return

    // Use DB id if available (from URL param or SSE stream auto-save)
    const itineraryId = searchParams.get('id') || ready.itineraryId || null
    if (!itineraryId) return

    fetchFavorites('itinerary')
      .then((res) => {
        const fav = res.favorites.find(
          (f) => f.target_type === 'itinerary' && f.target_id === itineraryId
        )
        if (fav) { setFavorited(true); setFavoriteId(fav.id) }
      })
      .catch(() => { /* non-critical */ })
  }, [effectiveState, searchParams.get('id')])

  // ── Actions ─────────────────────────────────────────────

  async function loadItineraryById(id: string) {
    try {
      const detail = await fetchItineraryDetail(id)
      setLocalReady({
        stage: 'ready',
        itinerary: detail.plan,
        weather: null,
        error: null,
        preview: false,
        itineraryId: id,
      })
    } catch {
      setLocalReady(null)
    }
  }

  async function toggleFavorite() {
    const ready = effectiveState
    if (ready?.stage !== 'ready' || favBusy) return
    setFavBusy(true)
    try {
      if (favorited && favoriteId) {
        await removeFavorite(favoriteId)
        setFavorited(false); setFavoriteId(null)
        toast.success('已取消收藏')
      } else {
        // Use DB id (from URL param or SSE save), fallback to title
        const itineraryId = searchParams.get('id') || ready.itineraryId || null
        const targetId = itineraryId || ready.itinerary.trip.title
        const res = await addFavorite('itinerary', targetId)
        if (res.ok) {
          // setFavorited even if the backend didn't return a favorite object
          // (idempotent case — desired state already achieved)
          setFavorited(true)
          if (res.favorite) {
            setFavoriteId(res.favorite.id)
          }
          toast.success('已收藏')
        }
      }
    } catch { toast.error('收藏操作失败') }
    finally { setFavBusy(false) }
  }

  async function loadVersions() {
    const itineraryId = searchParams.get('id')
    if (!itineraryId) return
    setVersionsLoading(true)
    try { setVersions(await fetchVersions(itineraryId)) }
    catch { setVersions([]) }
    finally { setVersionsLoading(false) }
  }

  async function handleRestore(versionId: string, versionNum: number) {
    const itineraryId = searchParams.get('id')
    const ready = effectiveState
    if (!itineraryId || ready?.stage !== 'ready') return
    if (!confirm(`确定要恢复到版本 V${versionNum} 吗？当前行程将被保留为新版本。`)) return
    setRestoreBusy(versionId)
    try {
      const result = await restoreVersion(itineraryId, versionId)
      setLocalReady((prev) =>
        prev?.stage === 'ready' ? { ...prev, itinerary: result.itinerary, preview: false } : prev
      )
      toast.success(`已恢复到版本 V${versionNum}`)
      setVersionPanelOpen(false)
      loadVersions()
    } catch { toast.error('恢复版本失败，请稍后重试。') }
    finally { setRestoreBusy(null) }
  }

  async function handleRegen(dayIndex: number) {
    const ready = effectiveState
    if (ready?.stage !== 'ready' || !regenText.trim() || regenBusy) return
    setRegenBusy(true)
    try {
      const updated = await regenerateDay({
        itinerary: ready.itinerary, dayIndex,
        feedback: regenText.trim(), userInput: query || undefined,
      })
      if (state) {
        setState((prev) => prev?.stage === 'ready' ? { ...prev, itinerary: updated } : prev)
      } else {
        setLocalReady((prev) => prev?.stage === 'ready' ? { ...prev, itinerary: updated } : prev)
      }
      setRegenIndex(null); setRegenText('')
      toast.success(`第 ${dayIndex + 1} 天已重新安排`)
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : '重生成失败，请稍后再试')
    } finally { setRegenBusy(false) }
  }

  // ── Derived values ──────────────────────────────────────

  // Phase 16: 单项删除（本地即时生效 + 后端持久化 + 重算地点数 + 写回 sessionStorage）
  async function handleRemoveItem(dayIndex: number, itemIndex: number) {
    const ready = effectiveState
    if (ready?.stage !== 'ready') return
    const day = ready.itinerary.days[dayIndex]
    if (!day) return
    if (day.items.length <= 1) {
      toast.error('这一天只剩一个项目了，不能再删～试试「重新安排」这一天')
      return
    }
    const removed = day.items[itemIndex]
    if (!removed) return

    // 本地即时更新（乐观更新）
    const updated: TravelItinerary = {
      ...ready.itinerary,
      days: ready.itinerary.days.map((d, i) =>
        i === dayIndex ? { ...d, items: d.items.filter((_, j) => j !== itemIndex) } : d
      ) as TravelItinerary['days'],
    }
    const visitCount = updated.days.reduce(
      (n, d) => n + d.items.filter((it) => !/餐|休息|入住|返程|酒店/.test(it.poi)).length,
      0
    )
    updated.trip = {
      ...updated.trip,
      stats: updated.trip.stats.map((s) =>
        /地点/.test(s.label) ? { ...s, value: `${visitCount} 个` } : s
      ) as typeof updated.trip.stats,
    }
    if (state) {
      setState((prev) => (prev?.stage === 'ready' ? { ...prev, itinerary: updated } : prev))
    } else {
      setLocalReady((prev) => (prev?.stage === 'ready' ? { ...prev, itinerary: updated } : prev))
    }
    try {
      sessionStorage.setItem('travelmind_itinerary', JSON.stringify(updated))
    } catch { /* non-fatal */ }
    toast.success(`已去掉「${removed.poi}」`)

    // Phase 16: 后端持久化（如果行程有 ID）
    const itineraryId = searchParams.get('id') || ready.itineraryId || null
    if (itineraryId) {
      try {
        await removeItineraryItem(itineraryId, dayIndex, itemIndex)
      } catch (err) {
        // 非致命错误：后端保存失败不影响前端展示
        console.warn('Failed to persist item removal to backend:', err)
      }
    }
  }

  // Phase 14: 项目上移/下移
  function handleMoveItem(dayIndex: number, itemIndex: number, direction: 'up' | 'down') {
    const ready = effectiveState
    if (ready?.stage !== 'ready') return
    const day = ready.itinerary.days[dayIndex]
    if (!day || day.items.length < 2) return
    const targetIndex = direction === 'up' ? itemIndex - 1 : itemIndex + 1
    if (targetIndex < 0 || targetIndex >= day.items.length) return
    const items = [...day.items]
    ;[items[itemIndex], items[targetIndex]] = [items[targetIndex], items[itemIndex]]
    const updated: TravelItinerary = {
      ...ready.itinerary,
      days: ready.itinerary.days.map((d, i) => (i === dayIndex ? { ...d, items } : d)) as TravelItinerary['days'],
    }
    if (state) setState((prev) => (prev?.stage === 'ready' ? { ...prev, itinerary: updated } : prev))
    else setLocalReady((prev) => (prev?.stage === 'ready' ? { ...prev, itinerary: updated } : prev))
    try { sessionStorage.setItem('travelmind_itinerary', JSON.stringify(updated)) } catch { /* */ }
  }

  // Phase 14: 编辑项目名称
  function handleEditItem(dayIndex: number, itemIndex: number, newName: string) {
    const ready = effectiveState
    if (ready?.stage !== 'ready') return
    const updated: TravelItinerary = {
      ...ready.itinerary,
      days: ready.itinerary.days.map((d, i) =>
        i === dayIndex
          ? { ...d, items: d.items.map((item, j) => (j === itemIndex ? { ...item, poi: newName } : item)) }
          : d
      ) as TravelItinerary['days'],
    }
    if (state) setState((prev) => (prev?.stage === 'ready' ? { ...prev, itinerary: updated } : prev))
    else setLocalReady((prev) => (prev?.stage === 'ready' ? { ...prev, itinerary: updated } : prev))
    try { sessionStorage.setItem('travelmind_itinerary', JSON.stringify(updated)) } catch { /* */ }
    toast.success('已更新')
  }

  // Pre-compute max version number (avoid O(n²) in render)
  const maxVersionNum = useMemo(
    () => (versions.length > 0 ? Math.max(...versions.map((v) => v.version_number)) : 0),
    [versions]
  )

  const ready = effectiveState?.stage === 'ready' ? effectiveState : null

  // ── Render ──────────────────────────────────────────────

  return (
    <div className="relative min-h-screen overflow-hidden bg-surface-secondary">
      {/* 弱化极光背景（Phase 12.24） */}
      <div aria-hidden className="aurora aurora-soft">
        <span /><span /><span />
      </div>
      {/* Header */}
      <header className="glass sticky top-0 z-10 border-b border-border-light">
        <div className="mx-auto flex max-w-4xl items-center gap-2 px-3 py-2.5 sm:gap-3 sm:px-4 sm:py-3">
          <Link to="/recommend" className="rounded-xl p-1.5 text-slate-500 dark:text-slate-400 transition-colors hover:bg-brand-50 dark:hover:bg-brand-900/30 hover:text-brand-600 dark:hover:text-brand-400" aria-label="返回推荐">
            <ArrowLeft size={20} />
          </Link>
          <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200">行程规划</h2>
          {ready && (
            <span className="hidden text-xs text-slate-400 dark:text-slate-500 sm:inline">
              {ready.itinerary.trip.daysCount} 天行程
            </span>
          )}
          <div className="flex-1" />

          {/* Desktop actions — visible sm+ */}
          <div className="hidden items-center gap-1 sm:flex">
            <Link to="/history" className="flex items-center gap-1 rounded-xl px-2 py-1.5 text-xs text-slate-400 dark:text-slate-500 transition-colors hover:bg-brand-50 dark:hover:bg-brand-900/30 hover:text-brand-600 dark:hover:text-brand-400" aria-label="我的行程">
              <List size={14} /> 我的行程
            </Link>
            {ready && !ready.preview && searchParams.get('id') && (
              <button onClick={() => { setVersionPanelOpen(true); loadVersions() }} className="flex items-center gap-1 rounded-xl px-2 py-1.5 text-xs text-slate-400 dark:text-slate-500 transition-colors hover:bg-brand-50 dark:hover:bg-brand-900/30 hover:text-brand-600 dark:hover:text-brand-400" aria-label="版本历史">
                <History size={14} /> 历史
              </button>
            )}
            {ready && !ready.preview && (
              <button
                onClick={async () => {
                  if (pdfExporting) return; setPdfExporting(true)
                  try {
                    const { exportItineraryPdf } = await import('../lib/exportPdf')
                    await exportItineraryPdf(ready.itinerary, weather)
                  }
                  catch (err) {
                    console.error('PDF export failed:', err)
                    toast.error('PDF 导出失败，请稍后重试。')
                  }
                  finally { setPdfExporting(false) }
                }}
                disabled={pdfExporting}
                className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-slate-400 dark:text-slate-500 transition-colors hover:bg-slate-100 dark:bg-slate-800 hover:text-green-500 disabled:opacity-50"
                aria-label="导出 PDF"
              >
                {pdfExporting ? <Loader2 size={14} className="animate-spin" /> : <FileDown size={14} />}
                PDF
              </button>
            )}
            {ready && !ready.preview && (
              <button
                onClick={toggleFavorite} disabled={favBusy}
                className={`flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs transition-colors ${
                  favorited ? 'text-red-500 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30' : 'text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:bg-slate-800 hover:text-red-400'
                }`}
                aria-label={favorited ? '取消收藏' : '收藏行程'}
              >
                <Heart size={14} className={favorited ? 'fill-current' : ''} />
                {favorited ? '已收藏' : '收藏'}
              </button>
            )}
            {ready && !ready.preview && (
              <button
                onClick={() => setShareModalOpen(true)}
                className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-slate-400 dark:text-slate-500 transition-colors hover:bg-brand-50 dark:hover:bg-brand-900/30 hover:text-brand-600 dark:hover:text-brand-400"
                aria-label="分享行程"
              >
                <Share2 size={14} />
                分享
              </button>
            )}
          </div>

          {/* Mobile "More" menu — visible below sm */}
          {ready && !ready.preview && (
            <div className="relative sm:hidden">
              <button
                      onClick={() => setMobileMenuOpen((v) => !v)}
                      className="rounded-lg p-1.5 text-slate-500 dark:text-slate-400 transition-colors hover:bg-slate-100 dark:hover:bg-slate-800"
                      aria-label="更多操作"
                    >
                <MoreHorizontal size={18} />
              </button>
              {mobileMenuOpen && (
                <>
                  <div className="fixed inset-0 z-20" onClick={() => setMobileMenuOpen(false)} />
                  <div className="absolute right-0 top-full z-30 mt-1 w-40 animate-fade-in rounded-2xl border border-border bg-white dark:bg-slate-900 py-1 shadow-lg">
                    <Link to="/history" onClick={() => setMobileMenuOpen(false)} className="flex items-center gap-2 px-4 py-2.5 text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800">
                      <List size={16} /> 我的行程
                    </Link>
                    {searchParams.get('id') && (
                      <button onClick={() => { setVersionPanelOpen(true); setMobileMenuOpen(false); loadVersions() }} className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800">
                        <History size={16} /> 版本历史
                      </button>
                    )}
                    <button
                      onClick={async () => {
                        setMobileMenuOpen(false)
                        if (pdfExporting) return; setPdfExporting(true)
                        try {
                          const { exportItineraryPdf } = await import('../lib/exportPdf')
                          await exportItineraryPdf(ready.itinerary, weather)
                        }
                        catch (err) { toast.error('PDF 导出失败，请稍后重试。') }
                        finally { setPdfExporting(false) }
                      }}
                      disabled={pdfExporting}
                      className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
                    >
                      <FileDown size={16} /> 导出 PDF
                    </button>
                    <button
                      onClick={() => { toggleFavorite(); setMobileMenuOpen(false) }}
                      disabled={favBusy}
                      className={`flex w-full items-center gap-2 px-4 py-2.5 text-sm hover:bg-slate-50 dark:hover:bg-slate-800 ${favorited ? 'text-red-500 dark:text-red-400' : 'text-slate-600 dark:text-slate-400'}`}
                    >
                      <Heart size={16} className={favorited ? 'fill-current' : ''} />
                      {favorited ? '取消收藏' : '收藏'}
                    </button>
                    <button
                      onClick={() => { setShareModalOpen(true); setMobileMenuOpen(false) }}
                      className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-800"
                    >
                      <Share2 size={16} /> 分享
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </header>

      <main className="relative mx-auto max-w-4xl px-4 py-6 pb-20 sm:pb-6">
        {/* Loading */}
        {effectiveState?.stage === 'loading' && (
          <>
            <LoadingView state={effectiveState} />
            <div className="mt-8 hidden sm:block">
              <SkeletonItinerary />
            </div>
          </>
        )}

        {/* Error */}
        {effectiveState?.stage === 'error' && (
          <ErrorView
            message={effectiveState.message}
            onRetry={query ? () => { setHasRun(false); setTimeout(() => start(query), 0) } : undefined}
          />
        )}

        {/* Empty — no itinerary, no query, no id */}
        {!effectiveState && (
          <div className="mt-16 text-center animate-fade-in-up">
            <div className="mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-3xl bg-gradient-to-br from-brand-100 to-accent-100 dark:from-slate-800 dark:to-slate-700 animate-float-slow">
              <Map size={36} className="text-brand-500" />
            </div>
            <p className="mb-2 font-semibold text-slate-600 dark:text-slate-400">尚未生成行程</p>
            <p className="mb-6 text-sm leading-relaxed text-slate-400 dark:text-slate-500">
              通过 AI 对话或智能推荐，一句话即可生成你的专属旅行计划。
            </p>
            <div className="flex items-center justify-center gap-3">
              <Link to="/chat" className="btn-primary px-4 py-2 text-sm">
                AI 对话规划
              </Link>
              <Link to="/recommend" className="btn-secondary px-4 py-2 text-sm">
                智能推荐
              </Link>
            </div>
          </div>
        )}

        {/* Ready */}
        {ready && (
          <>
            {/* ── 概览统计条 ── */}
            <div className="card mb-6 p-5">
              <h3 className="text-lg font-extrabold text-slate-900 dark:text-slate-100">{ready.itinerary.trip.title}</h3>
              <p className="mt-0.5 text-xs text-slate-400 dark:text-slate-500">
                {ready.itinerary.trip.city} · {ready.itinerary.trip.dateStart} — {ready.itinerary.trip.dateEnd}
              </p>
              <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {ready.itinerary.trip.stats.map((s, i) => (
                  <div key={i} className="rounded-xl bg-surface-secondary px-3 py-2 text-center">
                    <p className="text-base font-bold text-slate-800 dark:text-slate-200">{s.value}</p>
                    <p className="text-xs text-slate-400 dark:text-slate-500">{s.label}</p>
                  </div>
                ))}
              </div>
              {weather && (
                <div className="mt-4 rounded-2xl border border-accent-100 dark:border-slate-700 bg-accent-50 dark:bg-slate-800/50 p-3">
                  <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-accent-700 dark:text-teal-400">
                    <Sun size={16} /> 天气参考
                    <span className="text-xs font-normal text-accent-600 dark:text-teal-500">({weather.city})</span>
                    {/* 天气安全徽章：有降雨/降雪时提示室内安排 */}
                    {weather.daily.some((d) => /雨|雪|雷/.test(d.weather_desc) || d.precipitation >= 5) ? (
                      <span className="inline-flex items-center gap-1 rounded-full border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/30 px-2.5 py-0.5 text-xs font-semibold text-amber-700 dark:text-amber-300">
                        <Umbrella size={12} />
                        天气安全 · 有降雨，建议安排室内项目
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded-full border border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/30 px-2.5 py-0.5 text-xs font-semibold text-green-700 dark:text-green-300">
                        <Sun size={12} />
                        天气安全 · 整体适宜出行
                      </span>
                    )}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {weather.daily.slice(0, 5).map((d) => (
                      <div key={d.date} className="rounded-xl bg-white dark:bg-slate-900/80 px-3 py-1.5 text-center text-xs shadow-sm">
                        <p className="font-medium text-slate-700 dark:text-slate-300">{d.date.slice(5)}</p>
                        <p className="text-slate-500 dark:text-slate-400">{d.weather_desc}</p>
                        <p className="tabular-nums text-slate-400 dark:text-slate-500">{d.temp_min.toFixed(0)}~{d.temp_max.toFixed(0)}°C</p>
                      </div>
                    ))}
                  </div>
                  <p className="mt-2 text-xs text-accent-700 dark:text-slate-400">{weather.advice}</p>
                </div>
              )}
              {ready.error && (
                <div className="mt-3 rounded-lg bg-amber-50 dark:bg-amber-900/30 px-3 py-2 text-xs text-amber-700 dark:text-amber-400">
                  <AlertCircle size={14} className="mr-1 inline" />
                  {ready.error}
                </div>
              )}
            </div>

            {/* ── 校验报告卡片 ── */}
            {ready.itinerary.validation_report && (
              <ValidationReportCard report={ready.itinerary.validation_report} />
            )}

            {/* ── 每天一栏（带侧边栏拖拽投放）─ */}
            <div className="space-y-6">
              {ready.itinerary.days.map((day, dayIndex) => (
                <div
                  key={`drop-${day.day}-${dayIndex}`}
                  className="relative"
                  onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = 'copy' }}
                  onDrop={(e) => {
                    e.preventDefault()
                    try {
                      const data = JSON.parse(e.dataTransfer.getData('text/plain'))
                      if (data && data.name) {
                        const updated: TravelItinerary = {
                          ...ready.itinerary,
                          days: ready.itinerary.days.map((d, i) =>
                            i === dayIndex ? { ...d, items: [...d.items, { poi: data.name, time: '自由安排', note: `[景] ${data.city}景点` }] } : d
                          ) as TravelItinerary['days'],
                        }
                        if (state) setState((prev) => (prev?.stage === 'ready' ? { ...prev, itinerary: updated } : prev))
                        else setLocalReady((prev) => (prev?.stage === 'ready' ? { ...prev, itinerary: updated } : prev))
                        try { sessionStorage.setItem('travelmind_itinerary', JSON.stringify(updated)) } catch { /* */ }
                        toast.success(`已添加「${data.name}」到第 ${dayIndex + 1} 天`)
                      }
                    } catch { /* */ }
                  }}
                >
                  <DayCard
                    key={`${day.day}-${dayIndex}`}
                    day={day}
                    icon={getDayIcon(day.theme)}
                    regenOpen={regenIndex === dayIndex}
                    regenBusy={regenBusy}
                    regenText={regenIndex === dayIndex ? regenText : ''}
                    onRegenOpen={() => { setRegenIndex(dayIndex); setRegenText('') }}
                    onRegenClose={() => setRegenIndex(null)}
                    onRegenText={setRegenText}
                    onRegenSubmit={() => handleRegen(dayIndex)}
                    onRemoveItem={(itemIndex) => handleRemoveItem(dayIndex, itemIndex)}
                    onMoveItem={(itemIndex, dir) => handleMoveItem(dayIndex, itemIndex, dir)}
                    onEditItem={(itemIndex, newName) => handleEditItem(dayIndex, itemIndex, newName)}
                    totalItems={day.items.length}
                  />
                  {/* Drop zone indicator — Phase 16.4: React 状态管理替代 DOM style 操作 */}
                  <div
                    className={`mt-2 h-10 rounded-xl border-2 border-dashed text-xs transition-all ${
                      dragOverDay === dayIndex
                        ? 'border-indigo-400 text-indigo-400'
                        : 'border-transparent text-transparent'
                    }`}
                    onDragOver={(e) => { e.preventDefault(); setDragOverDay(dayIndex) }}
                    onDragLeave={() => setDragOverDay(null)}
                    onDrop={(e) => {
                      e.preventDefault(); e.stopPropagation()
                      setDragOverDay(null)
                      try {
                        const data = JSON.parse(e.dataTransfer.getData('text/plain'))
                        if (data && data.name) {
                          const updated: TravelItinerary = {
                            ...ready.itinerary,
                            days: ready.itinerary.days.map((d, i) =>
                              i === dayIndex ? { ...d, items: [...d.items, { poi: data.name, time: '自由安排', note: `[景] ${data.city}景点` }] } : d
                            ) as TravelItinerary['days'],
                          }
                          if (state) setState((prev) => (prev?.stage === 'ready' ? { ...prev, itinerary: updated } : prev))
                          else setLocalReady((prev) => (prev?.stage === 'ready' ? { ...prev, itinerary: updated } : prev))
                          try { sessionStorage.setItem('travelmind_itinerary', JSON.stringify(updated)) } catch { /* */ }
                          toast.success(`已添加「${data.name}」`)
                        }
                      } catch { /* */ }
                    }}
                  >
                    {dragOverDay === dayIndex && '📥 松开添加到此天'}
                  </div>
                </div>
              ))}
            </div>

            {/* ── 预算进度条 ── */}
            {ready.itinerary.budget.length > 0 && (
              <div className="card mt-6 p-5">
                <h3 className="flex items-center gap-2 text-sm font-bold text-slate-800 dark:text-slate-200">
                  <Wallet size={16} className="text-green-600" />
                  预算分配（人均）
                </h3>
                <div className="mt-3 space-y-3">
                  {ready.itinerary.budget.map((b) => (
                    <div key={b.label}>
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-medium text-slate-700 dark:text-slate-300">{b.label}</span>
                        <span className="tabular-nums text-slate-400 dark:text-slate-500">¥{b.amount} · {b.percent}%</span>
                      </div>
                      <div className="mt-1 h-2 overflow-hidden rounded-full bg-surface-tertiary">
                        <div className="h-full rounded-full bg-gradient-to-r from-green-400 to-green-600" style={{ width: `${Math.min(b.percent, 100)}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ── 价格参考卡片 ── */}
            {ready.itinerary.price_summary && (
              <PriceSummaryCard summary={ready.itinerary.price_summary as PriceSummary} />
            )}

            {/* ── 可打勾行前清单 ── */}
            {ready.itinerary.checklist.length > 0 && (
              <div className="card mt-6 p-5">
                <h3 className="flex items-center gap-2 text-sm font-bold text-slate-800 dark:text-slate-200">
                  <ClipboardCheck size={16} className="text-brand-500" />
                  行前清单
                  <span className="text-xs font-normal text-slate-400 dark:text-slate-500">
                    {checked.filter(Boolean).length}/{ready.itinerary.checklist.length}
                  </span>
                </h3>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {ready.itinerary.checklist.map((item, i) => (
                    <button
                      key={i}
                      onClick={() => setChecked((prev) => prev.map((v, j) => (j === i ? !v : v)))}
                      className={`flex items-start gap-2 rounded-xl border px-3 py-2 text-left text-sm transition-all ${
                        checked[i]
                          ? 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/20 text-slate-400 dark:text-slate-500 line-through'
                          : 'border-border bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 hover:border-brand-300 dark:hover:border-brand-700 hover:shadow-sm'
                      }`}
                    >
                      <span className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                        checked[i] ? 'border-green-500 bg-green-500 text-white' : 'border-slate-300 dark:border-slate-700'
                      }`}>
                        {checked[i] && <Check size={12} />}
                      </span>
                      {item.text}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* ── tips chips ── */}
            {ready.itinerary.tips.length > 0 && (
              <div className="mt-6 rounded-2xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/20 p-5">
                <h3 className="flex items-center gap-2 text-sm font-bold text-amber-800 dark:text-amber-300">
                  <Lightbulb size={16} />
                  实用提示
                </h3>
                <div className="mt-3 flex flex-wrap gap-2">
                  {ready.itinerary.tips.map((tip, i) => (
                    <span key={i} className="rounded-full bg-white dark:bg-slate-900 px-3 py-1.5 text-xs text-amber-700 dark:text-amber-400 shadow-sm">
                      {tip}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* ── 版本历史面板 ── */}
            {versionPanelOpen && (
              <div className="fixed inset-0 z-50 flex justify-end">
                <div className="absolute inset-0 bg-black/30" onClick={() => setVersionPanelOpen(false)} />
                <div className="relative z-10 flex h-full w-80 flex-col bg-white dark:bg-slate-900 shadow-xl">
                  <div className="flex items-center justify-between border-b border-border-light px-4 py-3">
                    <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">版本历史</h3>
                    <button type="button" onClick={() => setVersionPanelOpen(false)} className="rounded-lg p-1 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:bg-slate-800" aria-label="关闭">
                      <X size={16} />
                    </button>
                  </div>
                  <div className="flex-1 overflow-y-auto p-3">
                    {versionsLoading ? (
                      <div className="flex items-center justify-center py-8">
                        <Loader2 size={20} className="animate-spin text-brand-500" />
                      </div>
                    ) : versions.length === 0 ? (
                      <p className="py-8 text-center text-xs text-slate-400 dark:text-slate-500">暂无版本历史。生成行程或修改后自动保存。</p>
                    ) : (
                      <div className="space-y-2">
                        {versions.map((v) => (
                          <div
                            key={v.id}
                            className={`rounded-xl border p-3 ${
                              v.version_number === maxVersionNum ? 'border-brand-200 dark:border-brand-800 bg-brand-50 dark:bg-brand-900/30' : 'border-border bg-white dark:bg-slate-900'
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                                V{v.version_number}
                                {v.version_number === maxVersionNum && (
                                  <span className="ml-1.5 rounded bg-brand-600 dark:bg-brand-500 px-1 py-0.5 text-[10px] text-white">当前</span>
                                )}
                              </span>
                              <span className="text-[10px] text-slate-400 dark:text-slate-500">
                                {new Date(v.created_at).toLocaleDateString('zh-CN')}
                              </span>
                            </div>
                            {v.change_description && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{v.change_description}</p>}
                            {v.version_number !== maxVersionNum && (
                              <button
                                onClick={() => handleRestore(v.id, v.version_number)}
                                disabled={restoreBusy === v.id}
                                className="mt-2 flex w-full items-center justify-center gap-1 rounded-lg border border-slate-300 dark:border-slate-700 px-2 py-1.5 text-xs text-slate-600 dark:text-slate-400 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
                              >
                                {restoreBusy === v.id ? <Loader2 size={12} className="animate-spin" /> : <RotateCcw size={12} />}
                                恢复到此版本
                              </button>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Bottom actions */}
            <div className="mt-8 flex justify-center gap-4 pb-8">
              <Link to="/recommend" className="btn-secondary px-4 py-2 text-sm">
                返回推荐
              </Link>
              <Link to="/" className="btn-primary px-4 py-2 text-sm">
                规划新行程
              </Link>
            </div>
          </>
        )}
      </main>

      {/* Share Modal */}
      {ready && (
        <ShareModal
          isOpen={shareModalOpen}
          onClose={() => setShareModalOpen(false)}
          itineraryId={searchParams.get('id') || ready.itineraryId || ''}
          title={ready.itinerary.trip.title || '我的行程'}
        />
      )}
    </div>
  )
}
