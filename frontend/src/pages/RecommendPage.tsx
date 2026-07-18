/**
 * TravelMind Agent — RecommendPage
 *
 * Search for travel recommendations. Runs the full recommendation pipeline
 * (Profile → Trend → RAG → Recommend) and displays ranked places with
 * 6-factor score breakdowns.
 */

import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeft, Search, Sparkles, TrendingUp, Loader2, AlertCircle } from 'lucide-react'
import { PlaceCard } from '../components/PlaceCard'
import { fetchRecommendations, type RecommendResponse } from '../lib/api'

type PageState =
  | { stage: 'idle' }
  | { stage: 'loading' }
  | { stage: 'results'; data: RecommendResponse }
  | { stage: 'error'; message: string }

export function RecommendPage() {
  const [query, setQuery] = useState('')
  const [state, setState] = useState<PageState>({ stage: 'idle' })

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    const q = query.trim()
    if (!q) return

    setState({ stage: 'loading' })

    try {
      const data = await fetchRecommendations(q)
      if (data.total_results === 0) {
        setState({ stage: 'error', message: `未找到「${data.city}」的相关推荐，请尝试其他目的地。` })
      } else {
        setState({ stage: 'results', data })
      }
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : '推荐服务暂不可用，请稍后重试。'
      setState({ stage: 'error', message: msg })
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-3">
          <Link
            to="/"
            className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
            aria-label="返回首页"
          >
            <ArrowLeft size={20} />
          </Link>
          <h2 className="text-sm font-semibold text-slate-800">智能推荐</h2>
          <span className="text-xs text-slate-400">
            输入需求，AI 为你推荐最佳景点
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6">
        {/* Search Bar */}
        <form onSubmit={handleSubmit} className="mb-8">
          <div className="relative flex items-center">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="例如：推荐重庆3日游，喜欢夜景和美食..."
              className="w-full rounded-xl border border-slate-300 bg-white px-5 py-3.5 pr-12 text-base shadow-sm transition-all placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
              disabled={state.stage === 'loading'}
            />
            <button
              type="submit"
              disabled={state.stage === 'loading' || !query.trim()}
              aria-label="搜索推荐"
              className="absolute right-3 rounded-lg p-2 text-slate-400 transition-colors hover:bg-blue-50 hover:text-blue-600 disabled:opacity-50"
            >
              {state.stage === 'loading' ? (
                <Loader2 size={22} className="animate-spin" />
              ) : (
                <Search size={22} />
              )}
            </button>
          </div>
        </form>

        {/* Idle state */}
        {state.stage === 'idle' && (
          <div className="mt-20 text-center">
            <Sparkles className="mx-auto mb-4 text-slate-300" size={48} />
            <p className="text-lg text-slate-400">
              输入你的旅行需求，AI 将为你智能推荐
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              {[
                '推荐重庆3日游，喜欢夜景和美食',
                '想去成都看熊猫，吃火锅',
                '西安历史文化之旅',
                '带父母去杭州休闲游',
              ].map((example) => (
                <button
                  key={example}
                  onClick={() => {
                    setQuery(example)
                  }}
                  className="rounded-full border border-slate-200 px-4 py-1.5 text-sm text-slate-500 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Loading */}
        {state.stage === 'loading' && (
          <div className="mt-20 text-center">
            <Loader2 size={40} className="mx-auto mb-4 animate-spin text-blue-500" />
            <p className="text-slate-500">AI 正在分析你的需求，搜索最佳景点...</p>
            <p className="mt-1 text-xs text-slate-400">
              这可能需要 10-15 秒
            </p>
          </div>
        )}

        {/* Error */}
        {state.stage === 'error' && (
          <div className="mt-12 text-center">
            <AlertCircle size={40} className="mx-auto mb-3 text-amber-500" />
            <p className="text-slate-600">{state.message}</p>
            <button
              onClick={() => setState({ stage: 'idle' })}
              className="mt-4 text-sm text-blue-600 hover:underline"
            >
              重新搜索
            </button>
          </div>
        )}

        {/* Results */}
        {state.stage === 'results' && (
          <>
            {/* Summary */}
            <div className="mb-6 rounded-xl bg-white border border-slate-200 p-5 shadow-sm">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-bold text-slate-900">
                    {state.data.city} · 共 {state.data.total_results} 个推荐
                  </h3>
                  {state.data.trend_summary.top_trending.length > 0 && (
                    <div className="mt-2 flex items-center gap-2 text-xs text-slate-500">
                      <TrendingUp size={14} className="text-orange-500" />
                      <span>热门趋势：</span>
                      {state.data.trend_summary.top_trending.slice(0, 3).map((t, i) => (
                        <span key={t.name} className="font-medium text-slate-700">
                          {t.name}
                          {i < Math.min(state.data.trend_summary.top_trending.length, 3) - 1 && '、'}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <Link
                  to={`/itinerary?q=${encodeURIComponent(query)}`}
                  className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
                >
                  生成行程
                </Link>
              </div>
            </div>

            {/* Place Grid */}
            <div className="grid gap-4 sm:grid-cols-2">
              {state.data.places.map((place, i) => (
                <PlaceCard key={`${place.name}-${i}`} place={place} rank={i + 1} />
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  )
}
