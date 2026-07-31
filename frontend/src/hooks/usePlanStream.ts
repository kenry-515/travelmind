/**
 * TravelMind Agent — usePlanStream Hook
 *
 * SSE streaming hook for the multi-agent pipeline.
 * Extracted from ItineraryPage so the component stays focused on rendering.
 *
 * Usage:
 *   const { state, start } = usePlanStream()
 *   // call start(userInput) to begin; state tracks loading → ready → error
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import { getDeviceId } from '../lib/deviceId'
import type { TravelItinerary, PlanResponse } from '../lib/api'

export interface ProgressStep {
  step: string
  label: string
  status: 'pending' | 'running' | 'done'
}

export interface LoadingState {
  stage: 'loading'
  message: string
  progress: ProgressStep[]
}

export interface ReadyState {
  stage: 'ready'
  itinerary: TravelItinerary
  weather: null  // fetched separately by the page
  error: string | null
  preview: boolean
  itineraryId: string | null  // DB id when auto-saved by backend
}

export interface ErrorState {
  stage: 'error'
  message: string
}

export type StreamState = LoadingState | ReadyState | ErrorState

/** Labels for each pipeline step — shown in the progress stepper. */
const STEP_LABELS: Record<string, string> = {
  profile_extraction: '提取用户画像',
  trend_analysis: '分析热门趋势',
  weather_fetch: '获取天气数据',
  rag_retrieval: '检索知识库',
  recommendation: '评分和排序',
  planning: '生成行程规划',
}

function initialProgress(): ProgressStep[] {
  return Object.entries(STEP_LABELS).map(([step, label]) => ({
    step,
    label,
    status: 'pending' as const,
  }))
}

export function usePlanStream() {
  const [state, setState] = useState<StreamState | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const taskIdRef = useRef<string | null>(null)

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort()
    }
  }, [])

  /**
   * Fallback: Poll the backend for task status when SSE stream is lost.
   * @param taskId The task ID to poll for.
   * @param signal AbortSignal to cancel polling.
   */
  const pollForResult = useCallback(async (taskId: string, signal: AbortSignal) => {
    const MAX_POLLS = 20 // 20 * 2s = 40s max polling time
    const POLL_INTERVAL = 2000 // 2 seconds

    for (let i = 0; i < MAX_POLLS; i++) {
      if (signal.aborted) return

      try {
        const res = await fetch(`/api/v1/agent/plan/status/${taskId}`, {
          signal,
          headers: { 'X-Device-ID': getDeviceId() }
        })
        if (!res.ok) throw new Error(`Polling failed: ${res.status}`)
        
        const data = await res.json()
        
        if (data.status === 'completed' && data.data) {
          const planData = data.data as PlanResponse
          if (planData.itinerary?.days?.length) {
            setState({
              stage: 'ready',
              itinerary: planData.itinerary,
              weather: null,
              error: planData.error,
              preview: false,
              itineraryId: planData.itinerary_id || null,
            })
            return
          }
        } else if (data.status === 'error') {
          setState({ stage: 'error', message: data.data?.message || '行程生成失败。' })
          return
        } else if (data.status === 'not_found') {
          // Task not found, might be too early or expired
          // Continue polling
        }
      } catch (e) {
        // Ignore individual polling errors, continue until max retries
        console.warn('Polling attempt failed:', e)
      }

      // Wait for next poll
      await new Promise(resolve => setTimeout(resolve, POLL_INTERVAL))
    }

    // If we exhaust polling attempts
    setState({ stage: 'error', message: '行程规划超时，请稍后重试。' })
  }, [])

  const start = useCallback(async (userInput: string) => {
    const progress = initialProgress()
    taskIdRef.current = null // Reset task ID
    setState({ stage: 'loading', message: '正在启动...', progress })

    const controller = new AbortController()
    abortRef.current = controller
    const timeoutId = setTimeout(() => controller.abort(), 120000)
    
    let streamFinished = false

    try {
      const response = await fetch('/api/v1/agent/plan/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Device-ID': getDeviceId(),
        },
        body: JSON.stringify({ user_input: userInput }),
        signal: controller.signal,
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) throw new Error('Response body not readable')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) {
          streamFinished = true
          break
        }

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          try {
            const event = JSON.parse(line.slice(6))

            // Capture task_id from the first progress event
            if (event.event === 'progress' && event.task_id && !taskIdRef.current) {
              taskIdRef.current = event.task_id
            }

            if (event.event === 'progress') {
              const stepIdx = progress.findIndex((p) => p.step === event.step)
              if (stepIdx !== -1) {
                // Mark previous steps as done, current as running/done
                for (let i = 0; i < stepIdx; i++) {
                  progress[i] = { ...progress[i], status: 'done' }
                }
                progress[stepIdx] = {
                  ...progress[stepIdx],
                  status: event.status === 'done' ? 'done' : 'running',
                }
              }
              setState((prev) =>
                prev?.stage === 'loading'
                  ? { ...prev, message: event.message || prev.message, progress: [...progress] }
                  : prev
              )
            } else if (event.event === 'result') {
              streamFinished = true
              const data = event.data as PlanResponse
              if (!data.itinerary?.days?.length) {
                setState({
                  stage: 'error',
                  message: data.error || '行程生成失败，请稍后重试。',
                })
                return
              }
              setState({
                stage: 'ready',
                itinerary: data.itinerary,
                weather: null,
                error: data.error,
                preview: false,
                itineraryId: data.itinerary_id || null,
              })
              return
            } else if (event.event === 'saved') {
              // Backend auto-saved the itinerary — capture the DB id
              setState((prev) =>
                prev?.stage === 'ready'
                  ? { ...prev, itineraryId: event.itinerary_id || prev.itineraryId }
                  : prev
              )
            } else if (event.event === 'error') {
              streamFinished = true
              setState({ stage: 'error', message: event.message })
              return
            }
          } catch {
            // skip unparseable lines
          }
        }
      }

      // Stream ended without a result event
      if (!streamFinished) {
        // Check if we have a task_id for fallback
        if (taskIdRef.current) {
          // Wait briefly before polling to allow backend to process
          await new Promise(resolve => setTimeout(resolve, 2000))
          await pollForResult(taskIdRef.current, controller.signal)
        } else {
          setState({ stage: 'error', message: '行程规划连接中断，请重试。' })
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        clearTimeout(timeoutId)
        return
      }
      
      // If we have a task_id and got an error, try polling
      if (taskIdRef.current) {
        await pollForResult(taskIdRef.current, controller.signal)
      } else {
        setState({
          stage: 'error',
          message:
            err instanceof Error ? err.message : '行程规划服务暂不可用，请稍后重试。',
        })
      }
    } finally {
      clearTimeout(timeoutId)
      abortRef.current = null
      taskIdRef.current = null // Reset for next request
    }
  }, [pollForResult])

  return { state, start, setState }
}
