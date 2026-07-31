/**
 * TravelMind Agent — ResourcesPage (景区资源调度管理)
 *
 * 广东智能体大赛 "AI+旅游休闲" 命题页面：聚焦"酒店景区资源调度管理"场景。
 * 基于 attractions.json 真实数据，提供：
 *  - 资源总览仪表盘（KPI + 热度/价格/区域分布 + 标签云）
 *  - 热度排行 Top10（辅助客流调度决策）
 *  - 资源卡片网格（每条含基于真实热度的调度建议，可排序/区域筛选）
 *  - 联动入口：跳转 AI 导游讲解 / 对话式规划行程
 *
 * 【硬约束】所有数据来自后端真实统计，前端不编造。数据缺失时明确标注。
 */

import { useState, useEffect, useCallback } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowLeft,
  AlertCircle,
  RefreshCw,
  MapPin,
  Tag,
  TrendingUp,
  Building2,
  Navigation,
  Compass,
  Sparkles,
  Clock,
  DollarSign,
  BarChart3,
  Layers,
} from 'lucide-react'
import {
  fetchResourcesOverview,
  fetchResourcesList,
  fetchDistricts,
  type ResourcesOverview,
  type ResourceItem,
} from '../lib/api'

const DEFAULT_CITY = '广州'

// ── 调度建议样式映射（按 level 着色，暗夜模式同步适配） ──
const ADVICE_STYLES: Record<string, { badge: string; dot: string }> = {
  '超高热度': {
    badge: 'bg-red-50 text-red-600 dark:bg-red-900/30 dark:text-red-400',
    dot: 'bg-red-500',
  },
  '高热度': {
    badge: 'bg-amber-50 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400',
    dot: 'bg-amber-500',
  },
  '中等热度': {
    badge: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-900/30 dark:text-emerald-400',
    dot: 'bg-emerald-500',
  },
  '小众静谧': {
    badge: 'bg-sky-50 text-sky-600 dark:bg-sky-900/30 dark:text-sky-400',
    dot: 'bg-sky-500',
  },
  '未知': {
    badge: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
    dot: 'bg-slate-400',
  },
}

function adviceStyle(level: string) {
  return ADVICE_STYLES[level] || ADVICE_STYLES['未知']
}

// ── 工具函数 ─────────────────────────────────────────────

/** 格式化价格区间 */
function formatPrice(item: { price_range: { min: number; max: number } | null; price_level: string }): string {
  const pr = item.price_range
  if (pr && pr.min > 0) {
    if (pr.min === pr.max) return `¥${pr.min}`
    return `¥${pr.min}-${pr.max}`
  }
  return item.price_level || '待核实'
}

/** 热度条形图宽度（按 10 分制换算百分比） */
function popBarWidth(pop: number | null): string {
  if (pop == null) return '0%'
  return `${Math.min(100, (pop / 10) * 100)}%`
}

// ── 子组件 ───────────────────────────────────────────────

/** KPI 指标卡 */
function KpiCard({
  icon: Icon,
  label,
  value,
  sub,
  tint,
}: {
  icon: typeof TrendingUp
  label: string
  value: string | number
  sub?: string
  tint: string
}) {
  return (
    <div className="card hover-lift p-4">
      <div className="flex items-center gap-2">
        <span className={`flex h-8 w-8 items-center justify-center rounded-lg ${tint}`}>
          <Icon size={16} />
        </span>
        <span className="text-[11px] font-medium text-slate-400 dark:text-slate-500">{label}</span>
      </div>
      <p className="mt-2 text-2xl font-extrabold tabular-nums text-slate-800 dark:text-slate-100">
        {value}
      </p>
      {sub && <p className="mt-0.5 text-[11px] text-slate-400 dark:text-slate-500">{sub}</p>}
    </div>
  )
}

/** 分布条形图（单条） */
function DistributionBar({
  label,
  count,
  total,
  color,
}: {
  label: string
  count: number
  total: number
  color: string
}) {
  const pct = total > 0 ? (count / total) * 100 : 0
  return (
    <div className="flex items-center gap-2">
      <span className="w-24 shrink-0 truncate text-xs text-slate-500 dark:text-slate-400">{label}</span>
      <div className="h-5 flex-1 overflow-hidden rounded-md bg-slate-100 dark:bg-slate-800">
        <div
          className={`h-full rounded-md ${color} transition-all duration-500`}
          style={{ width: `${Math.max(2, pct)}%` }}
        />
      </div>
      <span className="w-8 shrink-0 text-right text-xs font-medium tabular-nums text-slate-600 dark:text-slate-300">
        {count}
      </span>
    </div>
  )
}

/** 骨架屏 */
function OverviewSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card p-4">
            <div className="skeleton-shimmer h-8 w-8 rounded-lg" />
            <div className="skeleton-shimmer mt-3 h-7 w-16 rounded" />
            <div className="skeleton-shimmer mt-2 h-3 w-20 rounded" />
          </div>
        ))}
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card p-5">
            <div className="skeleton-shimmer h-4 w-24 rounded" />
            <div className="mt-4 space-y-2">
              {Array.from({ length: 4 }).map((_, j) => (
                <div key={j} className="skeleton-shimmer h-5 w-full rounded" />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function CardSkeleton() {
  return (
    <div className="card overflow-hidden">
      <div className="skeleton-shimmer h-28 w-full" />
      <div className="space-y-2 p-3">
        <div className="skeleton-shimmer h-3.5 w-3/4 rounded" />
        <div className="skeleton-shimmer h-2.5 w-1/2 rounded" />
        <div className="skeleton-shimmer h-5 w-20 rounded" />
      </div>
    </div>
  )
}

// ── 主组件 ───────────────────────────────────────────────

export function ResourcesPage() {
  const navigate = useNavigate()

  // 总览
  const [overview, setOverview] = useState<ResourcesOverview | null>(null)
  const [ovLoading, setOvLoading] = useState(true)
  const [ovError, setOvError] = useState<string | null>(null)

  // 列表
  const [list, setList] = useState<ResourceItem[]>([])
  const [listLoading, setListLoading] = useState(true)
  const [listError, setListError] = useState<string | null>(null)
  const [sortBy, setSortBy] = useState<'popularity' | 'price' | 'name'>('popularity')
  const [district, setDistrict] = useState<string>('')
  const [districts, setDistricts] = useState<string[]>([])

  // ── 加载总览 ──
  const loadOverview = useCallback(async () => {
    setOvLoading(true)
    setOvError(null)
    try {
      const data = await fetchResourcesOverview(DEFAULT_CITY)
      setOverview(data)
    } catch (err: unknown) {
      setOvError(err instanceof Error ? err.message : '总览加载失败，请稍后重试。')
    } finally {
      setOvLoading(false)
    }
  }, [])

  // ── 加载区域列表 ──
  useEffect(() => {
    fetchDistricts(DEFAULT_CITY)
      .then((res) => setDistricts(res.districts || []))
      .catch(() => setDistricts([]))
  }, [])

  // ── 加载资源列表 ──
  const loadList = useCallback(async () => {
    setListLoading(true)
    setListError(null)
    try {
      const data = await fetchResourcesList({
        city: DEFAULT_CITY,
        sortBy,
        district: district || undefined,
        limit: 50,
      })
      setList(data || [])
    } catch (err: unknown) {
      setListError(err instanceof Error ? err.message : '资源列表加载失败，请稍后重试。')
    } finally {
      setListLoading(false)
    }
  }, [sortBy, district])

  useEffect(() => {
    loadOverview()
  }, [loadOverview])

  useEffect(() => {
    loadList()
  }, [loadList])

  // ── 渲染辅助 ──
  const priceEntries = overview
    ? Object.entries(overview.price_distribution).sort((a, b) => b[1] - a[1])
    : []
  const popEntries = overview
    ? Object.entries(overview.popularity_distribution)
    : []
  const districtEntries = overview
    ? Object.entries(overview.district_distribution).sort((a, b) => b[1] - a[1])
    : []
  const priceColorMap: Record<string, string> = {
    '免费': 'bg-emerald-400',
    '经济': 'bg-sky-400',
    '适中': 'bg-brand-400',
    '付费': 'bg-amber-400',
    '高端': 'bg-red-400',
    '未知': 'bg-slate-300 dark:bg-slate-600',
  }
  const popColorMap: Record<string, string> = {
    '超高热度(9-10)': 'bg-red-500',
    '高热度(7-8)': 'bg-amber-500',
    '中等热度(5-6)': 'bg-emerald-500',
    '小众(<5)': 'bg-sky-500',
    '未评级': 'bg-slate-300 dark:bg-slate-600',
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-surface-secondary pb-20 sm:pb-8">
      <div aria-hidden className="aurora aurora-soft">
        <span />
        <span />
        <span />
      </div>

      {/* Header */}
      <header className="glass sticky top-0 z-10 border-b border-border-light">
        <div className="mx-auto flex max-w-6xl items-center gap-2 px-3 py-2.5 sm:gap-3 sm:px-4 sm:py-3">
          <Link
            to="/"
            className="rounded-xl p-1.5 text-slate-500 dark:text-slate-400 transition-colors hover:bg-brand-50 dark:hover:bg-brand-900/30 hover:text-brand-600 dark:hover:text-brand-400"
            aria-label="返回首页"
          >
            <ArrowLeft size={20} />
          </Link>
          <div className="min-w-0 flex-1">
            <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
              景区资源调度
            </h2>
            <p className="hidden text-xs text-slate-400 dark:text-slate-500 sm:block">
              广州景区资源总览 · 智能调度建议
            </p>
          </div>
          <span className="hidden items-center gap-1 rounded-full bg-brand-50 dark:bg-brand-900/30 px-2.5 py-1 text-xs font-medium text-brand-600 dark:text-brand-400 sm:inline-flex">
            <Sparkles size={12} />
            广东智能体大赛
          </span>
        </div>
      </header>

      <main className="relative mx-auto max-w-6xl px-4 py-6">
        {/* 标题区 */}
        <div className="mb-6 text-center">
          <div className="mb-3 inline-flex h-16 w-16 items-center justify-center rounded-3xl bg-gradient-to-br from-brand-100 to-accent-100 dark:from-slate-800 dark:to-slate-700 animate-float-slow">
            <BarChart3 size={32} className="text-brand-500" />
          </div>
          <h1 className="display-lg mb-2">
            <span className="text-gradient">景区资源调度</span>
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 sm:text-base">
            全量广州景区真实数据 · 客流热度可视化 · 智能错峰调度建议
          </p>
        </div>

        {/* ════════ 总览仪表盘 ════════ */}
        {ovLoading && <OverviewSkeleton />}

        {ovError && !ovLoading && (
          <div className="mt-8 text-center">
            <AlertCircle size={40} className="mx-auto mb-3 text-amber-500" />
            <p className="text-slate-600 dark:text-slate-400">{ovError}</p>
            <button onClick={loadOverview} className="btn-secondary mt-4 px-4 py-2 text-sm">
              <RefreshCw size={14} />
              重新加载
            </button>
          </div>
        )}

        {overview && !ovLoading && (
          <div className="animate-fade-in-up space-y-4">
            {overview.total === 0 ? (
              <div className="card p-8 text-center text-slate-500 dark:text-slate-400">
                {overview.message || `暂无${overview.city}景区数据`}
              </div>
            ) : (
              <>
                {/* KPI 卡片 */}
                <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                  <KpiCard
                    icon={Building2}
                    label="景区总数"
                    value={overview.total}
                    sub="广州全量收录"
                    tint="bg-brand-50 text-brand-500 dark:bg-brand-900/30 dark:text-brand-400"
                  />
                  <KpiCard
                    icon={TrendingUp}
                    label="平均热度"
                    value={overview.avg_popularity.toFixed(1)}
                    sub="10 分制"
                    tint="bg-amber-50 text-amber-500 dark:bg-amber-900/30 dark:text-amber-400"
                  />
                  <KpiCard
                    icon={Navigation}
                    label="有坐标景区"
                    value={overview.with_coords}
                    sub={`覆盖 ${Math.round((overview.with_coords / overview.total) * 100)}%`}
                    tint="bg-emerald-50 text-emerald-500 dark:bg-emerald-900/30 dark:text-emerald-400"
                  />
                  <KpiCard
                    icon={DollarSign}
                    label="免费景区"
                    value={overview.price_distribution['免费'] || 0}
                    sub="可优先调度"
                    tint="bg-sky-50 text-sky-500 dark:bg-sky-900/30 dark:text-sky-400"
                  />
                </div>

                {/* 分布图组 */}
                <div className="grid gap-4 lg:grid-cols-2">
                  {/* 热度分布 */}
                  <div className="card p-5">
                    <h3 className="mb-4 flex items-center gap-2 text-sm font-bold text-slate-800 dark:text-slate-200">
                      <TrendingUp size={16} className="text-brand-500" />
                      热度分布
                      <span className="ml-auto text-[11px] font-normal text-slate-400 dark:text-slate-500">
                        共 {overview.total} 个
                      </span>
                    </h3>
                    <div className="space-y-2.5">
                      {popEntries.map(([label, count]) => (
                        <DistributionBar
                          key={label}
                          label={label}
                          count={count}
                          total={overview.total}
                          color={popColorMap[label] || 'bg-slate-300 dark:bg-slate-600'}
                        />
                      ))}
                    </div>
                  </div>

                  {/* 价格档位分布 */}
                  <div className="card p-5">
                    <h3 className="mb-4 flex items-center gap-2 text-sm font-bold text-slate-800 dark:text-slate-200">
                      <DollarSign size={16} className="text-accent-500" />
                      价格档位分布
                    </h3>
                    <div className="space-y-2.5">
                      {priceEntries.map(([label, count]) => (
                        <DistributionBar
                          key={label}
                          label={label}
                          count={count}
                          total={overview.total}
                          color={priceColorMap[label] || 'bg-slate-300 dark:bg-slate-600'}
                        />
                      ))}
                    </div>
                  </div>

                  {/* 区域分布 */}
                  <div className="card p-5">
                    <h3 className="mb-4 flex items-center gap-2 text-sm font-bold text-slate-800 dark:text-slate-200">
                      <MapPin size={16} className="text-emerald-500" />
                      区域分布
                      <span className="ml-auto text-[11px] font-normal text-slate-400 dark:text-slate-500">
                        已定位 {overview.total - overview.unlocated_count} · 待补 {overview.unlocated_count}
                      </span>
                    </h3>
                    {districtEntries.length > 0 ? (
                      <div className="space-y-2.5">
                        {districtEntries.map(([label, count]) => (
                          <DistributionBar
                            key={label}
                            label={label}
                            count={count}
                            total={overview.total}
                            color="bg-emerald-400"
                          />
                        ))}
                      </div>
                    ) : (
                      <p className="py-4 text-center text-xs text-slate-400 dark:text-slate-500">
                        暂无区域数据
                      </p>
                    )}
                  </div>

                  {/* 标签云 */}
                  <div className="card p-5">
                    <h3 className="mb-4 flex items-center gap-2 text-sm font-bold text-slate-800 dark:text-slate-200">
                      <Tag size={16} className="text-sky-500" />
                      热门标签
                    </h3>
                    {overview.top_tags.length > 0 ? (
                      <div className="flex flex-wrap gap-2">
                        {overview.top_tags.map((t, i) => {
                          const maxCount = overview.top_tags[0]?.count || 1
                          const scale = 0.8 + (t.count / maxCount) * 0.6
                          return (
                            <span
                              key={t.tag}
                              style={{ fontSize: `${scale * 0.75}rem` }}
                              className={`rounded-full px-2.5 py-1 font-medium ${
                                i < 3
                                  ? 'bg-brand-100 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300'
                                  : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
                              }`}
                            >
                              {t.tag}
                              <span className="ml-1 text-[10px] opacity-60">{t.count}</span>
                            </span>
                          )
                        })}
                      </div>
                    ) : (
                      <p className="py-4 text-center text-xs text-slate-400 dark:text-slate-500">
                        暂无标签数据
                      </p>
                    )}
                  </div>
                </div>

                {/* 热度排行 Top10 */}
                <div className="card p-5">
                  <h3 className="mb-4 flex items-center gap-2 text-sm font-bold text-slate-800 dark:text-slate-200">
                    <Layers size={16} className="text-brand-500" />
                    热度排行 Top 10
                    <span className="ml-auto text-[11px] font-normal text-slate-400 dark:text-slate-500">
                      客流调度优先关注
                    </span>
                  </h3>
                  <div className="space-y-2">
                    {overview.top_popular.map((p, i) => (
                      <button
                        key={`${p.name}-${i}`}
                        onClick={() => navigate(`/chat?q=${encodeURIComponent(`广州${p.name}游览攻略`)}`)}
                        className="hover-lift flex w-full items-center gap-3 rounded-xl border border-border-light bg-surface-secondary dark:bg-slate-800/40 p-2.5 text-left transition-colors hover:border-brand-300 dark:hover:border-brand-700 hover:bg-brand-50/50 dark:hover:bg-brand-900/20"
                      >
                        <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold text-white ${
                          i < 3 ? 'bg-gradient-to-br from-brand-400 to-brand-600' : 'bg-slate-400 dark:bg-slate-600'
                        }`}>
                          {i + 1}
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="line-clamp-1 text-sm font-medium text-slate-800 dark:text-slate-200">
                            {p.name}
                          </p>
                          <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-slate-100 dark:bg-slate-700">
                            <div
                              className="h-full rounded-full bg-gradient-to-r from-brand-400 to-amber-400"
                              style={{ width: popBarWidth(p.popularity) }}
                            />
                          </div>
                        </div>
                        <span className="shrink-0 text-sm font-bold tabular-nums text-brand-600 dark:text-brand-400">
                          {p.popularity ?? '-'}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        {/* ════════ 资源列表（带调度建议） ════════ */}
        <div className="mt-8">
          {/* 列表标题 + 排序/筛选 */}
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <h3 className="flex items-center gap-2 text-base font-bold text-slate-800 dark:text-slate-200">
              <Compass size={18} className="text-brand-500" />
              景区资源调度清单
            </h3>
            <div className="ml-auto flex flex-wrap items-center gap-2">
              {/* 排序 */}
              <div className="flex items-center gap-1 rounded-xl bg-slate-100 dark:bg-slate-800 p-1">
                {([
                  { key: 'popularity', label: '热度' },
                  { key: 'price', label: '价格' },
                  { key: 'name', label: '名称' },
                ] as const).map((opt) => (
                  <button
                    key={opt.key}
                    onClick={() => setSortBy(opt.key)}
                    className={`rounded-lg px-3 py-1 text-xs font-medium transition-all ${
                      sortBy === opt.key
                        ? 'bg-white text-brand-600 shadow-sm dark:bg-slate-700 dark:text-brand-400'
                        : 'text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-300'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
              {/* 区域筛选 */}
              {districts.length > 0 && (
                <select
                  value={district}
                  onChange={(e) => setDistrict(e.target.value)}
                  className="rounded-xl border border-border-light bg-white dark:bg-slate-800 px-3 py-1.5 text-xs text-slate-700 dark:text-slate-300 focus:border-brand-400 focus:outline-none"
                >
                  <option value="">全部区域</option>
                  {districts.map((d) => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                </select>
              )}
            </div>
          </div>

          {/* 加载中 */}
          {listLoading && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {Array.from({ length: 6 }).map((_, i) => (
                <CardSkeleton key={i} />
              ))}
            </div>
          )}

          {/* 错误 */}
          {listError && !listLoading && (
            <div className="mt-8 text-center">
              <AlertCircle size={40} className="mx-auto mb-3 text-amber-500" />
              <p className="text-slate-600 dark:text-slate-400">{listError}</p>
              <button onClick={loadList} className="btn-secondary mt-4 px-4 py-2 text-sm">
                <RefreshCw size={14} />
                重新加载
              </button>
            </div>
          )}

          {/* 空结果 */}
          {!listLoading && !listError && list.length === 0 && (
            <div className="mt-8 text-center">
              <Compass size={40} className="mx-auto mb-3 text-slate-300 dark:text-slate-600" />
              <p className="text-slate-600 dark:text-slate-400">
                {district ? `「${district}」暂无景区数据` : '暂无景区数据'}
              </p>
            </div>
          )}

          {/* 资源卡片网格 */}
          {!listLoading && !listError && list.length > 0 && (
            <div className="stagger grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {list.map((item, idx) => {
                const advice = adviceStyle(item.schedule_advice.level)
                return (
                  <div key={`${item.name}-${idx}`} className="card hover-lift flex flex-col overflow-hidden">
                    {/* 头图 */}
                    <div className="relative h-28 w-full overflow-hidden sm:h-32">
                      {item.thumbnail_url ? (
                        <img
                          src={item.thumbnail_url}
                          alt={item.name}
                          loading="lazy"
                          className="h-full w-full object-cover"
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center bg-gradient-to-br from-brand-100 to-accent-100 dark:from-slate-700 dark:to-slate-800">
                          <Compass size={32} className="text-brand-400 dark:text-brand-500" />
                        </div>
                      )}
                      {/* 调度建议角标 */}
                      <span className={`absolute left-2 top-2 rounded-full px-2 py-0.5 text-[10px] font-semibold backdrop-blur-sm ${advice.badge}`}>
                        {item.schedule_advice.tag}
                      </span>
                      {/* 热度角标 */}
                      {item.popularity_score != null && item.popularity_score > 0 && (
                        <span className="absolute right-2 top-2 rounded-full bg-black/55 px-2 py-0.5 text-[10px] font-medium text-white backdrop-blur-sm">
                          ★ {item.popularity_score}
                        </span>
                      )}
                    </div>
                    {/* 文本区 */}
                    <div className="flex flex-1 flex-col p-3">
                      <h4 className="line-clamp-1 text-sm font-bold text-slate-900 dark:text-slate-100">
                        {item.name}
                      </h4>
                      <p className="mt-1 line-clamp-1 flex items-center gap-1 text-xs text-slate-400 dark:text-slate-500">
                        <MapPin size={11} className="shrink-0" />
                        {item.address || '地址待补充'}
                      </p>
                      {/* 标签 */}
                      {item.tags.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {item.tags.slice(0, 3).map((tag) => (
                            <span
                              key={tag}
                              className="rounded-md bg-brand-50 dark:bg-brand-900/30 px-1.5 py-0.5 text-[10px] font-medium text-brand-600 dark:text-brand-400"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                      {/* 调度建议说明 */}
                      <div className="mt-2.5 flex items-start gap-1.5 rounded-lg bg-surface-secondary dark:bg-slate-800/40 p-2">
                        <span className={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${advice.dot}`} />
                        <p className="line-clamp-2 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
                          {item.schedule_advice.advice}
                        </p>
                      </div>
                      {/* 元信息 + 联动入口 */}
                      <div className="mt-2.5 flex items-center gap-3 text-[11px] text-slate-400 dark:text-slate-500">
                        <span className="flex items-center gap-0.5">
                          <DollarSign size={11} />
                          {formatPrice(item)}
                        </span>
                        {item.best_time && (
                          <span className="flex items-center gap-0.5">
                            <Clock size={11} />
                            <span className="line-clamp-1">{item.best_time}</span>
                          </span>
                        )}
                      </div>
                      <div className="mt-3 flex gap-2 border-t border-border-light pt-2.5">
                        <Link
                          to={`/guide?q=${encodeURIComponent(item.name)}`}
                          className="flex-1 rounded-lg bg-brand-50 dark:bg-brand-900/30 py-1.5 text-center text-xs font-medium text-brand-600 dark:text-brand-400 transition-colors hover:bg-brand-100 dark:hover:bg-brand-900/50"
                        >
                          AI 导游讲解
                        </Link>
                        <button
                          onClick={() => navigate(`/chat?q=${encodeURIComponent(`广州${item.name}游览攻略`)}`)}
                          className="flex-1 rounded-lg bg-accent-50 dark:bg-accent-900/30 py-1.5 text-center text-xs font-medium text-accent-600 dark:text-accent-400 transition-colors hover:bg-accent-100 dark:hover:bg-accent-900/50"
                        >
                          规划行程
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>

        {/* 底部说明 */}
        <footer className="mt-10 text-center text-xs text-slate-400 dark:text-slate-500">
          <p>数据来源：attractions.json 真实统计 · 调度建议基于热度启发式</p>
          <p className="mt-1">价格/热度如有变动，以景区官方信息为准</p>
        </footer>
      </main>
    </div>
  )
}
