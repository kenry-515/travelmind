import { useNavigate, Link } from 'react-router-dom'
import { SearchInput } from '../components/SearchInput'
import { ExampleQuestions } from '../components/ExampleQuestions'
import { Sparkles, MessageCircle, Camera, Compass, MapPin, ChevronRight, Award, Clock } from 'lucide-react'

// 广州专属核心入口 —— 移除多城市推荐，聚焦本地化核心服务
const QUICK_LINKS = [
  { to: '/guide', icon: Compass, label: 'AI 虚拟导游', desc: '广州景点智能讲解伴游', tint: 'from-emerald-100 to-emerald-50 text-emerald-600' },
  { to: '/chat', icon: MessageCircle, label: 'AI 行程规划', desc: '多轮对话式定制广州行程', tint: 'from-brand-100 to-brand-50 text-brand-500' },
  { to: '/image', icon: Camera, label: '拍照识景', desc: '上传照片智能识别广州景点', tint: 'from-amber-100 to-amber-50 text-amber-500' },
  { to: '/resources', icon: Award, label: '资源调度', desc: '广州景区热度可视化与错峰建议', tint: 'from-accent-100 to-accent-50 text-accent-600' },
]

// 广州 AI+旅游休闲大赛 —— 预设经典路线
const GUANGZHOU_ROUTES: {
  emoji: string
  title: string
  duration: string
  desc: string
  spots: string[]
  query: string
  tag: string
}[] = [
  {
    emoji: '🏮',
    title: '西关文化非遗游',
    duration: '1日',
    desc: '漫步永庆坊与上下九，品味老广州的骑楼与粤剧韵味',
    spots: ['永庆坊', '上下九步行街', '陈家祠', '荔枝湾涌'],
    query: '广州西关文化一日游，想体验老广州骑楼和非遗文化',
    tag: '文化非遗',
  },
  {
    emoji: '🌉',
    title: '珠江夜游地标游',
    duration: '1日',
    desc: '傍晚登船赏两岸霓虹，感受花城地标之光',
    spots: ['广州塔', '海心沙', '珠江夜游', '花城广场'],
    query: '广州珠江夜游一日游，想看广州塔和花城广场夜景',
    tag: '夜景地标',
  },
  {
    emoji: '🍜',
    title: '粤式美食寻味游',
    duration: '1日',
    desc: '从早茶到宵夜，一路打卡地道粤菜与老字号',
    spots: ['点都德', '莲香楼', '荔湾美食街', '北京路'],
    query: '广州美食一日游，想体验早茶和地道粤菜',
    tag: '美食寻味',
  },
  {
    emoji: '🌳',
    title: '都市休闲亲子游',
    duration: '2日',
    desc: '长隆欢乐世界加动物园，两天满满亲子欢乐时光',
    spots: ['长隆欢乐世界', '长隆野生动物世界', '广州动物园'],
    query: '广州亲子两日游，想去长隆乐园和野生动物世界',
    tag: '亲子休闲',
  },
]

// 广州特色标签云
const GUANGZHOU_TAGS = [
  '早茶', '骑楼', '粤语', '陈家祠', '南越文化', '珠江夜景', '广州塔',
  '长隆', '北京路', '上下九', '沙面', '荔枝湾', '花城广场', '白云山',
  '粤菜', '糖水', '煲仔饭', '老字号', '非遗'
]

export function HomePage() {
  const navigate = useNavigate()

  const handleSearch = (query: string) => {
    // 自动追加广州上下文（如果用户没写）
    const finalQuery = query.includes('广州') ? query : `广州 ${query}`
    navigate(`/chat?q=${encodeURIComponent(finalQuery)}`)
  }

  return (
    <main className="grain relative flex min-h-screen flex-col items-center justify-center overflow-hidden px-4 py-8 pb-20 sm:pb-8">
      {/* Hero Background —— 广州城市意象渐变（珠江蓝 + 骑楼橙） */}
      <div aria-hidden className="hero-guangzhou">
        <span />
        <span />
        <span />
      </div>

      {/* Hero Content */}
      <div className="relative mb-6 animate-fade-in-up text-center z-10">
        <div className="mb-4 inline-flex items-center gap-1.5 rounded-full border border-brand-300 bg-white/80 dark:bg-slate-900/80 px-3 py-1 text-xs font-medium text-brand-700 dark:text-brand-400 backdrop-blur">
          <Sparkles size={12} />
          AI+旅游休闲大赛 · 广州专用智能体
        </div>
        <h1 className="display-xl mb-3">
          <span className="text-gradient">羊城智游</span>
        </h1>
        <p className="text-base leading-relaxed text-slate-600 dark:text-slate-300 sm:text-lg font-medium">
          广州专属 AI 旅行规划助手 — <span className="text-brand-600 dark:text-brand-400">一句话，定制你的花城之旅</span>
        </p>
      </div>

      {/* Search —— 锁定广州 */}
      <div className="focus-glow relative flex w-full justify-center rounded-2xl transition-shadow animate-fade-in-up [animation-delay:80ms] z-10">
        <SearchInput 
          onSearch={handleSearch} 
          placeholder="描述你想要的广州旅行，如：周末带家人游西关..."
        />
      </div>

      {/* 示例问题 —— 广州本地场景 */}
      <div className="relative flex w-full justify-center animate-fade-in-up [animation-delay:120ms] z-10">
        <ExampleQuestions onSelect={handleSearch} />
      </div>

      {/* 广州特色标签云 —— 快速灵感 */}
      <div className="relative mt-6 w-full max-w-2xl animate-fade-in-up [animation-delay:140ms] z-10">
        <div className="flex flex-wrap justify-center gap-2">
          {GUANGZHOU_TAGS.map((tag) => (
            <button
              key={tag}
              onClick={() => handleSearch(`关于广州${tag}的攻略`)}
              className="tag-chip rounded-full border border-brand-200 bg-white/70 dark:bg-slate-900/50 px-3 py-1 text-xs text-brand-700 dark:text-brand-300 backdrop-blur hover:bg-brand-50 dark:hover:bg-brand-900/40 hover:shadow-md"
            >
              #{tag}
            </button>
          ))}
        </div>
      </div>

      {/* Quick Nav —— 广州核心服务 */}
      <div className="stagger relative mt-6 grid w-full max-w-lg grid-cols-2 gap-3 z-10">
        {QUICK_LINKS.map(({ to, icon: Icon, label, desc, tint }) => (
          <Link
            key={to}
            to={to}
            className="card card-glow flex flex-col items-start gap-1.5 p-4 hover-lift"
          >
            <span className={`flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br ${tint}`}>
              <Icon size={18} />
            </span>
            <span className="text-sm font-bold text-slate-800 dark:text-slate-200">{label}</span>
            <span className="text-xs leading-relaxed text-slate-500 dark:text-slate-400">{desc}</span>
          </Link>
        ))}
      </div>

      {/* 广州景区资源调度 —— 大赛核心功能 */}
      <div className="relative mt-6 w-full max-w-2xl animate-fade-in-up [animation-delay:160ms] z-10">
        <Link
          to="/resources"
          className="card card-glow hover-lift group flex items-center gap-4 p-4"
        >
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand-100 to-accent-100 dark:from-slate-800 dark:to-slate-700">
            <Award size={22} className="text-brand-500" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <p className="text-sm font-bold text-slate-800 dark:text-slate-200">
                广州景区资源调度中心
              </p>
              <span className="badge-pulse rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400">
                大赛核心场景
              </span>
            </div>
            <p className="mt-0.5 text-xs leading-relaxed text-slate-500 dark:text-slate-400">
              168+ 广州景区实时热度 · 智能错峰调度 · 客流压力可视化
            </p>
          </div>
          <ChevronRight size={18} className="shrink-0 text-slate-300 transition-transform group-hover:translate-x-1 group-hover:text-brand-500 dark:text-slate-600" />
        </Link>
      </div>

      {/* 广州智能旅行体验 —— 精选预设路线 */}
      <div className="relative mt-10 w-full max-w-2xl animate-fade-in-up [animation-delay:200ms] z-10">
        <div className="mb-4 flex items-center gap-2">
          <MapPin size={18} className="text-brand-500" />
          <h2 className="text-base font-bold text-slate-800 dark:text-slate-200">
            广州精选体验
          </h2>
          <span className="rounded-full bg-brand-100 px-2 py-0.5 text-[10px] font-medium text-brand-700 dark:bg-brand-900/40 dark:text-brand-400">
            热门路线
          </span>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {GUANGZHOU_ROUTES.map((route) => (
            <button
              key={route.title}
              onClick={() => handleSearch(route.query)}
              className="card route-card hover-lift group flex flex-col gap-2 p-4 text-left relative overflow-hidden"
            >
              {/* Tag */}
              <span className="absolute right-3 top-3 rounded-full bg-brand-50 dark:bg-brand-900/30 px-2 py-0.5 text-[10px] font-medium text-brand-600 dark:text-brand-400">
                {route.tag}
              </span>
              
              <div className="flex items-center gap-2">
                <span className="text-2xl">{route.emoji}</span>
                <span className="text-[10px] text-slate-400 dark:text-slate-500 flex items-center gap-0.5">
                  <Clock size={10} /> {route.duration}
                </span>
              </div>
              
              <div>
                <p className="text-sm font-bold text-slate-800 dark:text-slate-200">{route.title}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-slate-500 dark:text-slate-400 pr-12">{route.desc}</p>
              </div>
              
              <div className="flex flex-wrap gap-1">
                {route.spots.slice(0, 3).map((spot) => (
                  <span key={spot} className="rounded-md bg-slate-100 dark:bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-600 dark:text-slate-400">
                    {spot}
                  </span>
                ))}
                {route.spots.length > 3 && (
                  <span className="text-[10px] text-slate-400">+{route.spots.length - 3}</span>
                )}
              </div>
              
              <span className="mt-1 text-xs font-medium text-brand-500 opacity-0 transition-opacity group-hover:opacity-100 flex items-center gap-1">
                点击体验 <ChevronRight size={12} />
              </span>
            </button>
          ))}
        </div>
      </div>

      {/* Footer */}
      <footer className="relative mt-8 text-center text-xs text-slate-400 dark:text-slate-500 z-10">
        <p>羊城智游 · 广州专属 AI 旅行规划智能体</p>
        <p className="mt-1">Powered by AI+旅游休闲大赛 · 真实数据 · 168+ 广州景区覆盖</p>
      </footer>
    </main>
  )
}
