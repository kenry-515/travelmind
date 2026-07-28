import { lazy, Suspense, useEffect, useCallback } from 'react'
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom'
import { ToastContainer } from './components/Toast'
import { MobileNav } from './components/MobileNav'
import { ThemeToggle } from './components/ThemeToggle'
import { ErrorBoundary } from './components/ErrorBoundary'
import { SkeletonItinerary } from './components/Skeleton'
import { SavedPlacesProvider } from './lib/savedPlaces'
import { SavedPlacesSidebar } from './components/SavedPlacesSidebar'

// Phase 12.29b: 路由级代码分割 — 每个页面独立 chunk，首屏仅加载首页
const HomePage = lazy(() => import('./pages/HomePage').then(m => ({ default: m.HomePage })))
const ChatPage = lazy(() => import('./pages/ChatPage').then(m => ({ default: m.ChatPage })))
const RecommendPage = lazy(() => import('./pages/RecommendPage').then(m => ({ default: m.RecommendPage })))
const ItineraryPage = lazy(() => import('./pages/ItineraryPage').then(m => ({ default: m.ItineraryPage })))
const ImagePage = lazy(() => import('./pages/ImagePage').then(m => ({ default: m.ImagePage })))
const HistoryPage = lazy(() => import('./pages/HistoryPage').then(m => ({ default: m.HistoryPage })))

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
    <SavedPlacesProvider>
    <BrowserRouter>
      <KeyboardShortcuts />
      <ToastContainer />

      {/* Saved places sidebar */}
      <SavedPlacesSidebar />

      {/* Floating theme toggle */}
      <div className="fixed bottom-24 right-4 z-50 sm:top-4 sm:bottom-auto">
        <ThemeToggle />
      </div>

      <Routes>
        <Route path="/" element={
          <Suspense fallback={<div className="p-8"><SkeletonItinerary /></div>}>
            <ErrorBoundary><HomePage /></ErrorBoundary>
          </Suspense>
        } />
        <Route path="/chat" element={
          <Suspense fallback={<div className="p-8"><SkeletonItinerary /></div>}>
            <ErrorBoundary><ChatPage /></ErrorBoundary>
          </Suspense>
        } />
        <Route path="/recommend" element={
          <Suspense fallback={<div className="p-8"><SkeletonItinerary /></div>}>
            <ErrorBoundary><RecommendPage /></ErrorBoundary>
          </Suspense>
        } />
        <Route path="/itinerary" element={
          <Suspense fallback={<div className="p-8"><SkeletonItinerary /></div>}>
            <ErrorBoundary><ItineraryPage /></ErrorBoundary>
          </Suspense>
        } />
        <Route path="/image" element={
          <Suspense fallback={<div className="p-8"><SkeletonItinerary /></div>}>
            <ErrorBoundary><ImagePage /></ErrorBoundary>
          </Suspense>
        } />
        <Route path="/history" element={
          <Suspense fallback={<div className="p-8"><SkeletonItinerary /></div>}>
            <ErrorBoundary><HistoryPage /></ErrorBoundary>
          </Suspense>
        } />
      </Routes>
      <MobileNav />
    </BrowserRouter>
    </SavedPlacesProvider>
  )
}

export default App
