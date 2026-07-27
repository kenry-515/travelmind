/**
 * TravelMind Agent — ThemeToggle (Phase 12.28d)
 *
 * Sun/moon icon toggle for dark mode.
 * Persists preference to localStorage under "travelmind-theme".
 */

import { useState, useEffect } from 'react'
import { Sun, Moon } from 'lucide-react'

export function ThemeToggle() {
  const [dark, setDark] = useState(() => {
    if (typeof window === 'undefined') return false
    const stored = localStorage.getItem('travelmind-theme')
    if (stored) return stored === 'dark'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useEffect(() => {
    const root = document.documentElement
    if (dark) {
      root.classList.add('dark')
    } else {
      root.classList.remove('dark')
    }
    localStorage.setItem('travelmind-theme', dark ? 'dark' : 'light')
  }, [dark])

  return (
    <button
      onClick={() => setDark(!dark)}
      className="theme-toggle"
      aria-label={dark ? '切换到亮色模式' : '切换到暗色模式'}
      title={dark ? '切换到亮色模式' : '切换到暗色模式'}
    >
      {dark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  )
}
