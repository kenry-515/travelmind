/**
 * TravelMind Agent — API Client
 * Axios instance with base URL + typed API functions.
 */

import axios from 'axios'
import { getDeviceId } from './deviceId'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Inject X-Device-ID header on every request for anonymous user identity
api.interceptors.request.use((config) => {
  config.headers['X-Device-ID'] = getDeviceId()
  return config
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
  weather: number  // Phase 12.28c: 天气感知 boost（Phase 12.16 起后端已返回）
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

// ── Itinerary contract types (generated from docs/itinerary.schema.json —
// run `npm run gen:types` to regenerate; only indexed aliases live here) ──

import type { TravelItinerary } from '../types/itinerary'

export type { TravelItinerary }
export type ItineraryTrip = TravelItinerary['trip']
export type TripStat = ItineraryTrip['stats'][number]
export type TripDay = TravelItinerary['days'][number]
export type DayItem = TripDay['items'][number]
export type BudgetItem = TravelItinerary['budget'][number]
export type ChecklistItem = TravelItinerary['checklist'][number]
export type ValidationReport = NonNullable<TravelItinerary['validation_report']>
export type PoiValidation = ValidationReport['poi'][number]
export type RouteValidation = ValidationReport['routes'][number]

// Phase 7: Price layer types (backward-compatible optional fields)
export interface PriceRange {
  min: number
  max: number
}

export interface PriceInfo {
  price_range?: PriceRange
  price_source?: string
  price_updated_at?: string
  booking_url?: string
}

export interface PriceSummary {
  total_estimate_min: number
  total_estimate_max: number
  priced_items: number
  total_items: number
  stale_items: number
  budget_slot: string
  over_budget: boolean
  over_budget_warning: string
}

/** Check if a price is stale (>90 days since last update) */
export function isPriceStale(updatedAt: string | undefined): boolean {
  if (!updatedAt) return true
  try {
    const updated = new Date(updatedAt)
    const now = new Date()
    const daysDiff = (now.getTime() - updated.getTime()) / (1000 * 60 * 60 * 24)
    return daysDiff > 90
  } catch {
    return true
  }
}

export interface PlanResponse {
  user_input: string
  user_profile: Record<string, unknown> | null
  recommendations: PlaceItem[] | null
  itinerary: TravelItinerary | null
  weather: WeatherForecast | null
  current_step: string
  error: string | null
  itinerary_id?: string | null
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

// ── API Functions ─────────────────────────────────────────

/** Get ranked recommendations (stops before LLM itinerary generation — faster). */
export async function fetchRecommendations(userInput: string): Promise<RecommendResponse> {
  const { data } = await api.post<RecommendResponse>('/recommend', {
    user_input: userInput,
  })
  return data
}

/** Cross-city similar place search using image-recognized tags (Phase 12). */
export interface ByTagsResponse {
  total_results: number
  filtered_results: number
  cities_covered: string[]
  places: PlaceItem[]
}

export async function fetchByTags(params: {
  tags: string[]
  top_k?: number
  min_score?: number
}): Promise<ByTagsResponse> {
  const { data } = await api.post<ByTagsResponse>('/recommend/by-tags', {
    tags: params.tags,
    top_k: params.top_k || 20,
    min_score: params.min_score || 0.4,
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

// ── Image Analysis ───────────────────────────────────────

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


// ── Partial itinerary regeneration (局部重生成) ──────────

/** Regenerate one day of an itinerary from user feedback.
 *  Returns the full itinerary with only days[dayIndex] replaced. */
export async function regenerateDay(params: {
  itinerary: TravelItinerary
  dayIndex: number
  feedback: string
  userInput?: string
}): Promise<TravelItinerary> {
  const { data } = await api.post<{ itinerary: TravelItinerary }>(
    '/agent/plan/regenerate-day',
    {
      itinerary: params.itinerary,
      day_index: params.dayIndex,
      feedback: params.feedback,
      user_input: params.userInput,
    },
    { timeout: 90000 }
  )
  return data.itinerary
}


// ── Conversational Planning (对话式规划 · 意图层) ─────────

export interface DialogSlots {
  city: string | null
  days: number | null
  date: string
  companions: string
  budget_level: string
  tags: string[]
  pace: string
}

export interface DialogSuggestion {
  label: string
  text: string
  city?: string
  days?: string
}

export type DialogStage = 'collecting' | 'confirming' | 'generating' | 'delivered' | 'refused'

export interface DialogResponse {
  session_id: string
  reply: string
  stage: DialogStage
  slots: DialogSlots
  followups_left: number
  suggestions?: DialogSuggestion[] | null
  confirm: boolean
  itinerary?: TravelItinerary | null
  itinerary_id?: string | null
  queued: number
  // Phase 8.1: Refusal / coverage warning fields
  refused?: boolean
  refuse_reason?: string | null
  coverage_warning?: string | null
}

/** Send a message (or slot override) to the conversational planner. */
export async function sendDialogMessage(params: {
  sessionId?: string
  text?: string
  slotOverride?: Partial<DialogSlots>
}): Promise<DialogResponse> {
  const { data } = await api.post<DialogResponse>('/dialog/message', {
    session_id: params.sessionId,
    text: params.text ?? '',
    slot_override: params.slotOverride,
  })
  return data
}

/** Trigger itinerary generation after the user confirms the summary. */
export async function generateDialogPlan(sessionId: string): Promise<DialogResponse> {
  const { data } = await api.post<DialogResponse>(
    '/dialog/generate',
    { session_id: sessionId },
    { timeout: 180000 }
  )
  return data
}


// ── Itinerary History (Phase 6) ───────────────────────────

export interface ItinerarySummary {
  id: string
  title: string
  city: string
  days: number
  created_at: string
}

export interface ItineraryListResponse {
  itineraries: ItinerarySummary[]
  total: number
  page: number
  page_size: number
}

export interface ItineraryDetailResponse {
  id: string
  title: string | null
  days: number
  plan: TravelItinerary
  validation_report: ValidationReport | null
  profile_snapshot: Record<string, unknown> | null
  weather_snapshot: WeatherForecast | null
  created_at: string
  updated_at: string
}

/** List the current user's saved itineraries. */
export async function fetchItineraries(
  page = 1,
  pageSize = 20
): Promise<ItineraryListResponse> {
  const { data } = await api.get<ItineraryListResponse>('/itineraries', {
    params: { page, page_size: pageSize },
  })
  return data
}

/** Get a single itinerary by ID. */
export async function fetchItineraryDetail(id: string): Promise<ItineraryDetailResponse> {
  const { data } = await api.get<ItineraryDetailResponse>(`/itineraries/${id}`)
  return data
}

/** Delete an itinerary. */
export async function deleteItinerary(id: string): Promise<void> {
  await api.delete(`/itineraries/${id}`)
}


// ── Favorites (Phase 6) ──────────────────────────────────

export interface FavoriteItem {
  id: string
  target_type: string
  target_id: string
  created_at: string
}

export interface FavoriteListResponse {
  favorites: FavoriteItem[]
}

/** List the current user's favorites. */
export async function fetchFavorites(
  targetType?: string
): Promise<FavoriteListResponse> {
  const { data } = await api.get<FavoriteListResponse>('/favorites', {
    params: targetType ? { target_type: targetType } : {},
  })
  return data
}

/** Add a favorite (attraction or itinerary). */
export async function addFavorite(
  targetType: string,
  targetId: string
): Promise<{ ok: boolean; favorite?: FavoriteItem }> {
  const { data } = await api.post('/favorites', {
    target_type: targetType,
    target_id: targetId,
  })
  return data
}

/** Remove a favorite. */
export async function removeFavorite(id: string): Promise<void> {
  await api.delete(`/favorites/${id}`)
}


// ── Itinerary Versioning (Phase 8.3) ──────────────────────

export interface VersionSummary {
  id: string
  version_number: number
  change_description: string
  created_at: string
}

export interface VersionListResponse {
  versions: VersionSummary[]
}

/** List all versions for an itinerary, newest first. */
export async function fetchVersions(
  itineraryId: string
): Promise<VersionSummary[]> {
  const { data } = await api.get<VersionListResponse>(
    `/itineraries/${itineraryId}/versions`
  )
  return data.versions
}

/** Restore itinerary to a previous version. */
export async function restoreVersion(
  itineraryId: string,
  versionId: string
): Promise<{ itinerary: TravelItinerary; version: VersionSummary }> {
  const { data } = await api.post<{
    itinerary: TravelItinerary
    version: VersionSummary
  }>(`/itineraries/${itineraryId}/restore/${versionId}`)
  return data
}
