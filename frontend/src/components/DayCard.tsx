/**
 * TravelMind Agent — DayCard Component
 *
 * Renders a single day of a trip itinerary: header, timeline items,
 * optional regeneration input, and daily food recommendation.
 */

import { Clock, Coffee, BedDouble, Loader2, MapPin, RefreshCw, X } from 'lucide-react'
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
                {/* 节点 */}
                <span className="relative z-10 mt-2.5 h-3 w-3 shrink-0 rounded-full border-2 border-brand-400 bg-white shadow-sm" />
                {/* 内容卡 */}
                <div className="group/item relative min-w-0 flex-1 rounded-xl border border-border-light bg-surface-secondary p-3 transition-colors hover:border-brand-200 hover:bg-brand-50/40">
                  <p className="text-sm font-semibold text-slate-800">{item.poi}</p>
                  <p className="mt-1 text-xs leading-relaxed text-slate-500">{item.note}</p>
                  <PriceBadge item={item} />
                  {onRemoveItem && day.items.length > 1 && (
                    <button
                      onClick={() => onRemoveItem(i)}
                      aria-label={`去掉${item.poi}`}
                      title="去掉这个项目"
                      className="absolute right-2 top-2 rounded-lg p-1 text-slate-300 opacity-0 transition-all hover:bg-red-50 hover:text-red-500 group-hover/item:opacity-100"
                    >
                      <X size={14} />
                    </button>
                  )}
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
