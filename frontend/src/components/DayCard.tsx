/**
 * TravelMind Agent — DayCard Component
 *
 * Renders a single day of a trip itinerary: header, timeline items,
 * optional regeneration input, and daily food recommendation.
 */

import { Clock, Coffee, BedDouble, Loader2, MapPin, RefreshCw, X, UtensilsCrossed, Plane, Train, Car, Bus, Hotel, Tent, Moon, Footprints, ArrowUp, ArrowDown, Edit3 } from 'lucide-react'
import type { TripDay } from '../lib/api'
import { PriceBadge } from './PriceBadge'

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

/** 根据 note 开头标记获取对应的图标和颜色 */
function getItemStyle(note: string) {
  if (!note) return { icon: MapPin, color: 'text-brand-600', bg: 'bg-brand-100', border: 'border-brand-400' }
  if (note.startsWith('[吃]')) return { icon: UtensilsCrossed, color: 'text-amber-600', bg: 'bg-amber-100', border: 'border-amber-400' }
  if (note.startsWith('[景]')) return { icon: MapPin, color: 'text-brand-600', bg: 'bg-brand-100', border: 'border-brand-400' }
  if (note.startsWith('[休]')) return { icon: Moon, color: 'text-indigo-600', bg: 'bg-indigo-100', border: 'border-indigo-400' }
  if (note.startsWith('[行]')) {
    const lower = note.toLowerCase()
    if (lower.includes('飞机') || lower.includes('机场') || lower.includes('✈')) return { icon: Plane, color: 'text-blue-600', bg: 'bg-blue-100', border: 'border-blue-400' }
    if (lower.includes('高铁') || lower.includes('火车') || lower.includes('🚄') || lower.includes('🚂')) return { icon: Train, color: 'text-blue-600', bg: 'bg-blue-100', border: 'border-blue-400' }
    if (lower.includes('公交') || lower.includes('巴士') || lower.includes('🚌')) return { icon: Bus, color: 'text-blue-600', bg: 'bg-blue-100', border: 'border-blue-400' }
    if (lower.includes('自驾') || lower.includes('开车') || lower.includes('🚗')) return { icon: Car, color: 'text-blue-600', bg: 'bg-blue-100', border: 'border-blue-400' }
    return { icon: Plane, color: 'text-blue-600', bg: 'bg-blue-100', border: 'border-blue-400' }
  }
  if (note.startsWith('[住]')) {
    const lower = note.toLowerCase()
    if (lower.includes('民宿')) return { icon: Tent, color: 'text-purple-600', bg: 'bg-purple-100', border: 'border-purple-400' }
    if (lower.includes('青旅') || lower.includes('青年旅舍')) return { icon: Tent, color: 'text-purple-600', bg: 'bg-purple-100', border: 'border-purple-400' }
    return { icon: Hotel, color: 'text-purple-600', bg: 'bg-purple-100', border: 'border-purple-400' }
  }
  if (note.startsWith('[到]')) return { icon: Footprints, color: 'text-slate-600', bg: 'bg-slate-100', border: 'border-slate-400' }
  return { icon: MapPin, color: 'text-brand-600', bg: 'bg-brand-100', border: 'border-brand-400' }
}

/** 去掉类型标记显示纯文本 */
function cleanNote(note: string) {
  if (!note) return ''
  return note.replace(/^\[(景|吃|休|行|住|到)\]/, '').trim()
}

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
  return (
    <div className="card animate-fade-in-up overflow-hidden">
      {/* Day header — 渐变横幅 */}
      <div className="flex items-center gap-3 border-b border-border-light bg-gradient-to-r from-brand-100/70 via-brand-50/50 to-accent-50/40 px-5 py-4">
        <span className="flex h-10 w-10 items-center justify-center rounded-full bg-gradient-to-br from-brand-400 to-brand-600 text-base font-bold text-white shadow-pop">
          {day.day}
        </span>
        <div className="flex-1">
          <h3 className="font-bold text-slate-900">
            {icon} {day.title}
          </h3>
          <p className="text-xs text-slate-400">{day.theme}</p>
        </div>
        <button
          onClick={regenOpen ? onRegenClose : onRegenOpen}
          className="flex items-center gap-1 rounded-xl px-2 py-1.5 text-xs text-slate-400 transition-colors hover:bg-brand-50 hover:text-brand-600"
          aria-label="重新安排这一天"
        >
          <RefreshCw size={13} />
          重新安排
        </button>
      </div>

      {/* Partial regeneration input */}
      {regenOpen && (
        <div className="animate-fade-in border-b border-border-light bg-brand-50/50 px-5 py-3">
          <div className="flex gap-2">
            <input
              type="text"
              value={regenText}
              onChange={(e) => onRegenText(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && onRegenSubmit()}
              placeholder="说说哪里不满意，如：太赶了 / 想多去博物馆"
              className="flex-1 rounded-xl border border-border bg-white px-3 py-2 text-sm focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
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
          <p className="mt-1.5 text-xs text-slate-400">
            只重新生成这一天，其他天保持不变
          </p>
        </div>
      )}

      {/* Timeline items — 贯通脊柱 + 节点卡片 */}
      <div className="px-5 py-4">
        <h4 className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-slate-400">
          <MapPin size={14} />
          景点安排
        </h4>
        <div className="relative">
          {/* 时间轴脊柱（贯穿全部节点） */}
          <div
            aria-hidden
            className="absolute bottom-3 left-[4.55rem] top-2 w-0.5 bg-gradient-to-b from-brand-200 via-brand-100 to-transparent"
          />
          <div className="space-y-2.5">
            {day.items.map((item, i) => (
              <div key={`${item.time}-${i}`} className="relative flex items-start gap-3">
                {/* 时刻 */}
                <p className="flex w-14 shrink-0 items-center justify-end gap-1 pt-2.5 text-xs font-semibold tabular-nums text-brand-600">
                  <Clock size={11} className="text-brand-400" />
                  {item.time}
                </p>
                {/* 节点 - 根据类型变色 */}
                <span className={`relative z-10 mt-2.5 h-3 w-3 shrink-0 rounded-full border-2 ${getItemStyle(item.note || '').border} bg-white shadow-sm`} />
                {/* 内容卡 - 根据类型带图标 */}
                <div className={`group/item relative min-w-0 flex-1 rounded-xl border ${getItemStyle(item.note || '').border.replace('border-', 'border-').replace('-400', '-200')} ${getItemStyle(item.note || '').bg.replace('bg-', 'bg-').replace('-100', '-30/50')} p-3 transition-colors hover:border-brand-200 hover:bg-brand-50/40`}>
                  <p className="flex items-center gap-1.5 text-sm font-semibold text-slate-800">
                    {(() => { const s = getItemStyle(item.note || ''); const Icon = s.icon; return <Icon size={14} className={s.color} />; })()}
                    {item.poi}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-slate-500">{cleanNote(item.note || '')}</p>
                  <PriceBadge item={item} />
                  {/* Phase 14: 编辑/上下移动/删除操作栏 */}
                  <div className="absolute right-2 top-2 flex items-center gap-0.5 opacity-0 transition-all group-hover/item:opacity-100">
                    {onMoveItem && i > 0 && (
                      <button onClick={() => onMoveItem(i, 'up')} className="rounded-lg p-1 text-slate-300 hover:bg-brand-50 hover:text-brand-600" title="上移" aria-label="上移">
                        <ArrowUp size={13} />
                      </button>
                    )}
                    {onMoveItem && totalItems && i < totalItems - 1 && (
                      <button onClick={() => onMoveItem(i, 'down')} className="rounded-lg p-1 text-slate-300 hover:bg-brand-50 hover:text-brand-600" title="下移" aria-label="下移">
                        <ArrowDown size={13} />
                      </button>
                    )}
                    {onEditItem && (
                      <button onClick={() => {
                        const input = document.createElement('input')
                        input.type = 'text'
                        input.value = item.poi
                        input.className = 'fixed inset-0 z-50 m-auto h-10 w-64 rounded-xl border border-brand-300 bg-white px-4 text-sm shadow-lg outline-none'
                        input.style.top = '50%'
                        input.style.transform = 'translateY(-50%)'
                        input.setAttribute('aria-label', '修改项目名称')
                        const overlay = document.createElement('div')
                        overlay.className = 'fixed inset-0 z-40 bg-black/20'
                        overlay.onclick = () => { overlay.remove(); input.remove() }
                        document.body.append(overlay, input)
                        input.focus()
                        input.select()
                        input.onkeydown = (e: KeyboardEvent) => {
                          if (e.key === 'Enter') { const v = input.value.trim(); if (v) onEditItem(i, v); overlay.remove(); input.remove() }
                          if (e.key === 'Escape') { overlay.remove(); input.remove() }
                        }
                      }} className="rounded-lg p-1 text-slate-300 hover:bg-amber-50 hover:text-amber-500" title="编辑" aria-label="编辑">
                        <Edit3 size={13} />
                      </button>
                    )}
                    {onRemoveItem && day.items.length > 1 && (
                      <button onClick={() => onRemoveItem(i)} className="rounded-lg p-1 text-slate-300 hover:bg-red-50 hover:text-red-500" title="删除" aria-label={`去掉${item.poi}`}>
                        <X size={14} />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 今日餐饮（KB 真实餐厅挂载） */}
      <div className="border-t border-border-light px-5 py-3">
        <p className="flex items-center gap-1.5 text-xs text-slate-500">
          <Coffee size={14} className="shrink-0 text-amber-500" />
          <span>
            <span className="font-semibold text-slate-600">今日餐饮：</span>
            {day.eat}
          </span>
        </p>
      </div>

      {/* 建议住宿（Phase 12.27，KB 有住宿数据时） */}
      {day.stay && (
        <div className="border-t border-border-light px-5 py-3">
          <p className="flex items-center gap-1.5 text-xs text-slate-500">
            <BedDouble size={14} className="shrink-0 text-accent-600" />
            <span>
              <span className="font-semibold text-slate-600">建议住宿：</span>
              {day.stay}
            </span>
          </p>
        </div>
      )}
    </div>
  )
}
