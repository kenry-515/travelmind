/**
 * TravelMind Agent — HistoryPage
 *
 * "My Trips" page showing saved itineraries from PostgreSQL.
 * Degrades gracefully: shows empty state when DB is unavailable.
 */

import { useState, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  Loader2,
  Trash2,
  MapPin,
  Calendar,
  Clock,
  AlertCircle,
  Heart,
} from 'lucide-react'
import {
  fetchItineraries,
  fetchItineraryDetail,
  deleteItinerary,
  fetchFavorites,
  type ItinerarySummary,
  type FavoriteItem,
} from '../lib/api'
import { toast } from '../components/Toast'

type PageState =
  | { stage: 'loading' }
  | { stage: 'ready'; itineraries: ItinerarySummary[]; favorites: FavoriteItem[] }
  | { stage: 'error'; message: string }

export function HistoryPage() {
  const navigate = useNavigate()
  const [state, setState] = useState<PageState>({ stage: 'loading' })
  const [deleting, setDeleting] = useState<string | null>(null)

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    setState({ stage: 'loading' })
    try {
      const [itineraryRes, favoritesRes] = await Promise.all([
        fetchItineraries(),
        fetchFavorites(),
      ])
      setState({
        stage: 'ready',
        itineraries: itineraryRes.itineraries,
        favorites: favoritesRes.favorites,
      })
    } catch {
      setState({ stage: 'error', message: '无法加载历史记录，请检查后端连接。' })
    }
  }

  async function handleDelete(id: string, title: string) {
    if (deleting) return
    setDeleting(id)
    try {
      await deleteItinerary(id)
      toast.success(`已删除「${title}」`)
      setState((prev) => {
        if (prev.stage !== 'ready') return prev
        return {
          ...prev,
          itineraries: prev.itineraries.filter((i) => i.id !== id),
        }
      })
    } catch {
      toast.error('删除失败，请稍后再试')
    } finally {
      setDeleting(null)
    }
  }

  async function handleView(id: string) {
    try {
      const detail = await fetchItineraryDetail(id)
      sessionStorage.setItem('travelmind_itinerary', JSON.stringify(detail.plan))
      navigate(`/itinerary?id=${id}`)
    } catch {
      toast.error('无法加载行程详情')
    }
  }

  const favoriteItineraryIds = new Set(
    state.stage === 'ready'
      ? state.favorites
          .filter((f) => f.target_type === 'itinerary')
          .map((f) => f.target_id)
      : []
  )

  return (
    <div className="relative min-h-screen overflow-hidden bg-surface-secondary pb-20 sm:pb-0">
      {/* 弱化极光背景（Phase 12.24） */}
      <div aria-hidden className="aurora aurora-soft">
        <span /><span /><span />
      </div>
      {/* Header */}
      <header className="glass sticky top-0 z-10 border-b border-border-light">
        <div className="mx-auto flex max-w-4xl items-center gap-2 px-3 py-2.5 sm:gap-3 sm:px-4 sm:py-3">
          <Link
            to="/"
            className="rounded-xl p-1.5 text-slate-500 transition-colors hover:bg-brand-50 hover:text-brand-600"
            aria-label="返回首页"
          >
            <ArrowLeft size={20} />
          </Link>
          <h2 className="text-sm font-semibold text-slate-800">我的行程</h2>
          {state.stage === 'ready' && (
            <span className="text-xs text-slate-400">
              {state.itineraries.length} 条记录
            </span>
          )}
        </div>
      </header>

      <main className="relative mx-auto max-w-4xl px-4 py-6">
        {/* Loading */}
        {state.stage === 'loading' && (
          <div className="mt-20 text-center">
            <Loader2 size={40} className="mx-auto mb-4 animate-spin text-brand-500" />
            <p className="text-slate-500">加载历史记录...</p>
          </div>
        )}

        {/* Error */}
        {state.stage === 'error' && (
          <div className="mt-12 text-center">
            <AlertCircle size={40} className="mx-auto mb-3 text-red-500" />
            <p className="text-slate-600">{state.message}</p>
            <button
              onClick={loadData}
              className="btn-primary mt-4 px-4 py-2 text-sm"
            >
              重试
            </button>
          </div>
        )}

        {/* Empty state */}
        {state.stage === 'ready' && state.itineraries.length === 0 && (
          <div className="mt-20 text-center animate-fade-in-up">
            <div className="mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-3xl bg-gradient-to-br from-brand-100 to-accent-100 animate-float-slow">
              <MapPin size={36} className="text-brand-500" />
            </div>
            <p className="font-semibold text-slate-600">还没有保存的行程</p>
            <p className="mt-1 text-sm text-slate-400">规划好的行程会自动保存在这里</p>
            <Link
              to="/chat"
              className="btn-primary mt-4 inline-flex px-6 py-3 text-sm"
            >
              去规划一个吧 →
            </Link>
          </div>
        )}

        {/* Itinerary list */}
        {state.stage === 'ready' && state.itineraries.length > 0 && (
          <div className="space-y-3">
            {state.itineraries.map((item) => (
              <div
                key={item.id}
                className="card hover-lift group flex items-center gap-4 p-4"
              >
                {/* Clickable main area */}
                <button
                  onClick={() => handleView(item.id)}
                  className="flex flex-1 items-center gap-4 text-left"
                >
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-100 to-accent-100 text-brand-500">
                    <MapPin size={22} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="font-bold text-slate-900 truncate">
                        {item.title}
                      </h3>
                      {favoriteItineraryIds.has(item.id) && (
                        <Heart size={14} className="shrink-0 fill-red-400 text-red-400" />
                      )}
                    </div>
                    <div className="mt-1 flex flex-wrap gap-3 text-xs text-slate-400">
                      {item.city && (
                        <span className="flex items-center gap-1">
                          <MapPin size={11} />
                          {item.city}
                        </span>
                      )}
                      <span className="flex items-center gap-1">
                        <Calendar size={11} />
                        {item.days} 天
                      </span>
                      <span className="flex items-center gap-1">
                        <Clock size={11} />
                        {item.created_at?.slice(0, 10) || ''}
                      </span>
                    </div>
                  </div>
                </button>

                {/* Delete button */}
                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    handleDelete(item.id, item.title)
                  }}
                  disabled={deleting === item.id}
                  className="shrink-0 rounded-lg p-2 text-slate-300 opacity-0 transition-all hover:bg-red-50 hover:text-red-500 group-hover:opacity-100 disabled:opacity-50"
                  aria-label="删除行程"
                >
                  {deleting === item.id ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <Trash2 size={16} />
                  )}
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Bottom actions — 仅列表非空时显示（空状态自带 CTA，避免重复） */}
        {state.stage === 'ready' && state.itineraries.length > 0 && (
          <div className="mt-8 flex justify-center gap-4 pb-8">
            <Link
              to="/"
              className="btn-secondary px-4 py-2 text-sm"
            >
              返回首页
            </Link>
            <Link
              to="/chat"
              className="btn-primary px-4 py-2 text-sm"
            >
              规划新行程
            </Link>
          </div>
        )}
      </main>
    </div>
  )
}
