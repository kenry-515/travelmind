import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { HomePage } from './pages/HomePage'
import { ChatPage } from './pages/ChatPage'
import { RecommendPage } from './pages/RecommendPage'
import { ItineraryPage } from './pages/ItineraryPage'
import { ImagePage } from './pages/ImagePage'
import { HistoryPage } from './pages/HistoryPage'
import { ToastContainer } from './components/Toast'

function App() {
  return (
    <BrowserRouter>
      <ToastContainer />
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/recommend" element={<RecommendPage />} />
        <Route path="/itinerary" element={<ItineraryPage />} />
        <Route path="/image" element={<ImagePage />} />
        <Route path="/history" element={<HistoryPage />} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
