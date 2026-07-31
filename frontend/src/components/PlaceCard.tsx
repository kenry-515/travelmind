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
import { Link } from 'react-router-dom'
import { ChevronDown, ChevronUp, MapPin, Clock, DollarSign, Users, Flame, Database, Heart, Compass, ExternalLink } from 'lucide-react'
import { ScoreBar } from './ScoreBar'
import type { PlaceItem, ScoreBreakdown } from '../lib/api'
import { useSavedPlaces } from '../lib/savedPlaces'

interface PlaceCardProps {
  place: PlaceItem
  rank?: number
}

/** 后端可能注入的可选扩展字段（契约之外，缺失时不显示，不编造）。 */
interface PlaceExt {
  trend_source?: string
  trend?: string
  data_source?: string
  source?: string
}

function getPlaceExt(place: PlaceItem): { trendSource: string; dataSource: string } {
  const ext = place as PlaceExt
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

/** Phase 16.4: 从 score_breakdown 中提取得分最高的 N 个维度 */
function getTopFactors(
  breakdown: ScoreBreakdown | undefined,
  n: number
): { key: string; label: string; value: number }[] {
  if (!breakdown) return []
  const FACTOR_LABELS: Record<string, string> = {
    preference_match: '偏好匹配',
    trend_heat: '热度趋势',
    budget_match: '预算匹配',
    location_efficiency: '位置便利',
    time_match: '时节匹配',
    weather: '天气匹配',
    data_reliability: '数据可靠',
  }
  return Object.entries(breakdown)
    .filter(([_, v]) => typeof v === 'number')
    .map(([k, v]) => ({ key: k, label: FACTOR_LABELS[k] || k, value: v as number }))
    .sort((a, b) => b.value - a.value)
    .slice(0, n)
}

export function PlaceCard({ place, rank }: PlaceCardProps) {
  const [expanded, setExpanded] = useState(false)
  const { togglePlace, isSaved } = useSavedPlaces()

  const scorePct = Math.round(place.total_score * 100)
  const scoreColor =
    scorePct >= 70 ? 'text-success-600' : scorePct >= 50 ? 'text-amber-600' : 'text-danger-500'

  const { trendSource, dataSource } = getPlaceExt(place)
  const saved = isSaved(place.name, place.city)
  const city = place.city
  const tags = place.tags || []

  // Phase 16.4: 提取 TOP 评分维度用于卡片预览
  const breakdown = place.score_breakdown
  const topFactors = getTopFactors(breakdown, 3)

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
            <h3 className="truncate text-base font-bold text-slate-900 dark:text-slate-100">
              {place.name}
            </h3>
          </div>
          <div className="mt-1 flex items-center gap-1 text-xs text-slate-400 dark:text-slate-500">
            <MapPin size={12} />
            <span>{place.city}</span>
          </div>
        </div>
        <div className="flex items-start gap-1">
          <button
            onClick={() => togglePlace({ name: place.name, city, tags, note: '', source: 'recommend' })}
            className={`rounded-lg p-1.5 transition-all ${
              saved ? 'text-red-400 hover:text-red-500' : 'text-slate-300 dark:text-slate-600 hover:text-red-400 dark:hover:text-red-400'
            }`}
            aria-label={saved ? '取消收藏' : '收藏'}
            title={saved ? '已收藏' : '收藏'}
          >
            <Heart size={16} fill={saved ? 'currentColor' : 'none'} />
          </button>
          <div className={`text-right ${scoreColor}`}>
            <span className="text-2xl font-extrabold tabular-nums">{scorePct}</span>
            <span className="text-xs">分</span>
          </div>
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
              className="rounded-full bg-brand-50 dark:bg-brand-900/30 px-2 py-0.5 text-xs font-medium text-brand-700 dark:text-brand-300"
            >
              {tag}
            </span>
          ))}
        </div>
      )}

      {/* Meta info */}
      <div className="mt-3 flex flex-wrap gap-3 text-xs text-slate-500 dark:text-slate-400">
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

      {/* 联动入口：AI 导游讲解 + 街景查看（大赛主题：导游联动） */}
      <div className="mt-3 flex gap-2">
        <Link
          to={`/guide?q=${encodeURIComponent(place.name)}`}
          className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-brand-50 dark:bg-brand-900/30 py-1.5 text-xs font-medium text-brand-600 dark:text-brand-400 transition-colors hover:bg-brand-100 dark:hover:bg-brand-900/50"
          title={`听 AI 导游讲解${place.name}`}
        >
          <Compass size={13} />
          AI 导游
        </Link>
        <a
          href={`https://uri.amap.com/search?keyword=${encodeURIComponent(place.name)}&city=${encodeURIComponent(place.city)}`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex flex-1 items-center justify-center gap-1 rounded-lg bg-accent-50 dark:bg-accent-900/30 py-1.5 text-xs font-medium text-accent-600 dark:text-accent-400 transition-colors hover:bg-accent-100 dark:hover:bg-accent-900/50"
          title={`在高德地图查看${place.name}街景`}
        >
          <ExternalLink size={13} />
          看街景
        </a>
      </div>

      {/* Phase 16.4: TOP 评分维度预览 — 不用展开就能看到为什么得分高 */}
      {topFactors.length > 0 && !expanded && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {topFactors.map((f) => (
            <span
              key={f.key}
              className="inline-flex items-center gap-1 rounded-full bg-gradient-to-r from-brand-50 to-accent-50 px-2 py-0.5 text-[11px] font-medium text-slate-600 dark:text-slate-400"
            >
              <span className={`font-bold ${
                f.value >= 0.8 ? 'text-brand-600' :
                f.value >= 0.6 ? 'text-amber-600' : 'text-slate-500 dark:text-slate-400'
              }`}>
                {f.label}
              </span>
              <span className="tabular-nums text-slate-400 dark:text-slate-500">
                {Math.round(f.value * 100)}
              </span>
            </span>
          ))}
        </div>
      )}

      {/* Expand toggle */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="mt-3 flex w-full items-center justify-center gap-1 rounded-xl py-1.5 text-xs text-slate-400 dark:text-slate-500 transition-colors hover:bg-brand-50 dark:hover:bg-brand-900/30 hover:text-brand-600 dark:hover:text-brand-400"
      >
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        {expanded ? '收起评分' : '查看评分明细'}
      </button>

      {/* Expanded score breakdown */}
      {expanded && (
        <div className="mt-2 animate-fade-in rounded-xl bg-surface-tertiary dark:bg-slate-800/40 p-3">
          <ScoreBar breakdown={place.score_breakdown} />
        </div>
      )}

      {/* POI 数据来源可追溯脚注 — 字段缺失则不显示 */}
      {dataSource && (
        <p className="mt-2 flex items-center gap-1 border-t border-border-light pt-2 text-[11px] text-slate-400 dark:text-slate-500">
          <Database size={10} />
          数据来源：{dataSourceLabel(dataSource)}
        </p>
      )}
    </div>
  )
}
