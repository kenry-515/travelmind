/**
 * TravelMind Agent — ImageUploader
 *
 * Drag-and-drop / click-to-select image upload with client-side validation
 * (format + size, mirroring the backend limits) and a local preview.
 */

import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from 'react'
import { ImagePlus, Loader2, X } from 'lucide-react'
import { toast } from './Toast'

// 与后端 /image/analyze 的限制保持一致
const ACCEPTED_TYPES = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']
const MAX_SIZE = 10 * 1024 * 1024 // 10 MB

interface ImageUploaderProps {
  onAnalyze: (file: File) => void
  loading: boolean
}

export function ImageUploader({ onAnalyze, loading }: ImageUploaderProps) {
  const [file, setFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  // preview URL 的生命周期统一由这个 effect 管理，避免内存泄漏
  useEffect(() => {
    if (!file) {
      setPreviewUrl(null)
      return
    }
    const url = URL.createObjectURL(file)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const selectFile = (candidate: File | null | undefined) => {
    if (!candidate) return
    if (!ACCEPTED_TYPES.includes(candidate.type)) {
      toast.error('仅支持 png / jpeg / webp / gif 格式的图片')
      return
    }
    if (candidate.size > MAX_SIZE) {
      toast.error('图片过大，请选择 10MB 以内的图片')
      return
    }
    setFile(candidate)
  }

  const clearFile = () => {
    setFile(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    selectFile(e.target.files?.[0])
  }

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragOver(false)
    if (loading) return
    selectFile(e.dataTransfer.files?.[0])
  }

  const formatSize = (bytes: number) =>
    bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`

  return (
    <div className="w-full">
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_TYPES.join(',')}
        onChange={handleInputChange}
        className="sr-only"
        aria-label="选择图片"
      />

      {!previewUrl ? (
        <div
          onClick={() => !loading && inputRef.current?.click()}
          onDragOver={(e) => {
            e.preventDefault()
            setDragOver(true)
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
          className={`flex h-56 w-full cursor-pointer flex-col items-center justify-center gap-3 rounded-3xl border-2 border-dashed transition-all ${
            dragOver
              ? 'border-brand-400 bg-brand-50 scale-[1.01]'
              : 'border-slate-300 bg-white hover:border-brand-300 hover:bg-brand-50/40'
          }`}
        >
          <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-gradient-to-br from-brand-100 to-accent-100">
            <ImagePlus size={32} className="text-brand-500" />
          </div>
          <p className="text-sm font-medium text-slate-600">
            拖拽图片到这里，或点击选择
          </p>
          <p className="text-xs text-slate-400">
            支持 png / jpeg / webp / gif，不超过 10MB
          </p>
        </div>
      ) : (
        <div className="card overflow-hidden rounded-2xl">
          <div className="relative flex items-center justify-center bg-surface-tertiary p-4">
            <img
              src={previewUrl}
              alt="待分析图片预览"
              className="max-h-72 rounded-lg object-contain"
            />
            <button
              onClick={clearFile}
              disabled={loading}
              className="absolute right-3 top-3 rounded-full bg-white/90 p-1.5 text-slate-500 shadow transition-colors hover:text-slate-800 disabled:opacity-50"
              aria-label="移除图片"
            >
              <X size={16} />
            </button>
          </div>
          <div className="flex items-center justify-between gap-3 px-4 py-3">
            <div className="min-w-0 text-sm text-slate-500">
              <p className="truncate font-medium text-slate-700">{file?.name}</p>
              <p className="text-xs">{file && formatSize(file.size)}</p>
            </div>
            <button
              onClick={() => file && onAnalyze(file)}
              disabled={loading || !file}
              className="btn-primary flex shrink-0 items-center gap-2 rounded-xl px-5 py-2.5 text-sm"
            >
              {loading && <Loader2 size={16} className="animate-spin" />}
              {loading ? '识别中...' : '开始识别'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
