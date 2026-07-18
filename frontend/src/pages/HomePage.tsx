import { useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { SearchInput } from '../components/SearchInput'
import { ExampleQuestions } from '../components/ExampleQuestions'
import { api } from '../lib/api'
import { Sparkles, MessageCircle, Map, Camera } from 'lucide-react'

type ServiceStatus = 'idle' | 'loading' | 'healthy' | 'degraded' | 'error'

export function HomePage() {
  const navigate = useNavigate()
  const [backendStatus, setBackendStatus] = useState<ServiceStatus>('idle')
  const [statusDetail, setStatusDetail] = useState('')

  const handleSearch = (query: string) => {
    navigate(`/chat?q=${encodeURIComponent(query)}`)
  }

  const handleExampleSelect = (question: string) => {
    navigate(`/chat?q=${encodeURIComponent(question)}`)
  }

  const checkHealth = async () => {
    setBackendStatus('loading')
    try {
      const { data } = await api.get('/health')
      if (data.status === 'ok') {
        setBackendStatus('healthy')
        setStatusDetail(
          `API: ${data.services.api} | Database: ${data.services.database} | v${data.version}`
        )
      } else {
        setBackendStatus('degraded')
        setStatusDetail(`API: ${data.services.api} | Database: ${data.services.database}`)
      }
    } catch (_err) {
      setBackendStatus('error')
      setStatusDetail('无法连接到后端服务，请确认后端已启动')
    }
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4 py-16">
      {/* Header */}
      <div className="mb-10 text-center">
        <h1 className="mb-3 text-5xl font-bold tracking-tight text-slate-900">
          ✈️ TravelMind
        </h1>
        <p className="text-lg text-slate-500">
          AI 智能旅行规划助手 — 一句话，生成完美旅程
        </p>
      </div>

      {/* Search */}
      <SearchInput onSearch={handleSearch} />

      {/* Quick Nav */}
      <div className="mt-6 flex gap-3">
        <Link
          to="/recommend"
          className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-medium text-slate-600 shadow-sm transition-all hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600"
        >
          <Sparkles size={18} />
          智能推荐
        </Link>
        <Link
          to="/chat"
          className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-medium text-slate-600 shadow-sm transition-all hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600"
        >
          <MessageCircle size={18} />
          AI 对话
        </Link>
        <Link
          to="/itinerary?q=推荐重庆3日游"
          className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-medium text-slate-600 shadow-sm transition-all hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600"
        >
          <Map size={18} />
          快速体验
        </Link>
        <Link
          to="/image"
          className="flex items-center gap-2 rounded-xl border border-slate-200 bg-white px-5 py-3 text-sm font-medium text-slate-600 shadow-sm transition-all hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600"
        >
          <Camera size={18} />
          图片识别
        </Link>
      </div>

      {/* Example Questions */}
      <ExampleQuestions onSelect={handleExampleSelect} />

      {/* Health Check */}
      <div className="mt-12 text-center">
        <button
          onClick={checkHealth}
          disabled={backendStatus === 'loading'}
          className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-600 shadow-sm transition-all hover:bg-slate-50 disabled:opacity-50"
        >
          {backendStatus === 'loading' ? '⏳ 检测中...' : '🔍 检测后端连接'}
        </button>

        {backendStatus !== 'idle' && backendStatus !== 'loading' && (
          <div
            className={`mt-3 inline-block rounded-lg px-4 py-2 text-sm ${
              backendStatus === 'healthy'
                ? 'bg-green-50 text-green-700'
                : backendStatus === 'degraded'
                  ? 'bg-yellow-50 text-yellow-700'
                  : 'bg-red-50 text-red-700'
            }`}
          >
            {backendStatus === 'healthy' && '✅ 后端连接正常'}
            {backendStatus === 'degraded' && '⚠️ 后端部分可用'}
            {backendStatus === 'error' && '❌ 后端连接失败'}
            {statusDetail && (
              <span className="ml-2 text-xs opacity-75">({statusDetail})</span>
            )}
          </div>
        )}
      </div>

      {/* Footer */}
      <footer className="mt-16 text-center text-xs text-slate-400">
        <p>TravelMind Agent — Phase 5 Multi-Agent Travel Planner</p>
        <p className="mt-1">Powered by DeepSeek · Kimi Vision · Open-Meteo · Amap · Chroma</p>
      </footer>
    </main>
  )
}
