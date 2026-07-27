/**
 * TravelMind Agent — PriceBadge & PriceSummaryCard
 *
 * Phase 7: Price layer UI components extracted from ItineraryPage.
 * Shows price range, staleness warning, and booking link for trip items.
 */

import { AlertCircle, Wallet } from 'lucide-react'
import { isPriceStale, type DayItem, type PriceRange, type PriceSummary } from '../lib/api'

/** Extract price fields from a day item (backend-injected, may not exist). */
export function getPriceInfo(item: DayItem): {
  range: PriceRange | null
  source: string
  updatedAt: string
  bookingUrl: string
  isFree: boolean
  stale: boolean
} {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const ext = item as any
  const range: PriceRange | null = ext.price_range || null
  const updatedAt: string = ext.price_updated_at || ''
  const bookingUrl: string = ext.booking_url || ''
  const isFree = range !== null && range.min === 0 && range.max === 0
  const stale = isPriceStale(updatedAt)
  return { range, source: ext.price_source || '', updatedAt, bookingUrl, isFree, stale }
}

export function PriceBadge({ item }: { item: DayItem }) {
  const { range, updatedAt, bookingUrl, isFree, stale } = getPriceInfo(item)

  if (!range) return null

  return (
    <div className="mt-1.5 flex items-center gap-2 flex-wrap">
      {isFree ? (
        <span className="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-500">
          免费
        </span>
      ) : (
        <span className="inline-flex items-center rounded-full bg-green-50 px-2 py-0.5 text-xs font-medium text-green-700">
          {range.min === range.max ? `¥${range.min}` : `¥${range.min}-${range.max}`}
        </span>
      )}
      {stale && updatedAt && (
        <span className="text-xs text-amber-500" title={`上次更新: ${updatedAt}`}>
          可能已变动
        </span>
      )}
      {bookingUrl && (
        <a
          href={bookingUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-0.5 text-xs text-brand-600 hover:text-brand-700 hover:underline"
        >
          去看实时价 →
        </a>
      )}
    </div>
  )
}

export function PriceSummaryCard({ summary }: { summary: PriceSummary }) {
  return (
    <div className="card mt-4 p-5">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800">
        <Wallet size={16} className="text-slate-400" />
        门票参考
      </h3>
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-xl bg-surface-secondary p-3 text-center">
          <p className="text-lg font-bold text-slate-800">
            ¥{summary.total_estimate_min}-{summary.total_estimate_max}
          </p>
          <p className="text-xs text-slate-400">门票估算（人均）</p>
        </div>
        <div className="rounded-xl bg-surface-secondary p-3 text-center">
          <p className="text-lg font-bold text-slate-800">
            {summary.priced_items}/{summary.total_items}
          </p>
          <p className="text-xs text-slate-400">有价格数据的景点</p>
        </div>
        <div className="rounded-xl bg-surface-secondary p-3 text-center">
          <p className="text-lg font-bold text-slate-800">{summary.budget_slot}</p>
          <p className="text-xs text-slate-400">预算档次</p>
        </div>
        {summary.stale_items > 0 && (
          <div className="rounded-lg bg-amber-50 p-3 text-center">
            <p className="text-lg font-bold text-amber-600">{summary.stale_items}</p>
            <p className="text-xs text-amber-500">价格可能过期</p>
          </div>
        )}
      </div>
      {summary.over_budget && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
          <AlertCircle size={14} className="mr-1 inline-block" />
          {summary.over_budget_warning}
        </div>
      )}
    </div>
  )
}
