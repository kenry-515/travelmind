/**
 * TravelMind Agent — ImagePage
 *
 * Upload a travel photo and let the Kimi vision model (kimi-k2.6) recognize
 * the location, landmark features, and style/mood tags — the multimodal
 * entry point of the recommendation pipeline.
 */

import { useState } from 'react'
import { Link } from 'react-router-dom'
import axios from 'axios'
import { ArrowLeft, AlertCircle, MapPin, Tag, FileText, Landmark } from 'lucide-react'
import { ImageUploader } from '../components/ImageUploader'
import { analyzeImage, type ImageAnalyzeResult } from '../lib/api'

type PageState =
  | { stage: 'idle' }
  | { stage: 'loading' }
  | { stage: 'done'; result: ImageAnalyzeResult }
  | { stage: 'error'; message: string }

/** Prefer the backend's friendly `detail` message over raw axios errors. */
function resolveErrorMessage(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = err.response?.data?.detail
    if (typeof detail === 'string' && detail) return detail
    if (err.code === 'ECONNABORTED') return '识别超时，请换一张更小的图片或稍后再试。'
  }
  return '图片分析服务暂不可用，请稍后重试。'
}

export function ImagePage() {
  const [state, setState] = useState<PageState>({ stage: 'idle' })

  const handleAnalyze = async (file: File) => {
    setState({ stage: 'loading' })
    try {
      const result = await analyzeImage(file)
      setState({ stage: 'done', result })
    } catch (err: unknown) {
      setState({ stage: 'error', message: resolveErrorMessage(err) })
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

        {/* Result */}
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
