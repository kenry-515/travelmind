/**
 * TravelMind Agent — API Client
 * Axios instance with base URL + typed API functions.
 */

import axios from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Response interceptor for error handling
api.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error('[API Error]', error.response?.data || error.message)
    return Promise.reject(error)
  }
)

// ── Types ────────────────────────────────────────────────

export interface ScoreBreakdown {
  preference_match: number
  trend_heat: number
  budget_match: number
  location_efficiency: number
  time_match: number
  data_reliability: number
}

export interface PlaceItem {
  name: string
  city: string
  tags: string[]
  price_level: string
  best_time: string
  suitable_for: string
  total_score: number
  score_breakdown: ScoreBreakdown
}

export interface TrendEntry {
  name: string
  score: number
  tag: string
  source: string
}

export interface RecommendResponse {
  city: string
  total_results: number
  places: PlaceItem[]
  trend_summary: {
    total: number
    top_trending: TrendEntry[]
  }
}

export interface DayAttraction {
  name: string
  time: string
  duration_min: number
  notes: string
}

export interface DayMeal {
  type: string
  suggestion: string
}

export interface DayPlan {
  day: number
  theme: string
  attractions: DayAttraction[]
  meals: DayMeal[]
  transport_tips: string
}

export interface ItineraryData {
  overview: string
  days: number
  plan: DayPlan[]
  general_tips: string
}

export interface PlanResponse {
  user_input: string
  user_profile: Record<string, unknown> | null
  recommendations: PlaceItem[] | null
  itinerary: ItineraryData | null
  weather: WeatherForecast | null
  current_step: string
  error: string | null
}

export interface DailyWeather {
  date: string
  temp_max: number
  temp_min: number
  precipitation: number
  weather_code: number
  weather_desc: string
  wind_speed_max: number
  travel_score: number
}

export interface WeatherForecast {
  city: string
  overall_score: number
  advice: string
  daily: DailyWeather[]
}

export interface WeatherAdvice {
  city: string
  overall_score: number
  advice: string
  daily_summary: {
    date: string
    weather: string
    temp: string
    rain: string
    travel_score: number
  }[]
  warnings: string[]
}

// ── API Functions ─────────────────────────────────────────

/** Run the full travel planning workflow (Profile → Trend → Weather → RAG → Recommend → Plan). */
export async function fetchPlan(userInput: string): Promise<PlanResponse> {
  const { data } = await api.post<PlanResponse>('/agent/plan', {
    user_input: userInput,
  })
  return data
}

/** Get ranked recommendations (stops before LLM itinerary generation — faster). */
export async function fetchRecommendations(userInput: string): Promise<RecommendResponse> {
  const { data } = await api.post<RecommendResponse>('/recommend', {
    user_input: userInput,
  })
  return data
}

/** Quick recommendations with pre-extracted parameters. */
export async function fetchQuickRecommendations(params: {
  city: string
  tags: string[]
  budget?: string
  travel_month?: number
  top_k?: number
}): Promise<{ city: string; total_results: number; places: PlaceItem[] }> {
  const { data } = await api.post('/recommend/quick', {
    city: params.city,
    tags: params.tags,
    budget: params.budget || '适中',
    travel_month: params.travel_month || 0,
    top_k: params.top_k || 20,
  })
  return data
}

/** Get weather forecast for a city. */
export async function fetchWeather(city: string, days = 5): Promise<WeatherForecast> {
  const { data } = await api.get<WeatherForecast>(`/weather/${encodeURIComponent(city)}`, {
    params: { days },
  })
  return data
}

/** Get simplified travel weather advice. */
export async function fetchWeatherAdvice(city: string, days = 5): Promise<WeatherAdvice> {
  const { data } = await api.post<WeatherAdvice>(
    '/weather/travel-advice',
    null,
    { params: { city, days } }
  )
  return data
}


// ── Image Analysis (Phase 5) ────────────────────────────

export interface ImageAnalyzeResult {
  location: string
  landmark_features: string
  tags: string[]
  description: string
  confidence: number
}

/** Analyze an uploaded travel photo with the Kimi vision model (kimi-k2.6). */
export async function analyzeImage(file: File): Promise<ImageAnalyzeResult> {
  const formData = new FormData()
  formData.append('image', file)
  // Vision inference can take tens of seconds — use a longer timeout than
  // the axios instance default (30s).
  // Content-Type: undefined removes the instance's default application/json
  // header so the browser sets multipart/form-data with the proper boundary.
  const { data } = await api.post<ImageAnalyzeResult>('/image/analyze', formData, {
    timeout: 90000,
    headers: { 'Content-Type': undefined },
  })
  return data
}
