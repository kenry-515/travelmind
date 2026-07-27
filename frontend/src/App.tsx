import { useEffect, useCallback } from 'react'
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom'
import { HomePage } from './pages/HomePage'
import { ChatPage } from './pages/ChatPage'
import { RecommendPage } from './pages/RecommendPage'
import { ItineraryPage } from './pages/ItineraryPage'
import { ImagePage } from './pages/ImagePage'
import { HistoryPage } from './pages/HistoryPage'
import { ToastContainer } from './components/Toast'
import { MobileNav } from './components/MobileNav'
import { ThemeToggle } from './components/ThemeToggle'

/** Keyboard shortcut handler (Phase 12.28d). */
function KeyboardShortcuts() {
  const navigate = useNavigate()

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      // Ctrl+K → go to chat (quick planning)
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        navigate('/chat')
      }
      // Esc → close any modal/focus (handled by individual components)
    },
    [navigate],
  )

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  return null
}

function App() {
  return (
    <BrowserRouter>
      <KeyboardShortcuts />
      <ToastContainer />

      {/* Floating theme toggle (Phase 12.28d) */}
      <div className="fixed top-4 right-4 z-50">
        <ThemeToggle />
      </div>

      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/recommend" element={<RecommendPage />} />
        <Route path="/itinerary" element={<ItineraryPage />} />
        <Route path="/image" element={<ImagePage />} />
        <Route path="/history" element={<HistoryPage />} />
      </Routes>
      <MobileNav />
    </BrowserRouter>
  )
}

export default App
