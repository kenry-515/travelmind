/**
 * TravelMind Agent — DayCard Component
 *
 * Renders a single day of a trip itinerary: header, timeline items,
 * optional regeneration input, dining and accommodation cards.
 */

import { useState } from 'react'
import { Clock, Loader2, MapPin, RefreshCw, X, UtensilsCrossed, Plane, Train, Car, Bus, Hotel, Tent, Moon, Footprints, ArrowUp, ArrowDown, Edit3, MoveRight, DollarSign, Check } from 'lucide-react'
import type { TripDay } from '../lib/api'
import { PriceBadge } from './PriceBadge'

/** 扩展的行程项目接口（包含新增的精细字段） */
interface ItineraryItem {
  time: string
  poi: string
  note?: string
  time_slot?: 'morning' | 'afternoon' | 'evening' | 'night'
  transportation?: string | null
  estimated_cost?: {
    ticket?: number
    transport?: number
    total?: number
  } | null
  price_range?: { min?: number; max?: number } | null
  price_source?: string
  booking_url?: string
  /** 内部标记：是否由 eat/stay 字段合成而来 */
  _synthetic?: boolean
  /** 合成项的子类型：lunch/dinner/snack/stay */
  _subType?: 'lunch' | 'dinner' | 'snack' | 'stay'
}

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
  /** 单项删除（Phase 12.27）：传了才显示删除按钮 */
  onRemoveItem?: (itemIndex: number) => void
  /** Phase 14: 上移/下移 */
  onMoveItem?: (itemIndex: number, direction: 'up' | 'down') => void
  /** Phase 14: 编辑项目名称 */
  onEditItem?: (itemIndex: number, newName: string) => void
  /** Phase 14: 全部项目数（用于判断可否上下移动） */
  totalItems?: number
}

/** 根据 note 开头标记获取对应的图标和颜色
 *  优先级：显式标记 > 合成子类型（从 eat/stay 合成的 lunch/dinner/stay）> POI 文本关键字推断 > 默认
 */
function getItemStyle(note: string, subType?: ItineraryItem['_subType'], poi?: string) {
  // 1. 显式 [吃] [住] [休] [行] [景] [到] 标记优先
  if (note?.startsWith?.('[吃]')) return { icon: UtensilsCrossed, color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-900/20', border: 'border-amber-300 dark:border-amber-700/50' }
  if (note?.startsWith?.('[景]')) return { icon: MapPin, color: 'text-brand-600 dark:text-brand-400', bg: 'bg-brand-50/60 dark:bg-brand-900/20', border: 'border-brand-300 dark:border-brand-700/50' }
  if (note?.startsWith?.('[休]')) return { icon: Moon, color: 'text-indigo-600 dark:text-indigo-400', bg: 'bg-indigo-50 dark:bg-indigo-900/20', border: 'border-indigo-300 dark:border-indigo-700/50' }
  if (note?.startsWith('[行]')) {
    const lower = note.toLowerCase()
    if (lower.includes('飞机') || lower.includes('机场') || lower.includes('✈')) return { icon: Plane, color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/20', border: 'border-blue-300 dark:border-blue-700/50' }
    if (lower.includes('高铁') || lower.includes('火车') || lower.includes('🚄') || lower.includes('🚂')) return { icon: Train, color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/20', border: 'border-blue-300 dark:border-blue-700/50' }
    if (lower.includes('公交') || lower.includes('巴士') || lower.includes('🚌')) return { icon: Bus, color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/20', border: 'border-blue-300 dark:border-blue-700/50' }
    if (lower.includes('自驾') || lower.includes('开车') || lower.includes('🚗')) return { icon: Car, color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/20', border: 'border-blue-300 dark:border-blue-700/50' }
    return { icon: Plane, color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/20', border: 'border-blue-300 dark:border-blue-700/50' }
  }
  if (note?.startsWith('[住]')) {
    const lower = note.toLowerCase()
    if (lower.includes('民宿')) return { icon: Tent, color: 'text-purple-600 dark:text-purple-400', bg: 'bg-purple-50 dark:bg-purple-900/20', border: 'border-purple-300 dark:border-purple-700/50' }
    if (lower.includes('青旅') || lower.includes('青年旅舍')) return { icon: Tent, color: 'text-purple-600 dark:text-purple-400', bg: 'bg-purple-50 dark:bg-purple-900/20', border: 'border-purple-300 dark:border-purple-700/50' }
    return { icon: Hotel, color: 'text-purple-600 dark:text-purple-400', bg: 'bg-purple-50 dark:bg-purple-900/20', border: 'border-purple-300 dark:border-purple-700/50' }
  }
  if (note?.startsWith('[到]')) return { icon: Footprints, color: 'text-slate-600 dark:text-slate-400', bg: 'bg-slate-50 dark:bg-slate-800/40', border: 'border-slate-300 dark:border-slate-600' }

  // 2. 合成项的子类型（来自 eat/stay 字段解析）
  if (subType === 'lunch' || subType === 'dinner' || subType === 'snack') {
    return { icon: UtensilsCrossed, color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-900/20', border: 'border-amber-300 dark:border-amber-700/50' }
  }
  if (subType === 'stay') {
    return { icon: Hotel, color: 'text-purple-600 dark:text-purple-400', bg: 'bg-purple-50 dark:bg-purple-900/20', border: 'border-purple-300 dark:border-purple-700/50' }
  }

  // 3. 关键字智能推断（兜底，应对 LLM 忘记写前缀的情况）
  const combined = `${poi || ''}${note || ''}`
  const hasFoodKeyword =
    /(火锅|烧烤|餐厅|饭店|菜馆|食堂|餐|吃|面|粉|饭|咖啡|奶茶|甜品|小吃|料理|茶|酒|宴|楼|店|馆|bar|cafe|coffee)/i.test(combined) ||
    /(餐|吃|午|晚|早)/.test(note?.slice(0, 12) || '')
  const hasLodgingKeyword = /(酒店|宾馆|民宿|客栈|住宿|入住|旅馆|青旅|motel|inn|hotel)/i.test(combined)
  const hasRestKeyword = /(午休|休息|自由活动|午睡|小憩|睡)/.test(note || '')
  const hasTransportKeyword = /(高铁|飞机|火车|打车|公交|地铁|自驾|航班|出发|前往|到达|机场|车站)/.test(combined)

  if (hasLodgingKeyword) {
    if (/(民宿|青旅|帐篷|露营)/.test(combined)) return { icon: Tent, color: 'text-purple-600 dark:text-purple-400', bg: 'bg-purple-50 dark:bg-purple-900/20', border: 'border-purple-300 dark:border-purple-700/50' }
    return { icon: Hotel, color: 'text-purple-600 dark:text-purple-400', bg: 'bg-purple-50 dark:bg-purple-900/20', border: 'border-purple-300 dark:border-purple-700/50' }
  }
  if (hasFoodKeyword) return { icon: UtensilsCrossed, color: 'text-amber-600 dark:text-amber-400', bg: 'bg-amber-50 dark:bg-amber-900/20', border: 'border-amber-300 dark:border-amber-700/50' }
  if (hasRestKeyword) return { icon: Moon, color: 'text-indigo-600 dark:text-indigo-400', bg: 'bg-indigo-50 dark:bg-indigo-900/20', border: 'border-indigo-300 dark:border-indigo-700/50' }
  if (hasTransportKeyword) return { icon: Train, color: 'text-blue-600 dark:text-blue-400', bg: 'bg-blue-50 dark:bg-blue-900/20', border: 'border-blue-300 dark:border-blue-700/50' }

  return { icon: MapPin, color: 'text-brand-600 dark:text-brand-400', bg: 'bg-brand-50/60 dark:bg-brand-900/20', border: 'border-brand-300 dark:border-brand-700/50' }
}

/** 时间段配置 — 使用通用标识（Clock/标签），避免太阳/月亮与午晚餐冲突 */
const TIME_SLOT_CONFIG: Record<string, { label: string; icon: typeof Clock; color: string; bg: string }> = {
  morning:   { label: '上午', icon: Clock, color: 'text-sky-600 dark:text-sky-400',     bg: 'bg-sky-50 dark:bg-sky-900/20' },
  afternoon: { label: '下午', icon: Clock, color: 'text-emerald-600 dark:text-emerald-400', bg: 'bg-emerald-50 dark:bg-emerald-900/20' },
  evening:   { label: '傍晚', icon: Clock, color: 'text-violet-600 dark:text-violet-400',  bg: 'bg-violet-50 dark:bg-violet-900/20' },
  night:     { label: '夜间', icon: Clock, color: 'text-indigo-500 dark:text-indigo-400',  bg: 'bg-indigo-50 dark:bg-indigo-900/20' },
}

/** 根据时间自动推断时间段 */
function inferTimeSlot(time: string): 'morning' | 'afternoon' | 'evening' | 'night' {
  const hour = parseInt(time.split(':')[0], 10)
  if (hour < 12) return 'morning'
  if (hour < 18) return 'afternoon'
  if (hour < 21) return 'evening'
  return 'night'
}

/** 去掉类型标记显示纯文本 */
function cleanNote(note: string) {
  if (!note) return ''
  return note.replace(/^\[(景|吃|休|行|住|到)\]/, '').trim()
}

/** 解析 eat 文本为结构化的餐饮卡片数据 */
interface DiningCard {
  type: 'lunch' | 'dinner' | 'snack'
  name: string
  recommendation?: string
  tag?: string
}

function parseEatText(eat: string): DiningCard[] {
  if (!eat) return []
  
  const cards: DiningCard[] = []
  const text = eat.trim()
  
  // 移除 "AI推荐:" 前缀
  const cleanText = text.replace(/AI推荐[:：]\s*/g, '').trim()
  
  // 模式1: 午餐「XXX」· 晚餐「YYY」 格式（KB 挂载）
  // 模式2: 午餐：XXX，推荐...；晚餐：YYY 格式（LLM 生成）
  // 模式3: 混合格式
  
  // 尝试匹配午餐
  const lunchPatterns = [
    /午餐[「"]([^」"]+)[」"][:：]?\s*(推荐[^\s·]*)?/,
    /午餐[:：]\s*([^；;·]+?)(?:[；;·]|$)/,
  ]
  
  // 尝试匹配晚餐
  const dinnerPatterns = [
    /晚餐[「"]([^」"]+)[」"][:：]?\s*(推荐[^\s·]*)?/,
    /晚餐[:：]\s*([^；;·]+?)(?:[；;·]|$)/,
  ]
  
  // 尝试匹配小吃/点心
  const snackPatterns = [
    /(?:小吃|点心|下午茶)[「"]([^」"]+)[」"]/,
  ]
  
  for (const pattern of lunchPatterns) {
    const match = cleanText.match(pattern)
    if (match) {
      cards.push({
        type: 'lunch',
        name: match[1].trim(),
        recommendation: match[2]?.trim(),
        tag: '午餐',
      })
      break
    }
  }
  
  for (const pattern of dinnerPatterns) {
    const match = cleanText.match(pattern)
    if (match) {
      cards.push({
        type: 'dinner',
        name: match[1].trim(),
        recommendation: match[2]?.trim(),
        tag: '晚餐',
      })
      break
    }
  }
  
  for (const pattern of snackPatterns) {
    const match = cleanText.match(pattern)
    if (match) {
      cards.push({
        type: 'snack',
        name: match[1].trim(),
        tag: '小吃',
      })
      break
    }
  }
  
  // 如果没有结构化解析成功，将整个文本作为单一卡片
  if (cards.length === 0 && cleanText) {
    // 尝试简单拆分
    const parts = cleanText.split(/[·；;]/).map(s => s.trim()).filter(Boolean)
    for (const part of parts) {
      if (part.includes('午餐') || part.includes('中')) {
        cards.push({ type: 'lunch', name: part, tag: '午餐' })
      } else if (part.includes('晚餐') || part.includes('晚')) {
        cards.push({ type: 'dinner', name: part, tag: '晚餐' })
      } else {
        cards.push({ type: 'snack', name: part, tag: '推荐' })
      }
    }
  }
  
  return cards
}

/** 餐饮卡片样式（保留以备将来扩展，目前未使用以避免 lint 警告） */

export function DayCard({
  day,
  icon,
  regenOpen,
  regenBusy,
  regenText,
  onRegenOpen,
  onRegenClose,
  onRegenText,
  onRegenSubmit,
  onRemoveItem,
  onMoveItem,
  onEditItem,
  totalItems,
}: DayCardProps) {
  // 解析餐饮数据
  const diningCards = parseEatText(day.eat || '')

  // ── 合并 items + eatCards + stayCard 为统一日程，并按时间排序 ──
  // Phase 18 CI fix: tsc 6.0.2 excess-property check 让 diningCards/stayCard 的
  // object literal push 报错(缺 price_range/time_slot 等必填字段)。用宽松类型。
  type MergedItem = ItineraryItem & {
    _originalIndex?: number
    _synthetic?: boolean
    _subType?: 'lunch' | 'dinner' | 'snack' | 'stay'
  }
  const mergedItems: MergedItem[] = []

  // 1. 先把原始 items 放入，记录原始索引，用于 onMoveItem/onEditItem/onRemoveItem 回调
  ;(day.items || []).forEach((item, idx) => {
    mergedItems.push({ ...(item as ItineraryItem), _originalIndex: idx })
  })

  // 检查 items 中是否已经有同名餐厅（LLM 可能已写入），避免重复渲染
  const existingItemNames = new Set(
    mergedItems.map((it) => (it.poi || '').replace(/\s/g, '').toLowerCase())
  )

  // 2. 将 day.eat 餐饮卡片按语义时间合成
  diningCards.forEach((dining) => {
    const normalizedName = dining.name.replace(/\s/g, '').toLowerCase()
    // 如果同名餐厅已经在 items 里了，不再合成（用 items 已有的样式+时间）
    if (
      existingItemNames.has(normalizedName) ||
      [...existingItemNames].some((n) => n.includes(normalizedName) || normalizedName.includes(n))
    ) {
      return
    }
    // 语义时间：午餐 12:00、下午茶 15:00、晚餐 18:30
    const time = dining.type === 'lunch' ? '12:00' : dining.type === 'dinner' ? '18:30' : '15:00'
    mergedItems.push({
      time,
      poi: dining.name,
      note: dining.recommendation ? `[吃]${dining.recommendation}` : '[吃]当日餐饮推荐',
      _synthetic: true,
      _subType: dining.type,
    } as MergedItem)
  })

  // 3. 将 day.stay 住宿合成（通常是夜间）
  if (day.stay) {
    const normalizedStay = (day.stay || '').replace(/\s/g, '').toLowerCase()
    const alreadyInItems = [...existingItemNames].some(
      (n) => n.includes(normalizedStay) || normalizedStay.includes(n)
    )
    if (!alreadyInItems) {
      mergedItems.push({
        time: '21:30',
        poi: day.stay,
        note: '[住]入住当日酒店，休整过夜',
        _synthetic: true,
        _subType: 'stay',
      } as MergedItem)
    }
  }

  // 4. 按时间排序（解决时间乱序、午晚餐被排到最下的问题）
  const timeToMinutes = (t: string) => {
    const [h, m] = t.split(':').map((x) => parseInt(x, 10))
    return (isNaN(h) ? 12 : h) * 60 + (isNaN(m) ? 0 : m)
  }
  mergedItems.sort((a, b) => timeToMinutes(a.time) - timeToMinutes(b.time))

  // 真实可编辑/删除项目数（不含合成项）
  const realTotal = totalItems ?? day.items?.length ?? 0

  // Phase 16.4: 内联编辑状态（替代旧的 DOM 操作）
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  const [editValue, setEditValue] = useState('')
  // Phase 16.4: 删除确认状态（二次点击确认）
  const [confirmingRemove, setConfirmingRemove] = useState<number | null>(null)

  function startEdit(index: number, currentName: string) {
    setEditingIndex(index)
    setEditValue(currentName)
  }

  function commitEdit(mergedIdx: number) {
    const trimmed = editValue.trim()
    if (trimmed && onEditItem) {
      const orig = mergedItems[mergedIdx]._originalIndex
      if (orig !== undefined) onEditItem(orig, trimmed)
    }
    setEditingIndex(null)
    setEditValue('')
  }

  function cancelEdit() {
    setEditingIndex(null)
    setEditValue('')
  }

  function handleRemoveClick(mergedIdx: number) {
    const orig = mergedItems[mergedIdx]._originalIndex
    if (orig === undefined) return // 合成项不允许删除
    if (confirmingRemove === mergedIdx) {
      onRemoveItem?.(orig)
      setConfirmingRemove(null)
    } else {
      setConfirmingRemove(mergedIdx)
      setTimeout(() => setConfirmingRemove((prev) => (prev === mergedIdx ? null : prev)), 3000)
    }
  }

  // 判断 merged 项是否可以上移/下移（基于真实 items 的索引）
  function canMove(mergedIdx: number, dir: 'up' | 'down') {
    const orig = mergedItems[mergedIdx]._originalIndex
    if (orig === undefined) return false
    if (dir === 'up') return orig > 0
    return orig < realTotal - 1
  }

  function doMove(mergedIdx: number, dir: 'up' | 'down') {
    const orig = mergedItems[mergedIdx]._originalIndex
    if (orig === undefined) return
    onMoveItem?.(orig, dir)
  }
  
  return (
    <div className="card animate-fade-in-up overflow-hidden">
      {/* Day header — 渐变横幅 */}
      <div className="flex items-center gap-3 border-b border-border-light bg-gradient-to-r from-brand-100/70 via-brand-50/50 to-accent-50/40 dark:from-slate-800/70 dark:via-slate-900/50 dark:to-slate-800/40 px-5 py-4">
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-brand-400 to-brand-600 text-base font-bold text-white shadow-pop">
          {day.day}
        </span>
        <div className="flex-1">
          <h3 className="font-bold text-slate-900 dark:text-slate-100">
            {icon} {day.title}
          </h3>
          <p className="text-xs text-slate-400 dark:text-slate-500">{day.theme}</p>
        </div>
        <button
          onClick={regenOpen ? onRegenClose : onRegenOpen}
          className="flex items-center gap-1 rounded-xl px-2 py-1.5 text-xs text-slate-400 dark:text-slate-500 transition-colors hover:bg-brand-50 dark:hover:bg-brand-900/30 hover:text-brand-600 dark:hover:text-brand-400"
          aria-label="重新安排这一天"
        >
          <RefreshCw size={13} />
          重新安排
        </button>
      </div>

      {/* Partial regeneration input */}
      {regenOpen && (
        <div className="animate-fade-in border-b border-border-light bg-brand-50/50 dark:bg-slate-800/30 px-5 py-3">
          <div className="flex gap-2">
            <input
              type="text"
              value={regenText}
              onChange={(e) => onRegenText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && onRegenSubmit()}
              placeholder="说说哪里不满意，如：太赶了 / 想多去博物馆"
              className="flex-1 rounded-xl border border-border bg-white dark:bg-slate-900 px-3 py-2 text-sm focus:border-brand-400 dark:focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-100 dark:focus:ring-brand-900/40"
              autoFocus
            />
            <button
              onClick={onRegenSubmit}
              disabled={regenBusy || !regenText.trim()}
              className="btn-primary px-4 py-2 text-sm"
            >
              {regenBusy && <Loader2 size={14} className="animate-spin" />}
              {regenBusy ? '生成中' : '重排'}
            </button>
          </div>
          <p className="mt-1.5 text-xs text-slate-400 dark:text-slate-500">
            只重新生成这一天，其他天保持不变
          </p>
        </div>
      )}

      {/* Timeline items — 贯通脊柱 + 节点卡片 */}
      <div className="px-5 py-4">
        <h4 className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
          <MapPin size={14} />
          行程安排
        </h4>
        <div className="relative">
          {/* 时间轴脊柱（贯穿全部节点） */}
          <div
            aria-hidden
            className="absolute bottom-3 left-[4.55rem] top-2 w-0.5 bg-gradient-to-b from-brand-200 via-brand-100 to-transparent dark:from-slate-700 dark:via-slate-800 dark:to-transparent"
          />
          <div className="space-y-2.5">
            {/* 统一渲染：items + 餐饮 + 住宿，已按时间排序且去重 */}
            {mergedItems.map((item, i) => {
              const timeSlot = item.time_slot || inferTimeSlot(item.time)
              const slotConfig = TIME_SLOT_CONFIG[timeSlot]
              const style = getItemStyle(item.note || '', item._subType, item.poi)
              const Icon = style.icon
              const isEditing = editingIndex === i
              const isConfirmingRemove = confirmingRemove === i
              const isSynthetic = !!item._synthetic

              // 时刻颜色：根据类型着色，比单一品牌色更直观
              const timeColorClass =
                item._subType === 'stay'
                  ? 'text-purple-600 dark:text-purple-400'
                  : item._subType === 'lunch' || item._subType === 'dinner' || item._subType === 'snack' ||
                    style.color.includes('amber')
                  ? 'text-amber-600 dark:text-amber-400'
                  : 'text-brand-600 dark:text-brand-400'
              const timeClockClass =
                item._subType === 'stay'
                  ? 'text-purple-400 dark:text-purple-300'
                  : item._subType === 'lunch' || item._subType === 'dinner' || item._subType === 'snack' ||
                    style.color.includes('amber')
                  ? 'text-amber-400 dark:text-amber-300'
                  : 'text-brand-400 dark:text-brand-300'

              // 合成项额外的子类型标签（午餐/晚餐/小吃/住宿）
              let subTag: { text: string; cls: string } | null = null
              if (isSynthetic && item._subType === 'lunch') subTag = { text: '午餐', cls: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300' }
              else if (isSynthetic && item._subType === 'dinner') subTag = { text: '晚餐', cls: 'bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300' }
              else if (isSynthetic && item._subType === 'snack') subTag = { text: '小吃', cls: 'bg-yellow-100 dark:bg-yellow-900/30 text-yellow-700 dark:text-yellow-300' }
              else if (isSynthetic && item._subType === 'stay') subTag = { text: '住宿', cls: 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300' }
              // 真实 items 里若能从 note 关键字判断出是餐饮/住宿，也给个标签，避免样式混乱
              else if (item.note?.startsWith('[吃]')) subTag = { text: '用餐', cls: 'bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300' }
              else if (item.note?.startsWith('[住]')) subTag = { text: '住宿', cls: 'bg-purple-100 dark:bg-purple-900/30 text-purple-700 dark:text-purple-300' }
              else if (item.note?.startsWith('[休]')) subTag = { text: '休息', cls: 'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300' }
              else if (item.note?.startsWith('[行]')) subTag = { text: '交通', cls: 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300' }
              else if (item.note?.startsWith('[到]')) subTag = { text: '到达', cls: 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300' }

              return (
                <div key={`${item.time}-${i}-${item.poi}`} className="relative flex items-start gap-3">
                  {/* 时刻 */}
                  <p className={`flex w-14 shrink-0 items-center justify-end gap-1 pt-2.5 text-xs font-semibold tabular-nums ${timeColorClass}`}>
                    <Clock size={11} className={timeClockClass} />
                    {item.time}
                  </p>
                  {/* 节点 - 根据类型变色 */}
                  <span className={`relative z-10 mt-2.5 h-3 w-3 shrink-0 rounded-full border-2 ${style.border} bg-white dark:bg-slate-900 shadow-sm`} />
                  {/* 内容卡 - 统一用 getItemStyle 的 bg/border，保持所有卡片风格一致 */}
                  <div
                    className={`group/item relative min-w-0 flex-1 rounded-xl border ${
                      style.border
                    } ${
                      isConfirmingRemove ? 'bg-red-50 dark:bg-red-900/20 border-red-300 dark:border-red-700' : style.bg
                    } p-3 transition-colors ${
                      !isSynthetic ? 'hover:border-brand-200 dark:hover:border-brand-700 hover:bg-brand-50/40 dark:hover:bg-brand-900/20' : 'hover:shadow-sm'
                    }`}
                  >
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <Icon size={14} className={style.color} />
                      {isEditing ? (
                        <input
                          type="text"
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') commitEdit(i)
                            if (e.key === 'Escape') cancelEdit()
                          }}
                          onBlur={() => commitEdit(i)}
                          autoFocus
                          className="flex-1 rounded-lg border border-brand-300 bg-white dark:bg-slate-900 px-2 py-0.5 text-sm font-semibold text-slate-800 dark:text-slate-200 outline-none focus:ring-2 focus:ring-brand-100 dark:focus:ring-brand-900/40"
                          aria-label="修改项目名称"
                        />
                      ) : (
                        <span className="text-sm font-semibold text-slate-800 dark:text-slate-200">{item.poi}</span>
                      )}
                      {/* 时间段标签 */}
                      <span className={`ml-1 rounded-md px-1.5 py-0.5 text-[10px] font-medium ${slotConfig.bg} ${slotConfig.color}`}>
                        {slotConfig.label}
                      </span>
                      {/* 子类型标签（午餐/晚餐/住宿...） */}
                      {subTag && (
                        <span className={`rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${subTag.cls}`}>
                          {subTag.text}
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-slate-500 dark:text-slate-400">{cleanNote(item.note || '')}</p>

                    {/* 交通建议 */}
                    {item._originalIndex !== undefined && item._originalIndex > 0 && item.transportation && (
                      <div className="mt-1.5 flex items-center gap-1 text-[11px] text-slate-400 dark:text-slate-500">
                        <MoveRight size={11} className="text-slate-300 dark:text-slate-600" />
                        <span>{item.transportation}</span>
                      </div>
                    )}

                    {/* 预估费用 */}
                    {item.estimated_cost && (item.estimated_cost.ticket || item.estimated_cost.total) ? (
                      <div className="mt-1.5 flex items-center gap-2 text-[11px] text-slate-400 dark:text-slate-500">
                        <DollarSign size={11} className="text-slate-300 dark:text-slate-600" />
                        {item.estimated_cost.ticket !== undefined && (
                          <span>门票 ¥{item.estimated_cost.ticket}</span>
                        )}
                        {item.estimated_cost.transport !== undefined && (
                          <span>交通 ¥{item.estimated_cost.transport}</span>
                        )}
                        {item.estimated_cost.total !== undefined && (
                          <span className="font-medium text-slate-500 dark:text-slate-400">合计 ¥{item.estimated_cost.total}</span>
                        )}
                      </div>
                    ) : null}

                    <PriceBadge item={item} />

                    {/* 操作栏：只有真实 items 才能编辑/移动/删除，合成项不提供 */}
                    {!isSynthetic && !isEditing && onMoveItem !== undefined && onEditItem !== undefined && onRemoveItem !== undefined && (
                      <div className="absolute right-2 top-2 flex items-center gap-0.5 opacity-0 transition-all group-hover/item:opacity-100">
                        {canMove(i, 'up') && (
                          <button onClick={() => doMove(i, 'up')} className="rounded-lg p-1 text-slate-300 dark:text-slate-600 hover:bg-brand-50 dark:hover:bg-brand-900/30 hover:text-brand-600 dark:hover:text-brand-400" title="上移" aria-label="上移">
                            <ArrowUp size={13} />
                          </button>
                        )}
                        {canMove(i, 'down') && (
                          <button onClick={() => doMove(i, 'down')} className="rounded-lg p-1 text-slate-300 dark:text-slate-600 hover:bg-brand-50 dark:hover:bg-brand-900/30 hover:text-brand-600 dark:hover:text-brand-400" title="下移" aria-label="下移">
                            <ArrowDown size={13} />
                          </button>
                        )}
                        <button
                          onClick={() => startEdit(i, item.poi)}
                          className="rounded-lg p-1 text-slate-300 dark:text-slate-600 hover:bg-amber-50 dark:hover:bg-amber-900/30 hover:text-amber-500 dark:hover:text-amber-400"
                          title="编辑"
                          aria-label="编辑"
                        >
                          <Edit3 size={13} />
                        </button>
                        {realTotal > 1 && (
                          <button
                            onClick={() => handleRemoveClick(i)}
                            className={`rounded-lg p-1 transition-colors ${isConfirmingRemove ? 'bg-red-100 dark:bg-red-900/30 text-red-500 dark:text-red-400' : 'text-slate-300 dark:text-slate-600 hover:bg-red-50 dark:hover:bg-red-900/30 hover:text-red-500 dark:hover:text-red-400'}`}
                            title={isConfirmingRemove ? '再点一次确认删除' : `去掉${item.poi}`}
                            aria-label={isConfirmingRemove ? '确认删除' : `去掉${item.poi}`}
                          >
                            {isConfirmingRemove ? <Check size={14} /> : <X size={14} />}
                          </button>
                        )}
                      </div>
                    )}
                    {!isSynthetic && isEditing && (
                      <div className="absolute right-2 top-2 flex items-center gap-0.5">
                        <button onClick={() => commitEdit(i)} className="rounded-lg p-1 text-green-500 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-900/30" title="确认" aria-label="确认修改">
                          <Check size={14} />
                        </button>
                        <button onClick={cancelEdit} className="rounded-lg p-1 text-slate-400 dark:text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" title="取消" aria-label="取消修改">
                          <X size={14} />
                        </button>
                      </div>
                    )}
                    {isConfirmingRemove && !isSynthetic && (
                      <p className="mt-1 text-[11px] font-medium text-red-500">
                        再点一次 ✕ 确认删除「{item.poi}」
                      </p>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}
