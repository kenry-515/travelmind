/**
 * TravelMind Agent — SavedPlacesSidebar（Phase 14）
 *
 * 🗂️ 浮动侧边栏「想去的地方」
 * 支持：收藏列表、一键加行程、拖拽、分享清单、热点推荐
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { BookmarkCheck, X, MapPin, Heart, Trash2, PlusCircle, Share2, Flame } from 'lucide-react'
import { useSavedPlaces } from '../lib/savedPlaces'
import { toast } from './Toast'

// Phase 14.4: 热门 POI 推荐（按城市分组的热度高且用户未收藏的）
const POPULAR_PLACES: Record<string, { name: string; tags: string[] }[]> = {
  '重庆': [
    { name: '洪崖洞', tags: ['夜景', '地标'] },
    { name: '解放碑', tags: ['美食', '购物'] },
    { name: '磁器口', tags: ['古镇', '美食'] },
  ],
  '成都': [
    { name: '大熊猫基地', tags: ['亲子', '自然'] },
    { name: '宽窄巷子', tags: ['历史', '美食'] },
    { name: '都江堰', tags: ['历史', '自然'] },
  ],
  '北京': [
    { name: '故宫博物院', tags: ['历史', '博物馆'] },
    { name: '长城', tags: ['历史', '自然'] },
  ],
  '上海': [
    { name: '外滩', tags: ['地标', '夜景'] },
    { name: '迪士尼', tags: ['亲子', '娱乐'] },
  ],
  '西安': [
    { name: '兵马俑', tags: ['历史', '博物馆'] },
    { name: '大唐不夜城', tags: ['夜景', '打卡'] },
  ],
  '广州': [
    { name: '广州塔', tags: ['地标', '夜景'] },
    { name: '沙面', tags: ['建筑', '文艺'] },
  ],
  '杭州': [
    { name: '西湖', tags: ['自然', '摄影'] },
    { name: '灵隐寺', tags: ['寺庙', '历史'] },
  ],
  '深圳': [
    { name: '世界之窗', tags: ['地标', '娱乐'] },
    { name: '欢乐港湾', tags: ['地标', '购物'] },
  ],
  '长沙': [
    { name: '岳麓山', tags: ['自然', '历史'] },
    { name: '橘子洲', tags: ['地标', '自然'] },
  ],
  '大理': [
    { name: '洱海', tags: ['自然', '摄影'] },
    { name: '大理古城', tags: ['古镇', '文艺'] },
  ],
  '喀什': [
    { name: '喀什古城', tags: ['古镇', '历史'] },
    { name: '艾提尕尔清真寺', tags: ['寺庙', '建筑'] },
  ],
}

export function SavedPlacesSidebar() {
  const { places, removePlace, addPlace, sharePlacesText } = useSavedPlaces()
  const [open, setOpen] = useState(false)
  const [showSuggestions, setShowSuggestions] = useState(false)
  const navigate = useNavigate()

  const addToItinerary = (name: string, city: string) => {
    try {
      const stored = sessionStorage.getItem('travelmind_itinerary')
      if (stored) {
        const itinerary = JSON.parse(stored)
        if (itinerary.days && itinerary.days.length > 0) {
          itinerary.days[0].items.push({ poi: name, time: '自由安排', note: `[景] ${city}景点` })
          const visitCount = itinerary.days.reduce((n: number, d: any) =>
            n + d.items.filter((it: any) => !/餐|休息|入住|返程|酒店/.test(it.poi)).length, 0)
          if (itinerary.trip?.stats) {
            itinerary.trip.stats = itinerary.trip.stats.map((s: any) =>
              /地点/.test(s.label) ? { ...s, value: `${visitCount} 个` } : s)
          }
          sessionStorage.setItem('travelmind_itinerary', JSON.stringify(itinerary))
          navigate('/itinerary')
          return
        }
      }
      navigate(`/chat?q=我想去${city}玩，想去${name}看看`)
    } catch { /* */ }
  }

  const handleShare = () => {
    const text = sharePlacesText()
    navigator.clipboard.writeText(text).then(() => {
      toast.success('已复制到剪贴板 📋')
    }).catch(() => {
      // Fallback
      const textarea = document.createElement('textarea')
      textarea.value = text
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
      toast.success('已复制到剪贴板 📋')
    })
  }

  // 计算未收藏的热门推荐
  const savedKeys = new Set(places.map(p => `${p.name}_${p.city}`))
  const suggestions = Object.entries(POPULAR_PLACES).flatMap(([city, items]) =>
    items
      .filter(item => !savedKeys.has(`${item.name}_${city}`))
      .map(item => ({ ...item, city }))
  ).slice(0, 8)

  const grouped = places.reduce<Record<string, typeof places>>((acc, p) => {
    const city = p.city || '未分类'
    if (!acc[city]) acc[city] = []
    acc[city].push(p)
    return acc
  }, {})

  return (
    <>
      {/* 浮动按钮 */}
      <button
        onClick={() => setOpen(true)}
        className="fixed right-0 top-1/3 z-40 flex items-center gap-1 rounded-l-xl bg-gradient-to-r from-brand-500 to-brand-600 px-2.5 py-3 text-xs font-medium text-white shadow-lg transition-all hover:from-brand-600 hover:to-brand-700 hover:shadow-xl"
        aria-label="打开想去的地方"
      >
        <BookmarkCheck size={16} />
        <span className="hidden sm:inline">{places.length}</span>
      </button>

      {open && (
        <div className="fixed inset-0 z-40 bg-black/20 backdrop-blur-sm" onClick={() => setOpen(false)} />
      )}

      <div className={`fixed right-0 top-0 z-50 flex h-full w-80 flex-col bg-white dark:bg-slate-900 shadow-2xl transition-transform duration-300 ${open ? 'translate-x-0' : 'translate-x-full'}`}>
        {/* Header */}
        <div className="flex items-center justify-between border-b border-brand-100 dark:border-brand-900/30 bg-gradient-to-r from-brand-50 dark:from-slate-800 to-accent-50 dark:to-slate-900 px-4 py-3">
          <div className="flex items-center gap-2">
            <Heart size={18} className="text-brand-500" />
            <h2 className="text-base font-bold text-slate-800 dark:text-slate-200">想去的地方</h2>
            <span className="rounded-full bg-brand-100 dark:bg-brand-900/40 px-2 py-0.5 text-xs font-medium text-brand-600 dark:text-brand-400">{places.length}</span>
          </div>
          <div className="flex items-center gap-1">
            {places.length > 0 && (
              <button onClick={handleShare} className="rounded-lg p-1.5 text-slate-400 dark:text-slate-500 transition-colors hover:bg-brand-100 dark:hover:bg-brand-900/30 hover:text-brand-600 dark:hover:text-brand-400" title="分享清单" aria-label="分享清单">
                <Share2 size={16} />
              </button>
            )}
            <button onClick={() => setOpen(false)} aria-label="关闭侧边栏" className="rounded-lg p-1.5 text-slate-400 dark:text-slate-500 transition-colors hover:bg-brand-100 dark:hover:bg-brand-900/30 hover:text-brand-600 dark:hover:text-brand-400">
              <X size={18} />
            </button>
          </div>
        </div>

        {/* 空状态 */}
        {places.length === 0 && !showSuggestions && (
          <div className="flex flex-1 flex-col items-center justify-center px-6 text-center">
            <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 dark:bg-brand-900/30">
              <BookmarkCheck size={28} className="text-brand-300 dark:text-brand-500" />
            </div>
            <p className="text-sm font-medium text-slate-600 dark:text-slate-400">还没有收藏想去的地方</p>
            <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">在推荐页、图片页点击 ❤️ 即可收藏</p>
            <button onClick={() => setShowSuggestions(true)} className="mt-4 rounded-xl bg-brand-50 dark:bg-brand-900/30 px-4 py-2 text-xs font-medium text-brand-600 dark:text-brand-400 hover:bg-brand-100 dark:hover:bg-brand-900/50">
              看看热门推荐 🔥
            </button>
          </div>
        )}

        {/* 收藏列表 */}
        {places.length > 0 && (
          <div className="flex-1 overflow-y-auto px-3 py-3">
            {/* 热门推荐快速添加 */}
            {suggestions.length > 0 && (
              <div className="mb-4 rounded-xl border border-amber-100 dark:border-amber-900/30 bg-amber-50/50 dark:bg-amber-900/20 p-3">
                <button
                  onClick={() => setShowSuggestions(!showSuggestions)}
                  className="flex items-center gap-1.5 text-xs font-semibold text-amber-700 dark:text-amber-400"
                >
                  <Flame size={13} className="text-amber-500" />
                  热门推荐
                  <span className="ml-auto text-amber-400">{showSuggestions ? '收起' : `${suggestions.length}个`}</span>
                </button>
                {showSuggestions && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {suggestions.map((s) => (
                      <button
                        key={`${s.city}_${s.name}`}
                        onClick={() => { addPlace({ name: s.name, city: s.city, tags: s.tags, note: '', source: 'manual' }); toast.success(`已收藏「${s.name}」`) }}
                        className="rounded-lg border border-amber-200 dark:border-amber-800 bg-white dark:bg-slate-900 px-2 py-1 text-xs text-slate-600 dark:text-slate-400 transition-all hover:border-amber-300 dark:hover:border-amber-700 hover:text-amber-700 dark:hover:text-amber-300"
                      >
                        + {s.name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {Object.entries(grouped).map(([city, cityPlaces]) => (
              <div key={city} className="mb-3">
                <h3 className="mb-1.5 flex items-center gap-1 px-1 text-xs font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                  <MapPin size={12} />
                  {city}
                  <span className="ml-auto text-slate-300 dark:text-slate-600">{cityPlaces.length}</span>
                </h3>
                <div className="space-y-1.5">
                  {cityPlaces.map((p) => (
                    <div key={p.id} draggable
                      onDragStart={(e) => { e.dataTransfer.setData('text/plain', JSON.stringify({ name: p.name, city: p.city, tags: p.tags, note: p.note })); e.dataTransfer.effectAllowed = 'copy' }}
                      className="group relative cursor-grab rounded-xl border border-border-light bg-white dark:bg-slate-900 p-3 transition-all hover:border-brand-200 dark:hover:border-brand-700 hover:shadow-sm active:cursor-grabbing"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-semibold text-slate-800 dark:text-slate-200 truncate">{p.name}</p>
                          <div className="mt-1 flex flex-wrap gap-1">
                            {(p.tags || []).slice(0, 3).map((t) => (
                              <span key={t} className="rounded-md bg-surface-secondary dark:bg-slate-800 px-1.5 py-0.5 text-xs text-slate-500 dark:text-slate-400">{t}</span>
                            ))}
                            {p.source === 'image' && <span className="rounded-md bg-purple-50 dark:bg-purple-900/30 px-1.5 py-0.5 text-xs text-purple-500 dark:text-purple-300">📸 图片识别</span>}
                          </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-all group-hover:opacity-100">
                          <button onClick={() => addToItinerary(p.name, p.city)} className="rounded-lg p-1 text-slate-300 dark:text-slate-600 hover:bg-brand-50 dark:hover:bg-brand-900/30 hover:text-brand-600 dark:hover:text-brand-400" title="添加到行程">
                            <PlusCircle size={14} />
                          </button>
                          <button onClick={() => removePlace(p.id)} className="rounded-lg p-1 text-slate-300 dark:text-slate-600 hover:bg-red-50 dark:hover:bg-red-900/30 hover:text-red-500 dark:hover:text-red-400" title="删除">
                            <Trash2 size={14} />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Footer */}
        <div className="border-t border-border-light px-4 py-2.5 text-center text-xs text-slate-400 dark:text-slate-500">
          💡 AI 对话会自动感知收藏的地点并排进行程
        </div>
      </div>
    </>
  )
}
