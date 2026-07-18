/**
 * TravelMind Agent — ImagePage
 *
 * Upload a travel photo and let the Kimi vision model (kimi-k2.6) recognize
 * the location, landmark features, and style/mood tags — then close the
 * multimodal loop by finding similar attractions from the same tags
 * (RAG → 6-factor scoring via /recommend/quick).
 */

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import axios from 'axios'
import {
  ArrowLeft, AlertCircle, MapPin, Tag, FileText, Landmark, Loader2, TrendingUp,
} from 'lucide-react'
import { ImageUploader } from '../components/ImageUploader'
import { PlaceCard } from '../components/PlaceCard'
import { toast } from '../components/Toast'
import {
  analyzeImage,
  fetchQuickRecommendations,
  fetchWeatherCities,
  type ImageAnalyzeResult,
  type PlaceItem,
} from '../lib/api'

type PageState =
  | { stage: 'idle' }
  | { stage: 'loading' }
  | { stage: 'done'; result: ImageAnalyzeResult }
  | { stage: 'error'; message: string }

type RecState =
  | { stage: 'idle' }
  | { stage: 'loading' }
  | { stage: 'done'; city: string; places: PlaceItem[] }
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
  const [cities, setCities] = useState<string[]>([])
  const [city, setCity] = useState('')
  const [recState, setRecState] = useState<RecState>({ stage: 'idle' })

  // 加载城市列表（与知识库相同的 10 个城市）
  useEffect(() => {
    fetchWeatherCities()
      .then((list) => setCities(list.map((c) => c.name)))
      .catch(() => toast.warning('城市列表加载失败，相似推荐可能不可用'))
  }, [])

  // 分析完成后，尝试从识别出的地点名中推断城市（如「西湖」→ 不含城市名则不推断）
  useEffect(() => {
    if (state.stage === 'done' && state.result.location) {
      const matched = cities.find((c) => state.result.location.includes(c))
      if (matched) setCity(matched)
    }
  }, [state, cities])

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

  const handleRecommend = async () => {
    if (state.stage !== 'done') return
    if (!city) {
      toast.warning('请先选择城市')
      return
    }
    const tags = state.result.tags
    if (tags.length === 0) {
      toast.warning('没有可用的风格标签，无法推荐')
      return
    }
    setRecState({ stage: 'loading' })
    try {
      const data = await fetchQuickRecommendations({ city, tags, top_k: 6 })
      setRecState({ stage: 'done', city: data.city, places: data.places })
    } catch (err: unknown) {
      setRecState({ stage: 'error', message: resolveErrorMessage(err) })
    }
  }

  const confidencePercent = (c: number) => `${Math.round(c * 100)}%`

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center gap-3 px-4 py-3">
          <Link
            to="/"
            className="rounded-lg p-1.5 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-700"
            aria-label="返回首页"
          >
            <ArrowLeft size={20} />
          </Link>
          <h2 className="text-sm font-semibold text-slate-800">图片识别</h2>
          <span className="text-xs text-slate-400">
            上传旅行照片，AI 识别地点与风格标签
          </span>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-6">
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
          <div className="mt-6 space-y-4 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            {/* Location */}
            <div className="flex items-start gap-3">
              <MapPin size={18} className="mt-0.5 shrink-0 text-blue-500" />
              <div>
                <p className="text-xs font-medium text-slate-400">识别地点</p>
                {state.result.location ? (
                  <p className="text-base font-semibold text-slate-800">
                    {state.result.location}
                    <span className="ml-2 rounded-full bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-600">
                      置信度 {confidencePercent(state.result.confidence)}
                    </span>
                  </p>
                ) : (
                  <p className="text-sm text-slate-500">未能识别出具体地点</p>
                )}
              </div>
            </div>

            {/* Landmark features */}
            {state.result.landmark_features && (
              <div className="flex items-start gap-3">
                <Landmark size={18} className="mt-0.5 shrink-0 text-amber-500" />
                <div>
                  <p className="text-xs font-medium text-slate-400">地标特征</p>
                  <p className="text-sm text-slate-700">{state.result.landmark_features}</p>
                </div>
              </div>
            )}

            {/* Description */}
            {state.result.description && (
              <div className="flex items-start gap-3">
                <FileText size={18} className="mt-0.5 shrink-0 text-slate-400" />
                <div>
                  <p className="text-xs font-medium text-slate-400">图片描述</p>
                  <p className="text-sm text-slate-700">{state.result.description}</p>
                </div>
              </div>
            )}

            {/* Tags */}
            {state.result.tags.length > 0 && (
              <div className="flex items-start gap-3">
                <Tag size={18} className="mt-0.5 shrink-0 text-green-500" />
                <div>
                  <p className="text-xs font-medium text-slate-400">风格标签</p>
                  <div className="mt-1 flex flex-wrap gap-2">
                    {state.result.tags.map((tag) => (
                      <span
                        key={tag}
                        className="rounded-full bg-green-50 px-3 py-1 text-xs font-medium text-green-700"
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

        {/* Similar attractions — closes the multimodal loop */}
        {state.stage === 'done' && (
          <div className="mt-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-800">
              <TrendingUp size={16} className="text-blue-500" />
              找相似景点
            </div>
            <p className="mt-1 text-xs text-slate-400">
              用图片的风格标签，在知识库中匹配相似景点（RAG + 6 因子打分）
            </p>
            <div className="mt-3 flex items-center gap-3">
              <select
                value={city}
                onChange={(e) => setCity(e.target.value)}
                className="rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-700 shadow-sm focus:border-blue-400 focus:outline-none"
                aria-label="选择城市"
              >
                <option value="">选择城市</option>
                {cities.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <button
                onClick={handleRecommend}
                disabled={recState.stage === 'loading' || !city}
                className="flex items-center gap-2 rounded-xl bg-blue-600 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-blue-700 disabled:opacity-50"
              >
                {recState.stage === 'loading' && (
                  <Loader2 size={16} className="animate-spin" />
                )}
                {recState.stage === 'loading' ? '推荐中...' : '开始推荐'}
              </button>
            </div>

            {recState.stage === 'error' && (
              <div className="mt-4 flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                <AlertCircle size={18} className="mt-0.5 shrink-0" />
                <span>{recState.message}</span>
              </div>
            )}

            {recState.stage === 'done' &&
              (recState.places.length > 0 ? (
                <div className="mt-4 grid gap-4 sm:grid-cols-2">
                  {recState.places.map((place, i) => (
                    <PlaceCard key={place.name} place={place} rank={i + 1} />
                  ))}
                </div>
              ) : (
                <p className="mt-4 text-sm text-slate-500">
                  在「{recState.city}」未找到匹配景点，换个城市或标签试试。
                </p>
              ))}
          </div>
        )}

        {/* Hint */}
        {state.stage === 'idle' && (
          <p className="mt-6 text-center text-xs text-slate-400">
            识别结果中的标签可直接用于智能推荐，帮你找到相似风格的景点
          </p>
        )}
      </main>
    </div>
  )
}
