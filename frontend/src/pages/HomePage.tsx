import { useNavigate, Link } from 'react-router-dom'
import { SearchInput } from '../components/SearchInput'
import { ExampleQuestions } from '../components/ExampleQuestions'
import { Sparkles, MessageCircle, Camera, List } from 'lucide-react'

const QUICK_LINKS = [
  { to: '/recommend', icon: Sparkles, label: '智能推荐', desc: '热门目的地排行与评分', tint: 'from-brand-100 to-brand-50 text-brand-500' },
  { to: '/chat', icon: MessageCircle, label: 'AI 对话', desc: '多轮对话式规划行程', tint: 'from-accent-100 to-accent-50 text-accent-600' },
  { to: '/image', icon: Camera, label: '图片识别', desc: '上传图片智能识别景点', tint: 'from-amber-100 to-amber-50 text-amber-500' },
  { to: '/history', icon: List, label: '我的行程', desc: '历史行程与收藏管理', tint: 'from-purple-100 to-purple-50 text-purple-500' },
]

export function HomePage() {
  const navigate = useNavigate()

  const handleSearch = (query: string) => {
    navigate(`/chat?q=${encodeURIComponent(query)}`)
  }

  return (
    <main className="grain relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-4 py-8 pb-20 sm:pb-8">
      {/* 动态极光背景（Phase 12.24 视觉 2.0） */}
      <div aria-hidden className="aurora">
        <span /><span /><span />
      </div>

      {/* Header */}
      <div className="relative mb-6 animate-fade-in-up text-center">
        <div className="mb-4 inline-flex items-center gap-1.5 rounded-full border border-brand-200 bg-white dark:bg-slate-900/70 px-3 py-1 text-xs font-medium text-brand-600 backdrop-blur">
          <Sparkles size={12} />
          AI 多智能体 · 真实数据校验
        </div>
        <h1 className="display-xl mb-3">
          <span className="align-middle">✈️</span>{' '}
          <span className="text-gradient">TravelMind</span>
        </h1>
        <p className="text-base leading-relaxed text-slate-500 dark:text-slate-400 sm:text-lg">
          AI 智能旅行规划助手 — <span className="font-medium text-slate-700 dark:text-slate-300">一句话，生成完美旅程</span>
        </p>
      </div>

      {/* Search */}
      <div className="focus-glow relative flex w-full justify-center rounded-2xl transition-shadow animate-fade-in-up [animation-delay:80ms]">
        <SearchInput onSearch={handleSearch} />
      </div>

      {/* 示例问题 — 一句话就能开始 */}
      <div className="relative flex w-full justify-center animate-fade-in-up [animation-delay:120ms]">
        <ExampleQuestions onSelect={handleSearch} />
      </div>

      {/* Quick Nav — 产品核心入口 */}
      <div className="stagger relative mt-6 grid w-full max-w-lg grid-cols-2 gap-3">
        {QUICK_LINKS.map(({ to, icon: Icon, label, desc, tint }) => (
          <Link
            key={to}
            to={to}
            className="card card-glow flex flex-col items-start gap-1.5 p-4"
          >
            <span className={`flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br ${tint}`}>
              <Icon size={18} />
            </span>
            <span className="text-sm font-bold text-slate-800 dark:text-slate-200">{label}</span>
            <span className="text-xs leading-relaxed text-slate-400 dark:text-slate-500">{desc}</span>
          </Link>
        ))}
      </div>

      {/* Footer */}
      <footer className="relative mt-8 text-center text-xs text-slate-400 dark:text-slate-500">
        <p>TravelMind Agent · Multi-Agent Travel Planner</p>
        <p className="mt-1">Powered by DeepSeek · Kimi Vision · Open-Meteo · Amap · Chroma</p>
      </footer>
    </main>
  )
}
