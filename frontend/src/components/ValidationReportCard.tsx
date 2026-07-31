/**
 * TravelMind Agent — ValidationReportCard
 *
 * 校验报告卡片：把后台静默运行的真实数据校验（POI 存续 / 路线顺路 /
 * 天气匹配）变成用户可见的产品卖点。
 * 纯渲染 docs/itinerary.schema.json 的 validation_report 字段。
 * weather_fit 以显眼徽章呈现：good=绿 / fair=黄 / poor=红。
 */

import { useState } from 'react'
import {
  ShieldCheck,
  ShieldAlert,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  RefreshCw,
  AlertTriangle,
  XCircle,
  CloudSun,
  CloudRain,
  Sun,
  Cloud,
  Route,
  MapPin,
} from 'lucide-react'
import type { ValidationReport, PoiValidation } from '../lib/api'

const STATUS_META: Record<PoiValidation['status'], { label: string; cls: string; Icon: typeof CheckCircle2 }> = {
  verified: { label: '在营', cls: 'text-green-600 dark:text-green-400', Icon: CheckCircle2 },
  replaced: { label: '已替换', cls: 'text-brand-600 dark:text-brand-400', Icon: RefreshCw },
  unknown: { label: '未核实', cls: 'text-amber-600 dark:text-amber-400', Icon: AlertTriangle },
  closed: { label: '已关闭', cls: 'text-red-500 dark:text-red-400', Icon: XCircle },
}

const FIT_META: Record<string, { label: string; cls: string; Icon: typeof Sun }> = {
  good: { label: '天气适宜', cls: 'border-green-300 dark:border-green-700 bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300', Icon: Sun },
  fair: { label: '天气一般', cls: 'border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300', Icon: CloudSun },
  poor: { label: '天气欠佳', cls: 'border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-400', Icon: CloudRain },
  unknown: { label: '天气未知', cls: 'border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-500 dark:text-slate-400', Icon: Cloud },
}

export function ValidationReportCard({ report }: { report: ValidationReport }) {
  const [expanded, setExpanded] = useState(false)

  const [verifiedN, totalN] = report.poi_verified.split('/').map((s) => parseInt(s, 10))
  const allVerified = verifiedN === totalN

  const fit = FIT_META[report.weather_fit] || FIT_META.unknown

  return (
    <div className="card mb-6 overflow-hidden">
      {/* 徽章行 */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-5 py-4 text-left transition-colors hover:bg-surface-secondary"
      >
        {allVerified ? (
          <ShieldCheck size={20} className="shrink-0 text-green-600" />
        ) : (
          <ShieldAlert size={20} className="shrink-0 text-amber-500" />
        )}
        <span className="text-sm font-bold text-slate-800 dark:text-slate-200">真实数据校验</span>
        <div className="ml-1 flex flex-wrap items-center gap-1.5 text-xs">
          <span
            className={`rounded-full border px-2.5 py-0.5 font-medium ${
              allVerified
                ? 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                : 'border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
            }`}
          >
            ✓ POI 在营 {report.poi_verified}
          </span>
          <span
            className={`rounded-full border px-2.5 py-0.5 font-medium ${
              report.route_backtrack
                ? 'border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
                : 'border-green-200 dark:border-green-800 bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300'
            }`}
          >
            {report.route_backtrack ? '⚠ 已优化折返' : '✓ 无折返路线'}
          </span>
          {/* 天气安全徽章：good=绿 / fair=黄 / poor=红 */}
          <span
            className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 font-semibold ${fit.cls}`}
          >
            <fit.Icon size={12} />
            {report.weather_fit === 'unknown' ? fit.label : `天气安全 · ${fit.label}`}
          </span>
        </div>
        <span className="ml-auto flex items-center gap-1 text-xs text-slate-400 dark:text-slate-500">
          校验于 {report.checked_at}
          {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </span>
      </button>

      {/* 明细（可展开） */}
      {expanded && (
        <div className="animate-fade-in border-t border-border-light px-5 py-4">
          {/* POI 存续明细 */}
          <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400">
            <MapPin size={13} />
            景点存续核实（高德地图 · {report.checked_at}）
          </h4>
          <div className="mb-4 grid gap-1.5 sm:grid-cols-2">
            {report.poi.map((p, i) => {
              const meta = STATUS_META[p.status]
              return (
                <div key={i} className="flex items-start gap-1.5 text-xs" title={p.note || ''}>
                  <meta.Icon size={14} className={`mt-0.5 shrink-0 ${meta.cls}`} />
                  <div className="min-w-0">
                    <span className="text-slate-700 dark:text-slate-300">{p.name}</span>
                    {p.district && <span className="ml-1 text-slate-400 dark:text-slate-500">· {p.district}</span>}
                    {p.note && <p className="mt-0.5 text-slate-400 dark:text-slate-500">{p.note}</p>}
                  </div>
                </div>
              )
            })}
          </div>

          {/* 路线结论 */}
          <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400">
            <Route size={13} />
            每日路线
          </h4>
          <div className="mb-4 flex flex-wrap gap-2">
            {report.routes.map((r) => (
              <span
                key={r.day}
                className={`rounded-xl border px-2.5 py-1 text-xs ${
                  r.backtrack
                    ? 'border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300'
                    : 'border-border bg-surface-secondary dark:bg-slate-800/40 text-slate-600 dark:text-slate-400'
                }`}
                title={r.note || ''}
              >
                第{r.day}天 · {r.total_km}km · {r.backtrack ? '已优化折返' : '顺路'}
              </span>
            ))}
          </div>

          {/* 天气匹配 */}
          {report.weather_notes && report.weather_notes.length > 0 && (
            <>
              <h4 className="mb-2 flex items-center gap-1.5 text-xs font-semibold text-slate-500 dark:text-slate-400">
                <CloudSun size={13} />
                天气匹配
              </h4>
              <ul className="space-y-1">
                {report.weather_notes.map((n, i) => (
                  <li key={i} className="text-xs text-slate-500 dark:text-slate-400">
                    · {n}
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  )
}
