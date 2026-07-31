import { lazy, Suspense, useEffect, useCallback } from 'react'
import { BrowserRouter, Routes, Route, useNavigate } from 'react-router-dom'
import { ToastContainer } from './components/Toast'
import { MobileNav } from './components/MobileNav'
import { ThemeToggle } from './components/ThemeToggle'
import { ErrorBoundary } from './components/ErrorBoundary'
import { SkeletonItinerary } from './components/Skeleton'
import { SavedPlacesProvider } from './lib/savedPlaces'
import { SavedPlacesSidebar } from './components/SavedPlacesSidebar'

// 羊城智游 — 路由级代码分割
const HomePage = lazy(() => import('./pages/HomePage').then(m => ({ default: m.HomePage })))
const ChatPage = lazy(() => import('./pages/ChatPage').then(m => ({ default: m.ChatPage })))
const ItineraryPage = lazy(() => import('./pages/ItineraryPage').then(m => ({ default: m.ItineraryPage })))
const ImagePage = lazy(() => import('./pages/ImagePage').then(m => ({ default: m.ImagePage })))
const HistoryPage = lazy(() => import('./pages/HistoryPage').then(m => ({ default: m.HistoryPage })))
const GuidePage = lazy(() => import('./pages/GuidePage').then(m => ({ default: m.GuidePage })))
const ResourcesPage = lazy(() => import('./pages/ResourcesPage').then(m => ({ default: m.ResourcesPage })))

/** Keyboard shortcut handler */
function KeyboardShortcuts() {
  const navigate = useNavigate()

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault()
        navigate('/chat')
      }
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
        <Route path="/guide" element={
          <Suspense fallback={<div className="p-8"><SkeletonItinerary /></div>}>
            <ErrorBoundary><GuidePage /></ErrorBoundary>
          </Suspense>
        } />
        <Route path="/resources" element={
          <Suspense fallback={<div className="p-8"><SkeletonItinerary /></div>}>
            <ErrorBoundary><ResourcesPage /></ErrorBoundary>
          </Suspense>
        } />
      </Routes>
      <MobileNav />
    </BrowserRouter>
    </SavedPlacesProvider>
  )
}

export default App
