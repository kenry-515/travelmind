/**
 * TravelMind Agent — ScoreBar Component
 *
 * Visual bar chart showing the 7-factor recommendation score breakdown.
 * Each factor is shown as a colored bar with label and 0.0-1.0 value.
 */

import type { ScoreBreakdown } from '../lib/api'

const FACTORS: { key: keyof ScoreBreakdown; label: string; color: string }[] = [
  { key: 'preference_match', label: '偏好匹配', color: 'bg-brand-500' },
  { key: 'trend_heat', label: '热度趋势', color: 'bg-amber-500' },
  { key: 'budget_match', label: '预算匹配', color: 'bg-green-500' },
  { key: 'location_efficiency', label: '位置便利', color: 'bg-accent-500' },
  { key: 'time_match', label: '时节匹配', color: 'bg-purple-500' },
  { key: 'weather', label: '天气匹配', color: 'bg-sky-400' },
  { key: 'data_reliability', label: '数据可靠', color: 'bg-slate-400' },
]

interface ScoreBarProps {
  breakdown: ScoreBreakdown
  compact?: boolean
}

export function ScoreBar({ breakdown, compact = false }: ScoreBarProps) {
  if (compact) {
    // Compact: just a single weighted bar
    const vals = FACTORS.map((f) => breakdown[f.key])
    const weighted = vals.reduce((a, b) => a + b, 0) / vals.length
    return (
      <div className="flex items-center gap-1.5">
        <div className="h-1.5 flex-1 rounded-full bg-slate-200">
          <div
            className="h-1.5 rounded-full bg-gradient-to-r from-brand-400 to-brand-600 transition-all"
            style={{ width: `${Math.round(weighted * 100)}%` }}
          />
        </div>
        <span className="text-xs tabular-nums text-slate-400 dark:text-slate-500">
          {weighted.toFixed(2)}
        </span>
      </div>
    )
  }

  return (
    <div className="space-y-1">
      {FACTORS.map((f) => {
        const val = breakdown[f.key] ?? 0
        return (
          <div key={f.key} className="flex items-center gap-2 text-xs">
            <span className="w-16 shrink-0 text-right tabular-nums text-slate-500 dark:text-slate-400">
              {f.label}
            </span>
            <div className="h-2 flex-1 rounded-full bg-slate-100 dark:bg-slate-800">
              <div
                className={`h-2 rounded-full ${f.color} transition-all`}
                style={{ width: `${Math.round(val * 100)}%` }}
              />
            </div>
            <span className="w-7 shrink-0 tabular-nums font-medium text-slate-700 dark:text-slate-300">
              {val.toFixed(2)}
            </span>
          </div>
        )
      })}
    </div>
  )
}
