/**
 * TravelMind Agent — ImagePage
 *
 * Upload a travel photo and let the Kimi vision model (kimi-k2.6) recognize
 * the location, landmark features, and style/mood tags — then close the
 * multimodal loop by finding similar attractions from the same tags
 * (RAG → 6-factor scoring via /recommend/quick).
 */

import { useEffect, useState, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import axios from 'axios'
import {
  ArrowLeft, AlertCircle, MapPin, Tag, FileText, Landmark, Loader2, TrendingUp, Sparkles, MessageCircle,
} from 'lucide-react'
import { ImageUploader } from '../components/ImageUploader'
import { PlaceCard } from '../components/PlaceCard'
import { toast } from '../components/Toast'
import {
  analyzeImage,
  fetchByTags,
  type ImageAnalyzeResult,
  type ByTagsResponse,
} from '../lib/api'

type PageState =
  | { stage: 'idle' }
  | { stage: 'loading' }
  | { stage: 'done'; result: ImageAnalyzeResult }
  | { stage: 'error'; message: string }

type RecState =
  | { stage: 'idle' }
  | { stage: 'loading' }
  | { stage: 'done'; data: ByTagsResponse }
  | { stage: 'error'; message: string }

/** Prefer the backend's friendly `detail` message over raw axios errors. */
function resolveErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    if (typeof detail === 'string' && detail) return detail
    if (err.code === 'ECONNABORTED') return '识别超时，请换一张更小的图片或稍后再试。'
  }
  return '服务暂不可用，请稍后重试。'
}

export function ImagePage() {
  const [state, setState] = useState<PageState>({ stage: 'idle' })
  const [recState, setRecState] = useState<RecState>({ stage: 'idle' })
  const recommendSentRef = useRef(false)
  const navigate = useNavigate()

  const handleAnalyze = async (file: File) => {
    setState({ stage: 'loading' })
    setRecState({ stage: 'idle' }) // 新图片清空上一轮推荐
    try {
      const result = await analyzeImage(file)
      setState({ stage: 'done', result })
    } catch (err: unknown) {
      setState({ stage: 'error', message: resolveErrorMessage(err) })
    }
  }

  // Auto-trigger similar places search when image analysis completes with tags
  useEffect(() => {
    if (state.stage === 'done' && state.result.tags.length > 0 && !recommendSentRef.current) {
      recommendSentRef.current = true
      handleRecommend().catch((err) => {
        console.error('Auto recommend failed:', err)
        setRecState({ stage: 'error', message: '相似地点推荐失败，请稍后重试。' })
      })
    }
  }, [state.stage])

  const handleRecommend = async () => {
    if (state.stage !== 'done') return
    const tags = state.result.tags
    if (tags.length === 0) {
      toast.warning('没有可用的风格标签，无法推荐')
      return
    }
    setRecState({ stage: 'loading' })
    try {
      const data = await fetchByTags({ tags, top_k: 20, min_score: 0.4 })
      setRecState({ stage: 'done', data })
    } catch (err: unknown) {
      setRecState({ stage: 'error', message: resolveErrorMessage(err) })
    }
  }

  const confidencePercent = (c: number) => `${Math.round(c * 100)}%`

  return (
    <div className="relative min-h-screen overflow-hidden bg-surface-secondary pb-20 sm:pb-0">
      {/* 弱化极光背景（Phase 12.24） */}
      <div aria-hidden className="aurora aurora-soft">
        <span /><span /><span />
      </div>
      {/* Header */}
      <header className="glass sticky top-0 z-10 border-b border-border-light">
        <div className="mx-auto flex max-w-5xl items-center gap-2 px-3 py-2.5 sm:gap-3 sm:px-4 sm:py-3">
          <Link
            to="/"
            className="rounded-xl p-1.5 text-slate-500 dark:text-slate-400 transition-colors hover:bg-brand-50 dark:hover:bg-brand-900/30 hover:text-brand-600 dark:hover:text-brand-400"
            aria-label="返回首页"
          >
            <ArrowLeft size={20} />
          </Link>
          <h2 className="text-sm font-semibold text-slate-800 dark:text-slate-200">图片识别</h2>
          <span className="hidden text-xs text-slate-400 dark:text-slate-500 sm:inline">
            上传旅行照片，AI 识别地点与风格标签
          </span>
        </div>
      </header>

      <main className="relative mx-auto max-w-3xl px-4 py-6">
        <ImageUploader onAnalyze={handleAnalyze} loading={state.stage === 'loading'} />

        {/* Error */}
        {state.stage === 'error' && (
          <div className="mt-6 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            <AlertCircle size={18} className="mt-0.5 shrink-0" />
            <span>{state.message}</span>
          </div>
        )}

        {/* Analysis result */}
        {state.stage === 'done' && (
          <div className="mt-6 animate-fade-in-up space-y-4 rounded-2xl border border-border bg-white dark:bg-slate-900 p-5 shadow-card">
            {/* Location */}
            <div className="flex items-start gap-3">
              <MapPin size={18} className="mt-0.5 shrink-0 text-brand-500" />
              <div>
                <p className="text-xs font-medium text-slate-400 dark:text-slate-500">识别地点</p>
                {state.result.location ? (
                  <p className="text-base font-bold text-slate-800 dark:text-slate-200">
                    {state.result.location}
                    <span className="ml-2 rounded-full bg-brand-50 dark:bg-brand-900/30 px-2 py-0.5 text-xs font-medium text-brand-600 dark:text-brand-400">
                      置信度 {confidencePercent(state.result.confidence)}
                    </span>
                  </p>
                ) : (
                  <p className="text-sm text-slate-500 dark:text-slate-400">未能识别出具体地点</p>
                )}
              </div>
            </div>

            {/* Landmark features */}
            {state.result.landmark_features && (
              <div className="flex items-start gap-3">
                <Landmark size={18} className="mt-0.5 shrink-0 text-amber-500" />
                <div>
                  <p className="text-xs font-medium text-slate-400 dark:text-slate-500">地标特征</p>
                  <p className="text-sm text-slate-700 dark:text-slate-300">{state.result.landmark_features}</p>
                </div>
              </div>
            )}

            {/* Description */}
            {state.result.description && (
              <div className="flex items-start gap-3">
                <FileText size={18} className="mt-0.5 shrink-0 text-slate-400 dark:text-slate-500" />
                <div>
                  <p className="text-xs font-medium text-slate-400 dark:text-slate-500">图片描述</p>
                  <p className="text-sm text-slate-700 dark:text-slate-300">{state.result.description}</p>
                </div>
              </div>
            )}

            {/* Tags */}
            {state.result.tags.length > 0 && (
              <div className="flex items-start gap-3">
                <Tag size={18} className="mt-0.5 shrink-0 text-green-500" />
                <div>
                  <p className="text-xs font-medium text-slate-400 dark:text-slate-500">风格标签</p>
                  <div className="mt-1 flex flex-wrap gap-2">
                    {state.result.tags.map((tag) => (
                      <span
                        key={tag}
                        className="rounded-full bg-green-50 dark:bg-green-900/30 px-3 py-1 text-xs font-medium text-green-700 dark:text-green-300"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Phase 16.4: 识别后衔接行程规划 */}
        {state.stage === 'done' && (state.result.location || state.result.tags.length > 0) && (
          <div className="mt-4 flex flex-wrap gap-2">
            {state.result.location && (
              <button
                onClick={() => navigate(`/itinerary?q=${encodeURIComponent(state.result.location!)}`)}
                className="btn-primary inline-flex items-center gap-1.5 px-4 py-2 text-sm"
              >
                <Sparkles size={16} />
                为「{state.result.location}」生成行程
              </button>
            )}
            <button
              onClick={() => {
                const q = [state.result.location, ...state.result.tags]
                  .filter(Boolean)
                  .join('、')
                navigate(`/chat?q=${encodeURIComponent(q)}`)
              }}
              className="btn-secondary inline-flex items-center gap-1.5 px-4 py-2 text-sm"
            >
              <MessageCircle size={16} />
              去对话规划
            </button>
          </div>
        )}

        {/* Similar attractions — cross-city search (Phase 12) */}
        {state.stage === 'done' && (
          <div className="mt-6 rounded-2xl border border-border bg-white dark:bg-slate-900 p-5 shadow-card">
            <div className="flex items-center gap-2 text-sm font-bold text-slate-800 dark:text-slate-200">
              <TrendingUp size={16} className="text-brand-500" />
              找相似景点
            </div>
            <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
              用图片的风格标签，全知识库跨城搜索相似景点
              {recState.stage === 'done' && recState.data.cities_covered.length > 0 &&
                `（覆盖 ${recState.data.cities_covered.length} 个城市）`}
            </p>

            {recState.stage === 'loading' && (
              <div className="mt-4 text-center py-4">
                <Loader2 size={24} className="mx-auto mb-2 animate-spin text-brand-500" />
                <p className="text-sm text-slate-500 dark:text-slate-400">全库搜索中...</p>
              </div>
            )}

            {recState.stage === 'error' && (
              <div className="mt-4 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                <AlertCircle size={18} className="mt-0.5 shrink-0" />
                <span>{recState.message}</span>
              </div>
            )}

            {recState.stage === 'done' &&
              (recState.data.places.length > 0 ? (
                <>
                  {/* City chips for quick visual grouping */}
                  {recState.data.cities_covered.length > 1 && (
                    <div className="mt-3 flex flex-wrap gap-1.5">
                      {recState.data.cities_covered.map((city) => (
                        <span
                          key={city}
                          className="rounded-full bg-accent-50 px-2.5 py-0.5 text-xs font-medium text-accent-700"
                        >
                          {city}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="mt-4 grid gap-4 sm:grid-cols-2">
                    {recState.data.places.map((place, i) => (
                      <PlaceCard key={`${place.city}-${place.name}-${i}`} place={place} rank={i + 1} />
                    ))}
                  </div>
                  {recState.data.filtered_results < recState.data.total_results && (
                    <p className="mt-3 text-xs text-slate-400 dark:text-slate-500">
                      已过滤 {recState.data.total_results - recState.data.filtered_results} 个低分结果
                      （阈值 {recState.data.filtered_results > 0 ? '0.4' : '-'}）
                    </p>
                  )}
                </>
              ) : (
                <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">
                  全库未找到匹配景点，换个图片或标签试试。
                  {recState.data.total_results > 0 && recState.data.filtered_results === 0 &&
                    `（${recState.data.total_results} 个候选均未达到最低匹配分数）`}
                </p>
              ))}
          </div>
        )}

        {/* Hint */}
        {state.stage === 'idle' && (
          <p className="mt-6 text-center text-xs text-slate-400 dark:text-slate-500">
            识别结果中的标签可直接用于智能推荐，帮你找到相似风格的景点
          </p>
        )}
      </main>
    </div>
  )
}
