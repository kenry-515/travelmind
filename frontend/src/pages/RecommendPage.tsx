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
import { SkeletonRecommend } from '../components/Skeleton'
import { fetchRecommendations, type RecommendResponse } from '../lib/api'

type PageState =
  | { stage: 'idle' }
  | { stage: 'loading' }
  | { stage: 'results'; data: RecommendResponse }
  | { stage: 'error'; message: string }

export function RecommendPage() {
  const [query, setQuery] = useState('')
  const [state, setState] = useState<PageState>({ stage: 'idle' })

  const runSearch = async (q: string) => {
    if (!q.trim()) return
    setQuery(q)
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

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    await runSearch(query.trim())
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-surface-secondary pb-20 sm:pb-0">
      {/* 弱化极光背景（Phase 12.24） */}
      <div aria-hidden className="aurora aurora-soft">
        <span /><span /><span />
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
          <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200">智能推荐</h2>
          <span className="hidden text-xs text-slate-400 dark:text-slate-500 sm:inline">
            输入需求，AI 为你推荐最佳景点
          </span>
        </div>
      </header>

      <main className="relative mx-auto max-w-5xl px-4 py-6">
        {/* Search Bar */}
        <form onSubmit={handleSubmit} className="mb-8">
          <div className="relative flex items-center">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="例如：广州3日游，想体验西关文化和早茶..."
              className="w-full rounded-2xl border border-border bg-white dark:bg-slate-900 px-5 py-3.5 pr-14 text-base shadow-card transition-all placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-brand-400 focus:outline-none focus:ring-4 focus:ring-brand-100 dark:focus:ring-brand-900/40"
              disabled={state.stage === 'loading'}
            />
            <button
              type="submit"
              disabled={state.stage === 'loading' || !query.trim()}
              aria-label="搜索推荐"
              className="btn-primary absolute right-2 rounded-xl p-2"
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
          <div className="mt-16 text-center animate-fade-in-up">
            <div className="mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-3xl bg-gradient-to-br from-brand-100 to-accent-100 dark:from-slate-800 dark:to-slate-700 animate-float-slow">
              <Sparkles className="text-brand-500" size={36} />
            </div>
            <p className="text-lg font-medium text-slate-600 dark:text-slate-400">
              说说你想怎么玩，AI 给你挑出最值得去的
            </p>
            <p className="mt-1 text-sm text-slate-400 dark:text-slate-500">点一个试试，或直接输入你的需求 👇</p>
            <div className="mx-auto mt-6 grid max-w-2xl grid-cols-1 gap-3 sm:grid-cols-2">
              {[
                { icon: '🏮', text: '推荐广州3日游，体验西关文化和早茶' },
                { icon: '🌉', text: '珠江夜游加广州塔夜景攻略' },
                { icon: '🍵', text: '广州美食寻味，老字号早茶' },
                { icon: '👨‍👩‍👧', text: '带孩子去长隆欢乐世界' },
              ].map((example) => (
                <button
                  key={example.text}
                  onClick={() => runSearch(example.text)}
                  className="hover-lift flex items-center gap-3 rounded-2xl border border-border bg-white dark:bg-slate-900 px-4 py-3 text-left text-sm text-slate-700 dark:text-slate-300 shadow-card hover:border-brand-300 dark:hover:border-brand-700 hover:bg-brand-50/50 dark:hover:bg-brand-900/30"
                >
                  <span className="text-xl">{example.icon}</span>
                  <span>{example.text}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Loading — Phase 12.29b: 使用骨架屏替代纯 spinner */}
        {state.stage === 'loading' && (
          <div className="mt-6">
            <SkeletonRecommend />
          </div>
        )}

        {/* Error */}
        {state.stage === 'error' && (
          <div className="mt-12 text-center">
            <AlertCircle size={40} className="mx-auto mb-3 text-amber-500" />
            <p className="text-slate-600 dark:text-slate-400">{state.message}</p>
            <button
              onClick={() => setState({ stage: 'idle' })}
              className="mt-4 text-sm font-medium text-brand-600 dark:text-brand-400 hover:underline"
            >
              重新搜索
            </button>
          </div>
        )}

        {/* Results */}
        {state.stage === 'results' && (
          <>
            {/* Summary */}
            <div className="card mb-6 p-4 sm:p-5">
              <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">
                    {state.data.city} · 共 {state.data.total_results} 个推荐
                  </h3>
                  {state.data.trend_summary.top_trending.length > 0 && (
                    <div className="mt-2 flex items-center gap-2 text-xs text-slate-500 dark:text-slate-400">
                      <TrendingUp size={14} className="text-orange-500" />
                      <span>热门趋势：</span>
                      {state.data.trend_summary.top_trending.slice(0, 3).map((t, i) => (
                        <span key={t.name} className="font-medium text-slate-700 dark:text-slate-300">
                          {t.name}
                          {i < Math.min(state.data.trend_summary.top_trending.length, 3) - 1 && '、'}
                        </span>
                      ))}
                    </div>
                  )}
                  {/* Phase 12.2: Multi-city notice */}
                  {(state.data.trend_summary as { multi_city?: boolean; cities?: string[] }).multi_city && (
                    <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                      未识别到具体景点，已展示广州全库匹配结果。如需生成行程，请在搜索中加入具体景点名（如"推荐广州早茶美食"）。
                    </p>
                  )}
                </div>
                {/* Only show "生成行程" when a specific city is identified */}
                {!state.data.city.startsWith('多城市') && (
                  <Link
                    to={`/itinerary?q=${encodeURIComponent(query)}`}
                    className="btn-primary whitespace-nowrap px-4 py-2 text-sm"
                  >
                    生成行程
                  </Link>
                )}
              </div>
            </div>

            {/* Place Grid — show city label for multi-city results */}
            <div className="grid gap-4 sm:grid-cols-2">
              {state.data.places.map((place, i) => (
                <PlaceCard key={`${place.city || '?'}-${place.name}-${i}`} place={place} rank={i + 1} />
              ))}
            </div>
          </>
        )}
      </main>
    </div>
  )
}
