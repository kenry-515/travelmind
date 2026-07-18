/**
 * TravelMind Agent — PlaceCard Component
 *
 * Card displaying a recommended attraction with:
 * - Name, city, score
 * - 6-factor score breakdown (expandable)
 * - Tags, price level, best time, suitable for
 */

import { useState } from 'react'
import { ChevronDown, ChevronUp, MapPin, Clock, DollarSign, Users } from 'lucide-react'
import { ScoreBar } from './ScoreBar'
import type { PlaceItem } from '../lib/api'

interface PlaceCardProps {
  place: PlaceItem
  rank?: number
}

export function PlaceCard({ place, rank }: PlaceCardProps) {
  const [expanded, setExpanded] = useState(false)

  const scorePct = Math.round(place.total_score * 100)
  const scoreColor =
    scorePct >= 70 ? 'text-green-600' : scorePct >= 50 ? 'text-amber-600' : 'text-red-500'

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            {rank !== undefined && (
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-blue-100 text-xs font-bold text-blue-700">
                {rank}
              </span>
            )}
            <h3 className="truncate text-base font-semibold text-slate-900">
              {place.name}
            </h3>
          </div>
          <div className="mt-1 flex items-center gap-1 text-xs text-slate-400">
            <MapPin size={12} />
            <span>{place.city}</span>
          </div>
        </div>
        <div className={`text-right shrink-0 ${scoreColor}`}>
          <span className="text-2xl font-bold tabular-nums">{scorePct}</span>
          <span className="text-xs">分</span>
        </div>
      </div>

      {/* Tags */}
      {place.tags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1">
          {place.tags.slice(0, 6).map((tag) => (
            <span
              key={tag}
              className="rounded-md bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700"
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
        className="mt-3 flex w-full items-center justify-center gap-1 rounded-lg py-1 text-xs text-slate-400 transition-colors hover:bg-slate-50 hover:text-slate-600"
      >
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        {expanded ? '收起评分' : '查看评分明细'}
      </button>

      {/* Expanded score breakdown */}
      {expanded && (
        <div className="mt-2 rounded-lg bg-slate-50 p-3">
          <ScoreBar breakdown={place.score_breakdown} />
        </div>
      )}
    </div>
  )
}
