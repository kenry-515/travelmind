/**
 * 羊城智游 — MobileNav
 *
 * Fixed bottom navigation bar visible only on small screens (<640px).
 * Focused on Guangzhou-specific core features.
 */

import { useLocation, Link } from 'react-router-dom'
import { Home, MessageCircle, Compass, Award } from 'lucide-react'

const NAV_ITEMS = [
  { to: '/', icon: Home, label: '首页' },
  { to: '/guide', icon: Compass, label: '导游' },
  { to: '/chat', icon: MessageCircle, label: '规划' },
  { to: '/resources', icon: Award, label: '资源' },
]

export function MobileNav() {
  const { pathname } = useLocation()

  return (
    <nav className="glass fixed bottom-0 left-0 right-0 z-30 border-t border-border-light sm:hidden safe-area-bottom">
      <div className="flex items-center justify-around py-1.5">
        {NAV_ITEMS.map(({ to, icon: Icon, label }) => {
          const active = to === '/' ? pathname === '/' : pathname.startsWith(to)
          return (
            <Link
              key={to}
              to={to}
              className={`flex flex-col items-center gap-0.5 rounded-xl px-3 py-1.5 text-xs transition-all ${
                active
                  ? 'bg-brand-50 dark:bg-brand-900/40 text-brand-600 dark:text-brand-400'
                  : 'text-slate-400 dark:text-slate-500 hover:text-slate-600 dark:hover:text-slate-300'
              }`}
              aria-label={label}
              aria-current={active ? 'page' : undefined}
            >
              <Icon size={18} strokeWidth={active ? 2.5 : 2} />
              <span className={active ? 'font-semibold' : ''}>{label}</span>
            </Link>
          )
        })}
      </div>
    </nav>
  )
}
