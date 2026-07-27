/**
 * TravelMind Agent — PlaceCard Component
 *
 * Card displaying a recommended attraction with:
 * - Name, city, score
 * - 热度来源徽章（place 含 trend/source 信息时显示）
 * - 6-factor score breakdown (expandable)
 * - Tags, price level, best time, suitable for
 * - 数据来源可追溯脚注（KB 验证/高德/OSM，字段缺失则不显示）
 */

import { useState } from 'react'
import { ChevronDown, ChevronUp, MapPin, Clock, DollarSign, Users, Flame, Database } from 'lucide-react'
import { ScoreBar } from './ScoreBar'
import type { PlaceItem } from '../lib/api'

interface PlaceCardProps {
  place: PlaceItem
  rank?: number
}

/** 后端可能注入的可选扩展字段（契约之外，缺失时不显示，不编造）。 */
function getPlaceExt(place: PlaceItem): { trendSource: string; dataSource: string } {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const ext = place as any
  const trendSource: string = ext.trend_source || ext.trend || ''
  const dataSource: string = ext.data_source || ext.source || ''
  return { trendSource, dataSource }
}

/** 已知数据来源标识 → 中文可追溯标签 */
const DATA_SOURCE_LABELS: Record<string, string> = {
  kb: 'KB 验证',
  knowledge_base: 'KB 验证',
  amap: '高德地图',
  gaode: '高德地图',
  osm: 'OpenStreetMap',
  openstreetmap: 'OpenStreetMap',
}

function dataSourceLabel(raw: string): string {
  return DATA_SOURCE_LABELS[raw.toLowerCase()] || raw
}

export function PlaceCard({ place, rank }: PlaceCardProps) {
  const [expanded, setExpanded] = useState(false)

  const scorePct = Math.round(place.total_score * 100)
  const scoreColor =
    scorePct >= 70 ? 'text-success-600' : scorePct >= 50 ? 'text-amber-600' : 'text-danger-500'

  const { trendSource, dataSource } = getPlaceExt(place)

  return (
    <div className="card hover-lift animate-fade-in-up p-4">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            {rank !== undefined && (
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brand-400 to-brand-600 text-xs font-bold text-white shadow-sm">
                {rank}
              </span>
            )}
            <h3 className="truncate text-base font-bold text-slate-900">
              {place.name}
            </h3>
          </div>
          <div className="mt-1 flex items-center gap-1 text-xs text-slate-400">
            <MapPin size={12} />
            <span>{place.city}</span>
          </div>
        </div>
        <div className={`text-right shrink-0 ${scoreColor}`}>
          <span className="text-2xl font-extrabold tabular-nums">{scorePct}</span>
          <span className="text-xs">分</span>
        </div>
      </div>

      {/* 热度来源徽章 — 仅当数据含 trend/source 信息时显示 */}
      {trendSource && (
        <div className="mt-2">
          <span className="inline-flex items-center gap-1 rounded-full bg-gradient-to-r from-brand-500 to-amber-500 px-2.5 py-0.5 text-xs font-semibold text-white shadow-sm">
            <Flame size={11} />
            {trendSource}热议
          </span>
        </div>
      )}

      {/* Tags */}
      {place.tags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {place.tags.slice(0, 6).map((tag) => (
            <span
              key={tag}
              className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Meta info */}
      <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-500">
        {place.price_level && (
          <span className="flex items-center gap-1">
            <DollarSign size={12} />
            {place.price_level}
          </span>
        )}
        {place.best_time && (
          <span className="flex items-center gap-1">
            <Clock size={12} />
            {place.best_time}
          </span>
        )}
        {place.suitable_for && (
          <span className="flex items-center gap-1">
            <Users size={12} />
            {place.suitable_for}
          </span>
        )}
      </div>

      {/* Expand toggle */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="mt-3 flex w-full items-center justify-center gap-1 rounded-xl py-1.5 text-xs text-slate-400 transition-colors hover:bg-brand-50 hover:text-brand-600"
      >
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        {expanded ? '收起评分' : '查看评分明细'}
      </button>

      {/* Expanded score breakdown */}
      {expanded && (
        <div className="mt-2 animate-fade-in rounded-xl bg-surface-tertiary p-3">
          <ScoreBar breakdown={place.score_breakdown} />
        </div>
      )}

      {/* POI 数据来源可追溯脚注 — 字段缺失则不显示 */}
      {dataSource && (
        <p className="mt-2 flex items-center gap-1 border-t border-border-light pt-2 text-[11px] text-slate-400">
          <Database size={10} />
          数据来源：{dataSourceLabel(dataSource)}
        </p>
      )}
    </div>
  )
}
