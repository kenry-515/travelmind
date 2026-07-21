/**
 * TravelMind Agent — ItineraryPage
 *
 * PURE RENDERING layer for contract-valid itineraries
 * (docs/itinerary.schema.json). No content-generation logic here.
 *
 * Blocks: 概览统计条 / 每天一栏 / 预算进度条 / 可打勾行前清单 / tips chips
 * Extras: weather widget, per-day partial regeneration (局部重生成),
 *         fixture preview when opened without ?q (no model call).
 */

import { useState, useEffect, useRef } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import {
  ArrowLeft,
  Clock,
  Coffee,
  Loader2,
  AlertCircle,
  Sun,
  Lightbulb,
  RefreshCw,
  Wallet,
  ClipboardCheck,
  Check,
  MapPin,
} from 'lucide-react'
import {
  fetchPlan,
  fetchWeather,
  regenerateDay,
  type TravelItinerary,
  type TripDay,
  type WeatherForecast,
} from '../lib/api'
import { toast } from '../components/Toast'
import { ValidationReportCard } from '../components/ValidationReportCard'
import fixtureJson from '../../fixtures/itinerary.example.json'

const fixture = fixtureJson as TravelItinerary

type PageState =
  | { stage: 'loading'; message: string }
  | {
      stage: 'ready'
      itinerary: TravelItinerary
      weather: WeatherForecast | null
      error: string | null
      preview: boolean
    }
  | { stage: 'error'; message: string }

const LOADING_MESSAGES = [
  '正在提取用户画像...',
  '正在分析热门趋势...',
  '正在获取天气数据...',
  '正在检索知识库...',
  '正在评分和排序...',
  '正在生成行程规划...',
]

export function ItineraryPage() {
  const [searchParams] = useSearchParams()
  const query = searchParams.get('q') || ''
  const [state, setState] = useState<PageState>(() => {
    if (query) return { stage: 'loading', message: LOADING_MESSAGES[0] }
    // 对话式规划跳转：优先读 sessionStorage 中的行程 JSON
    try {
      const raw = sessionStorage.getItem('travelmind_itinerary')
      if (raw) {
        const stored = JSON.parse(raw) as TravelItinerary
        return { stage: 'ready', itinerary: stored, weather: null, error: null, preview: false }
      }
    } catch {
      // fall through to fixture preview
    }
    return { stage: 'ready', itinerary: fixture, weather: null, error: null, preview: true }
  })
  const [checked, setChecked] = useState<boolean[]>([])
  const [regenIndex, setRegenIndex] = useState<number | null>(null)
  const [regenText, setRegenText] = useState('')
  const [regenBusy, setRegenBusy] = useState(false)
  const hasRun = useRef(false)

  // Reset checklist ticks whenever the itinerary changes
  useEffect(() => {
    if (state.stage === 'ready') {
      setChecked(state.itinerary.checklist.map(() => false))
    }
  }, [state.stage === 'ready' ? state.itinerary : null])

  useEffect(() => {
    if (!query || hasRun.current) return
    hasRun.current = true
    runPipeline(query)
  }, [query])

  // 从对话页/存储打开的行程：补取天气（非预览才需要）
  useEffect(() => {
    if (state.stage !== 'ready' || state.weather || state.preview) return
    const city = state.itinerary.trip.city
    if (!city) return
    let cancelled = false
    fetchWeather(city, state.itinerary.trip.daysCount)
      .then((w) => {
        if (!cancelled && state.stage === 'ready') {
          setState({ ...state, weather: w })
        }
      })
      .catch(() => {
        // weather is non-critical
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.stage])

  async function runPipeline(userInput: string) {
    setState({ stage: 'loading', message: LOADING_MESSAGES[0] })
    const timer = setInterval(() => {
      setState((prev) => {
        if (prev.stage !== 'loading') return prev
        const cur = LOADING_MESSAGES.indexOf(prev.message)
        return { ...prev, message: LOADING_MESSAGES[(cur + 1) % LOADING_MESSAGES.length] }
      })
    }, 2500)

    try {
      const data = await fetchPlan(userInput)
      clearInterval(timer)

      if (!data.itinerary || !data.itinerary.days || data.itinerary.days.length === 0) {
        setState({
          stage: 'error',
          message: data.error || '行程生成失败，请稍后重试。',
        })
        return
      }

      let weather: WeatherForecast | null = null
      try {
        weather = await fetchWeather(data.itinerary.trip.city, data.itinerary.trip.daysCount)
      } catch {
        // weather is non-critical
      }

      setState({
        stage: 'ready',
        itinerary: data.itinerary,
        weather,
        error: data.error,
        preview: false,
      })
    } catch (err: unknown) {
      clearInterval(timer)
      const msg =
        err instanceof Error ? err.message : '行程规划服务暂不可用，请稍后重试。'
      setState({ stage: 'error', message: msg })
    }
  }

  async function handleRegen(dayIndex: number) {
    if (state.stage !== 'ready' || !regenText.trim() || regenBusy) return
    setRegenBusy(true)
    try {
      const updated = await regenerateDay({
        itinerary: state.itinerary,
        dayIndex,
        feedback: regenText.trim(),
        userInput: query || undefined,
      })
      setState({ ...state, itinerary: updated })
      setRegenIndex(null)
      setRegenText('')
      toast.success(`第 ${dayIndex + 1} 天已重新安排`)
    } catch (err: unknown) {
      toast.error(err instanceof Error ? err.message : '重生成失败，请稍后再试')
    } finally {
      setRegenBusy(false)
    }
  }

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

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-4 py-3">
          <Link
            to="/recommend"
            className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
            aria-label="返回推荐"
          >
            <ArrowLeft size={20} />
          </Link>
          <h2 className="text-sm font-semibold text-slate-800">行程规划</h2>
          {state.stage === 'ready' && (
            <span className="text-xs text-slate-400">
              {state.itinerary.trip.daysCount} 天行程
              {state.preview && ' · 示例预览'}
            </span>
          )}
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-4 py-6">
        {/* Loading */}
        {state.stage === 'loading' && (
          <div className="mt-20 text-center">
            <Loader2 size={40} className="mx-auto mb-4 animate-spin text-blue-500" />
            <p className="text-slate-500">{state.message}</p>
            <p className="mt-1 text-xs text-slate-400">完整规划约需 30-60 秒</p>
          </div>
        )}

        {/* Error */}
        {state.stage === 'error' && (
          <div className="mt-12 text-center">
            <AlertCircle size={40} className="mx-auto mb-3 text-red-500" />
            <p className="text-slate-600">{state.message}</p>
            <Link
              to="/recommend"
              className="mt-4 inline-block text-sm text-blue-600 hover:underline"
            >
              返回推荐页
            </Link>
          </div>
        )}

        {/* Ready */}
        {state.stage === 'ready' && (
          <>
            {/* ── 概览统计条 ── */}
            <div className="mb-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              {state.preview && (
                <div className="mb-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
                  示例数据预览（地址栏加 ?q=你的需求 可生成真实行程）
                </div>
              )}
              <h3 className="text-lg font-bold text-slate-900">
                {state.itinerary.trip.title}
              </h3>
              <p className="mt-0.5 text-xs text-slate-400">
                {state.itinerary.trip.city} · {state.itinerary.trip.dateStart} —{' '}
                {state.itinerary.trip.dateEnd}
              </p>

              <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
                {state.itinerary.trip.stats.map((s, i) => (
                  <div key={i} className="rounded-lg bg-slate-50 px-3 py-2 text-center">
                    <p className="text-base font-bold text-slate-800">{s.value}</p>
                    <p className="text-xs text-slate-400">{s.label}</p>
                  </div>
                ))}
              </div>

              {/* Weather widget */}
              {state.weather && (
                <div className="mt-4 rounded-lg bg-blue-50 p-3">
                  <div className="flex items-center gap-2 text-sm font-medium text-blue-800">
                    <Sun size={16} />
                    <span>天气参考</span>
                    <span className="text-xs text-blue-500">({state.weather.city})</span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {state.weather.daily.slice(0, 5).map((d) => (
                      <div
                        key={d.date}
                        className="rounded-lg bg-white px-3 py-1.5 text-center text-xs shadow-sm"
                      >
                        <p className="font-medium text-slate-700">{d.date.slice(5)}</p>
                        <p className="text-slate-500">{d.weather_desc}</p>
                        <p className="tabular-nums text-slate-400">
                          {d.temp_min.toFixed(0)}~{d.temp_max.toFixed(0)}°C
                        </p>
                      </div>
                    ))}
                  </div>
                  <p className="mt-2 text-xs text-blue-600">{state.weather.advice}</p>
                </div>
              )}

              {/* Pipeline error notice */}
              {state.error && (
                <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
                  <AlertCircle size={14} className="mr-1 inline" />
                  {state.error}
                </div>
              )}
            </div>

            {/* ── 校验报告卡片（Phase 1：真实数据校验可视化） ── */}
            {state.itinerary.validation_report && (
              <ValidationReportCard report={state.itinerary.validation_report} />
            )}

            {/* ── 每天一栏 ── */}
            <div className="space-y-6">
              {state.itinerary.days.map((day, dayIndex) => (
                <DayCard
                  key={`${day.day}-${dayIndex}`}
                  day={day}
                  icon={getDayIcon(day.theme)}
                  regenOpen={regenIndex === dayIndex}
                  regenBusy={regenBusy}
                  regenText={regenIndex === dayIndex ? regenText : ''}
                  onRegenOpen={() => {
                    setRegenIndex(dayIndex)
                    setRegenText('')
                  }}
                  onRegenClose={() => setRegenIndex(null)}
                  onRegenText={setRegenText}
                  onRegenSubmit={() => handleRegen(dayIndex)}
                />
              ))}
            </div>

            {/* ── 预算进度条 ── */}
            {state.itinerary.budget.length > 0 && (
              <div className="mt-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                  <Wallet size={16} className="text-green-600" />
                  预算分配（人均）
                </h3>
                <div className="mt-3 space-y-3">
                  {state.itinerary.budget.map((b) => (
                    <div key={b.label}>
                      <div className="flex items-center justify-between text-xs">
                        <span className="font-medium text-slate-700">{b.label}</span>
                        <span className="tabular-nums text-slate-400">
                          ¥{b.amount} · {b.percent}%
                        </span>
                      </div>
                      <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100">
                        <div
                          className="h-full rounded-full bg-green-500"
                          style={{ width: `${Math.min(b.percent, 100)}%` }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ── 可打勾行前清单 ── */}
            {state.itinerary.checklist.length > 0 && (
              <div className="mt-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
                <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
                  <ClipboardCheck size={16} className="text-blue-500" />
                  行前清单
                  <span className="text-xs font-normal text-slate-400">
                    {checked.filter(Boolean).length}/{state.itinerary.checklist.length}
                  </span>
                </h3>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  {state.itinerary.checklist.map((item, i) => (
                    <button
                      key={i}
                      onClick={() =>
                        setChecked((prev) => prev.map((v, j) => (j === i ? !v : v)))
                      }
                      className={`flex items-start gap-2 rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                        checked[i]
                          ? 'border-green-200 bg-green-50 text-slate-400 line-through'
                          : 'border-slate-200 bg-white text-slate-700 hover:border-blue-300'
                      }`}
                    >
                      <span
                        className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                          checked[i]
                            ? 'border-green-500 bg-green-500 text-white'
                            : 'border-slate-300'
                        }`}
                      >
                        {checked[i] && <Check size={12} />}
                      </span>
                      {item.text}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* ── tips chips ── */}
            {state.itinerary.tips.length > 0 && (
              <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-5">
                <h3 className="flex items-center gap-2 text-sm font-semibold text-amber-800">
                  <Lightbulb size={16} />
                  实用提示
                </h3>
                <div className="mt-3 flex flex-wrap gap-2">
                  {state.itinerary.tips.map((tip, i) => (
                    <span
                      key={i}
                      className="rounded-full bg-white px-3 py-1.5 text-xs text-amber-700 shadow-sm"
                    >
                      {tip}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Bottom actions */}
            <div className="mt-8 flex justify-center gap-4 pb-8">
              <Link
                to="/recommend"
                className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50"
              >
                返回推荐
              </Link>
              <Link
                to="/"
                className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
              >
                规划新行程
              </Link>
            </div>
          </>
        )}
      </main>
    </div>
  )
}

// ── Day card (pure render of one TripDay) ────────────────

interface DayCardProps {
  day: TripDay
  icon: string
  regenOpen: boolean
  regenBusy: boolean
  regenText: string
  onRegenOpen: () => void
  onRegenClose: () => void
  onRegenText: (v: string) => void
  onRegenSubmit: () => void
}

function DayCard({
  day,
  icon,
  regenOpen,
  regenBusy,
  regenText,
  onRegenOpen,
  onRegenClose,
  onRegenText,
  onRegenSubmit,
}: DayCardProps) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm">
      {/* Day header */}
      <div className="flex items-center gap-3 border-b border-slate-100 px-5 py-4">
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100 text-lg">
          {day.day}
        </span>
        <div className="flex-1">
          <h3 className="font-semibold text-slate-900">
            {icon} {day.title}
          </h3>
          <p className="text-xs text-slate-400">{day.theme}</p>
        </div>
        <button
          onClick={regenOpen ? onRegenClose : onRegenOpen}
          className="flex items-center gap-1 rounded-lg px-2 py-1.5 text-xs text-slate-400 transition-colors hover:bg-slate-100 hover:text-blue-600"
          aria-label="重新安排这一天"
        >
          <RefreshCw size={13} />
          重新安排
        </button>
      </div>

      {/* Partial regeneration input */}
      {regenOpen && (
        <div className="border-b border-slate-100 bg-blue-50/50 px-5 py-3">
          <div className="flex gap-2">
            <input
              type="text"
              value={regenText}
              onChange={(e) => onRegenText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && onRegenSubmit()}
              placeholder="说说哪里不满意，如：太赶了 / 想多去博物馆"
              className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-blue-400 focus:outline-none"
              autoFocus
            />
            <button
              onClick={onRegenSubmit}
              disabled={regenBusy || !regenText.trim()}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700 disabled:opacity-50"
            >
              {regenBusy && <Loader2 size={14} className="animate-spin" />}
              {regenBusy ? '生成中' : '重排'}
            </button>
          </div>
          <p className="mt-1.5 text-xs text-slate-400">
            只重新生成这一天，其他天保持不变
          </p>
        </div>
      )}

      {/* Timeline items */}
      <div className="px-5 py-4">
        <h4 className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">
          <MapPin size={14} />
          景点安排
        </h4>
        <div className="space-y-3">
          {day.items.map((item, i) => (
            <div
              key={`${item.time}-${i}`}
              className="flex items-start gap-3 rounded-lg bg-slate-50 p-3"
            >
              <div className="shrink-0">
                <p className="flex items-center gap-1 text-xs font-medium tabular-nums text-blue-600">
                  <Clock size={12} />
                  {item.time}
                </p>
              </div>
              <div className="flex flex-col items-center pt-1">
                <div className="h-2.5 w-2.5 rounded-full border-2 border-blue-400 bg-white" />
                {i < day.items.length - 1 && <div className="mt-1 h-full w-0.5 bg-blue-100" />}
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-slate-800">{item.poi}</p>
                <p className="mt-1 text-xs leading-relaxed text-slate-500">{item.note}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* 每日一味 */}
      <div className="border-t border-slate-100 px-5 py-3">
        <p className="flex items-center gap-1.5 text-xs text-slate-500">
          <Coffee size={14} className="shrink-0 text-amber-500" />
          <span>
            <span className="font-medium text-slate-600">每日一味：</span>
            {day.eat}
          </span>
        </p>
      </div>
    </div>
  )
}
