/**
 * TravelMind Agent — ItineraryPage
 *
 * Displays a fully generated day-by-day travel itinerary from the
 * multi-agent planning workflow. Supports both:
 * - Direct navigation with ?q=... (runs full plan pipeline)
 * - Navigation after recommendations (reads from sessionStorage)
 */

import { useState, useEffect, useRef } from 'react'
import { useSearchParams, Link } from 'react-router-dom'
import {
  ArrowLeft,
  Clock,
  MapPin,
  Coffee,
  Navigation,
  Lightbulb,
  Loader2,
  AlertCircle,
  Sun,
} from 'lucide-react'
import {
  fetchPlan,
  fetchWeather,
  type ItineraryData,
  type PlanResponse,
  type WeatherForecast,
  type PlaceItem,
} from '../lib/api'

type PageState =
  | { stage: 'loading'; message: string }
  | { stage: 'ready'; itinerary: ItineraryData; places: PlaceItem[]; weather: WeatherForecast | null; error: string | null }
  | { stage: 'error'; message: string }

export function ItineraryPage() {
  const [searchParams] = useSearchParams()
  const query = searchParams.get('q') || ''
  const [state, setState] = useState<PageState>({
    stage: 'loading',
    message: '正在分析需求...',
  })
  const hasRun = useRef(false)

  useEffect(() => {
    if (!query || hasRun.current) return
    hasRun.current = true
    runPipeline(query)
  }, [query])

  async function runPipeline(userInput: string) {
    setState({ stage: 'loading', message: '正在提取用户画像...' })

    try {
      const timer = setInterval(() => {
        setState((prev) => {
          if (prev.stage !== 'loading') return prev
          const msgs = [
            '正在提取用户画像...',
            '正在分析热门趋势...',
            '正在获取天气数据...',
            '正在检索知识库...',
            '正在评分和排序...',
            '正在生成行程规划...',
          ]
          const cur = msgs.findIndex((m) => m === prev.message)
          const next = (cur + 1) % msgs.length
          return { ...prev, message: msgs[next] }
        })
      }, 2500)

      const data: PlanResponse = await fetchPlan(userInput)
      clearInterval(timer)

      if (!data.itinerary || !data.itinerary.plan || data.itinerary.plan.length === 0) {
        const errMsg = data.error || '行程生成失败，请稍后重试。'
        setState({ stage: 'error', message: errMsg })
        return
      }

      // Also fetch weather separately for richer display
      let weather: WeatherForecast | null = null
      const city = data.user_profile
        ? (data.user_profile as Record<string, unknown>).destination as string
        : ''
      if (city) {
        try {
          weather = await fetchWeather(city, data.itinerary.days)
        } catch {
          // Weather is non-critical
        }
      }

      setState({
        stage: 'ready',
        itinerary: data.itinerary,
        places: (data.recommendations || []) as PlaceItem[],
        weather,
        error: data.error,
      })
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : '行程规划服务暂不可用，请稍后重试。'
      setState({ stage: 'error', message: msg })
    }
  }

  // ── Helpers ──────────────────────────────────────────────

  const dayIcons: Record<string, string> = {
    '城市探索': '🏙️',
    '历史文化': '🏛️',
    '自然风光': '🏔️',
    '美食之旅': '🍜',
    '休闲度假': '🏖️',
    '亲子时光': '🎠',
    '文艺之旅': '🎨',
    '探险体验': '🧗',
  }

  function getDayIcon(theme: string): string {
    for (const [key, emoji] of Object.entries(dayIcons)) {
      if (theme.includes(key.replace('之旅', '')) || key.includes(theme.slice(0, 2))) {
        return emoji
      }
    }
    return '📍'
  }

  // ── Render ───────────────────────────────────────────────

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
              {state.itinerary.days} 天行程
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
            <p className="mt-1 text-xs text-slate-400">完整规划约需 15-20 秒</p>
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
            {/* Overview */}
            <div className="mb-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
              <p className="text-base leading-relaxed text-slate-700">
                {state.itinerary.overview}
              </p>

              {/* Weather widget */}
              {state.weather && (
                <div className="mt-4 rounded-lg bg-blue-50 p-3">
                  <div className="flex items-center gap-2 text-sm font-medium text-blue-800">
                    <Sun size={16} />
                    <span>天气参考</span>
                    <span className="text-xs text-blue-500">
                      ({state.weather.city})
                    </span>
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    {state.weather.daily.slice(0, 5).map((d) => (
                      <div
                        key={d.date}
                        className="rounded-lg bg-white px-3 py-1.5 text-center text-xs shadow-sm"
                      >
                        <p className="font-medium text-slate-700">
                          {d.date.slice(5)}
                        </p>
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

              {/* Error notice */}
              {state.error && (
                <div className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700">
                  <AlertCircle size={14} className="inline mr-1" />
                  {state.error}
                </div>
              )}
            </div>

            {/* Day-by-day plan */}
            <div className="space-y-6">
              {state.itinerary.plan.map((day) => (
                <div
                  key={day.day}
                  className="rounded-xl border border-slate-200 bg-white shadow-sm"
                >
                  {/* Day header */}
                  <div className="flex items-center gap-3 border-b border-slate-100 px-5 py-4">
                    <span className="flex h-10 w-10 items-center justify-center rounded-full bg-blue-100 text-lg">
                      {day.day}
                    </span>
                    <div className="flex-1">
                      <h3 className="font-semibold text-slate-900">
                        {getDayIcon(day.theme)} {day.theme}
                      </h3>
                      <p className="text-xs text-slate-400">第 {day.day} 天</p>
                    </div>
                    <div className="hidden sm:block text-xs text-slate-400">
                      <Navigation size={14} className="inline mr-1" />
                      {day.transport_tips.slice(0, 30)}
                      {day.transport_tips.length > 30 ? '...' : ''}
                    </div>
                  </div>

                  {/* Attractions */}
                  <div className="px-5 py-4">
                    <h4 className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">
                      <MapPin size={14} />
                      景点安排
                    </h4>
                    <div className="space-y-3">
                      {day.attractions.map((attr, i) => (
                        <div
                          key={`${attr.name}-${i}`}
                          className="flex items-start gap-3 rounded-lg bg-slate-50 p-3"
                        >
                          {/* Time column */}
                          <div className="shrink-0 text-right">
                            <p className="flex items-center gap-1 text-xs font-medium text-blue-600">
                              <Clock size={12} />
                              {attr.time}
                            </p>
                            <p className="mt-0.5 text-xs tabular-nums text-slate-400">
                              {attr.duration_min}分钟
                            </p>
                          </div>
                          {/* Separator line */}
                          <div className="flex flex-col items-center pt-1">
                            <div className="h-2.5 w-2.5 rounded-full border-2 border-blue-400 bg-white" />
                            {i < day.attractions.length - 1 && (
                              <div className="mt-1 h-full w-0.5 bg-blue-100" />
                            )}
                          </div>
                          {/* Details */}
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-slate-800">
                              {attr.name}
                            </p>
                            {attr.notes && (
                              <p className="mt-1 text-xs leading-relaxed text-slate-500">
                                {attr.notes}
                              </p>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Meals */}
                  {day.meals.length > 0 && (
                    <div className="border-t border-slate-100 px-5 py-4">
                      <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">
                        <Coffee size={14} />
                        餐饮推荐
                      </h4>
                      <div className="flex flex-wrap gap-2">
                        {day.meals.map((meal, i) => (
                          <span
                            key={`${meal.type}-${i}`}
                            className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-1 text-xs"
                          >
                            <span className="font-medium text-slate-600">
                              {meal.type}
                            </span>
                            <span className="text-slate-400">{meal.suggestion}</span>
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Transport tips (mobile only) */}
                  <div className="border-t border-slate-100 px-5 py-3 sm:hidden">
                    <p className="flex items-center gap-1.5 text-xs text-slate-400">
                      <Navigation size={14} />
                      {day.transport_tips}
                    </p>
                  </div>
                </div>
              ))}
            </div>

            {/* General tips */}
            {state.itinerary.general_tips && (
              <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-5">
                <h3 className="flex items-center gap-2 text-sm font-semibold text-amber-800">
                  <Lightbulb size={16} />
                  旅行贴士
                </h3>
                <p className="mt-2 text-sm leading-relaxed text-amber-700">
                  {state.itinerary.general_tips}
                </p>
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
