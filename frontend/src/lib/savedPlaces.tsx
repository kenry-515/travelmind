/**
 * TravelMind Agent — SavedPlaces Context（Phase 14）
 *
 * 跨页面共享「想去的地点」池。用户可以在推荐页/图片页/对话页
 * 点击收藏，所有收藏 POI 在这里集中管理，可被 AI 对话感知、
 * 可被拖入行程编辑。
 */

import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'

export interface SavedPlace {
  id: string
  name: string
  city: string
  tags: string[]
  note: string
  source: 'recommend' | 'image' | 'chat' | 'manual'
  addedAt: string
}

interface SavedPlacesContextValue {
  places: SavedPlace[]
  addPlace: (place: Omit<SavedPlace, 'id' | 'addedAt'>) => void
  removePlace: (id: string) => void
  togglePlace: (place: Omit<SavedPlace, 'id' | 'addedAt'>) => void
  isSaved: (name: string, city: string) => boolean
  getPlacesForPrompt: (currentCity?: string) => string
  sharePlacesText: () => string
}

const SavedPlacesContext = createContext<SavedPlacesContextValue | null>(null)

const STORAGE_KEY = 'travelmind_saved_places'
const MAX_PLACES = 50

function loadSaved(): SavedPlace[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const places: SavedPlace[] = JSON.parse(raw)
      // Phase 15.5: Filter out auto-saved entries (source: 'chat') —
      // only keep user-confirmed favorites from recommend/image/manual pages.
      // 'chat' source entries were auto-saved by the buggy auto-favorite logic.
      const cleaned = places.filter(p => p.source !== 'chat')
      if (cleaned.length !== places.length) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(cleaned))
        console.info(`[SavedPlaces] Cleaned ${places.length - cleaned.length} auto-saved entries`)
      }
      return cleaned
    }
  } catch { /* ignore */ }
  return []
}

function genId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function now() {
  return new Date().toISOString()
}

export function SavedPlacesProvider({ children }: { children: ReactNode }) {
  const [places, setPlaces] = useState<SavedPlace[]>(loadSaved)

  // 持久化
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(places.slice(-MAX_PLACES)))
    } catch { /* quota exceeded — ignore */ }
  }, [places])

  const addPlace = useCallback((input: Omit<SavedPlace, 'id' | 'addedAt'>) => {
    setPlaces(prev => {
      // 去重检查
      const exists = prev.some(p => p.name === input.name && p.city === input.city)
      if (exists) return prev
      const newPlace: SavedPlace = { ...input, id: genId(), addedAt: now() }
      return [newPlace, ...prev]
    })
  }, [])

  const removePlace = useCallback((id: string) => {
    setPlaces(prev => prev.filter(p => p.id !== id))
  }, [])

  const togglePlace = useCallback((input: Omit<SavedPlace, 'id' | 'addedAt'>) => {
    setPlaces(prev => {
      const existing = prev.find(p => p.name === input.name && p.city === input.city)
      if (existing) return prev.filter(p => p.id !== existing.id)
      return [{ ...input, id: genId(), addedAt: now() }, ...prev]
    })
  }, [])

  const isSaved = useCallback((name: string, city: string) => {
    return places.some(p => p.name === name && p.city === city)
  }, [places])

  /** 生成给 AI Prompt 的文本（挂在对话 prompt 尾部）
   *  Phase 15.4: 按当前城市过滤收藏地点，避免跨城市污染。
   *  currentCity 为空时不附加（防止用旧收藏干扰新目的地）。
   */
  const getPlacesForPrompt = useCallback((currentCity?: string): string => {
    if (places.length === 0) return ''
    if (!currentCity) return ''
    const matched = places.filter(p => p.city === currentCity)
    if (matched.length === 0) return ''
    const lines = matched.map(p => `- ${p.name}（${p.city}）${p.note ? '—' + p.note : ''}`)
    return '\n【用户收藏的' + currentCity + '地点】\n' + lines.join('\n')
  }, [places])

  /** 生成可分享的纯文本 */
  const sharePlacesText = useCallback(() => {
    if (places.length === 0) return '我还没有收藏想去的地方～'
    const byCity = places.reduce<Record<string, string[]>>((acc, p) => {
      const c = p.city || '未分类'
      if (!acc[c]) acc[c] = []
      acc[c].push(p.name)
      return acc
    }, {})
    const lines = Object.entries(byCity).map(([city, names]) =>
      `📍 ${city}：${names.join('、')}`
    )
    return `🗺️ 我的旅行收藏清单\n${lines.join('\n')}\n\n—— 来自羊城智游`
  }, [places])

  return (
    <SavedPlacesContext value={{ places, addPlace, removePlace, togglePlace, isSaved, getPlacesForPrompt, sharePlacesText }}>
      {children}
    </SavedPlacesContext>
  )
}

export function useSavedPlaces() {
  const ctx = useContext(SavedPlacesContext)
  if (!ctx) throw new Error('useSavedPlaces must be used within SavedPlacesProvider')
  return ctx
}
