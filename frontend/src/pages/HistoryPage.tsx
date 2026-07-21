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
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center gap-3 px-4 py-3">
          <Link
            to="/"
            className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
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

      <main className="mx-auto max-w-4xl px-4 py-6">
        {/* Loading */}
        {state.stage === 'loading' && (
          <div className="mt-20 text-center">
            <Loader2 size={40} className="mx-auto mb-4 animate-spin text-blue-500" />
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
              className="mt-4 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
            >
              重试
            </button>
          </div>
        )}

        {/* Empty state */}
        {state.stage === 'ready' && state.itineraries.length === 0 && (
          <div className="mt-20 text-center">
            <MapPin size={48} className="mx-auto mb-4 text-slate-300" />
            <p className="text-slate-500">还没有保存的行程</p>
            <Link
              to="/chat"
              className="mt-4 inline-block rounded-lg bg-blue-600 px-6 py-3 text-sm font-medium text-white transition-colors hover:bg-blue-700"
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
                className="group flex items-center gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md"
              >
                {/* Clickable main area */}
                <button
                  onClick={() => handleView(item.id)}
                  className="flex flex-1 items-center gap-4 text-left"
                >
                  <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-50 text-blue-500">
                    <MapPin size={22} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h3 className="font-medium text-slate-900 truncate">
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

        {/* Bottom actions */}
        <div className="mt-8 flex justify-center gap-4 pb-8">
          <Link
            to="/"
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-50"
          >
            返回首页
          </Link>
          <Link
            to="/chat"
            className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-700"
          >
            规划新行程
          </Link>
        </div>
      </main>
    </div>
  )
}
