/**
 * TravelMind Agent — Skeleton Loading Components
 *
 * Animated placeholder cards shown during data loading.
 * Uses a shimmer sweep (skeleton-shimmer) over soft warm-toned blocks
 * for a finer loading feel than a plain pulse.
 */

/** A single shimmer bar with configurable width. */
function Bar({ className = '' }: { className?: string }) {
  return (
    <div className={`h-4 rounded-md skeleton-shimmer ${className}`} />
  )
}

/** Skeleton placeholder for the itinerary stats overview bar. */
export function SkeletonStats() {
  return (
    <div className="card mb-6 p-5">
      <Bar className="mb-2 w-2/3 h-5" />
      <Bar className="mb-4 w-1/3 h-3" />
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="rounded-xl bg-surface-secondary px-3 py-2 text-center">
            <Bar className="mx-auto mb-1 w-8 h-5" />
            <Bar className="mx-auto w-12 h-3" />
          </div>
        ))}
      </div>
    </div>
  )
}

/** Skeleton placeholder for a single day card. */
export function SkeletonDayCard({ dayNum }: { dayNum: number }) {
  return (
    <div className="card overflow-hidden">
      <div className="flex items-center gap-3 border-b border-border-light px-5 py-4">
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-surface-tertiary">
          <span className="text-sm font-bold text-slate-300">{dayNum}</span>
        </div>
        <div className="flex-1">
          <Bar className="mb-1 w-1/3" />
          <Bar className="w-1/4 h-3" />
        </div>
      </div>
      <div className="px-5 py-4 space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex items-start gap-3 rounded-xl bg-surface-secondary p-3">
            <Bar className="w-12 h-4 shrink-0" />
            <div className="flex flex-col items-center pt-1">
              <div className="h-2.5 w-2.5 rounded-full skeleton-shimmer" />
              {i < 2 && <div className="mt-1 h-10 w-0.5 bg-surface-tertiary" />}
            </div>
            <div className="flex-1">
              <Bar className="mb-1 w-1/2" />
              <Bar className="w-3/4 h-3" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/** Full page itinerary skeleton — shown during streaming generation. */
export function SkeletonItinerary() {
  return (
    <div className="space-y-6 animate-fade-in">
      <SkeletonStats />
      {Array.from({ length: 3 }).map((_, i) => (
        <SkeletonDayCard key={i} dayNum={i + 1} />
      ))}
      {/* Budget skeleton */}
      <div className="card p-5">
        <Bar className="mb-3 w-1/3" />
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="mb-2">
            <div className="flex justify-between mb-1">
              <Bar className="w-12 h-3" />
              <Bar className="w-16 h-3" />
            </div>
            <div className="h-2 rounded-full skeleton-shimmer" />
          </div>
        ))}
      </div>
      {/* Checklist skeleton */}
      <div className="card p-5">
        <Bar className="mb-3 w-1/4" />
        <div className="grid gap-2 sm:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-center gap-2 rounded-xl border border-border px-3 py-2">
              <div className="h-4 w-4 rounded skeleton-shimmer shrink-0" />
              <Bar className="flex-1 h-3" />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

/** Skeleton placeholder for the recommend page (Phase 12.28d). */
export function SkeletonRecommend() {
  return (
    <div className="space-y-4 animate-fade-in">
      <div className="card p-4">
        <div className="flex gap-3">
          <div className="h-11 flex-1 rounded-xl skeleton-shimmer" />
          <div className="h-11 w-24 rounded-xl skeleton-shimmer" />
        </div>
      </div>
      {Array.from({ length: 4 }).map((_, i) => (
        <div key={i} className="card p-4 flex gap-4">
          <div className="h-20 w-20 rounded-xl shrink-0 skeleton-shimmer" />
          <div className="flex-1 space-y-2">
            <Bar className="w-2/3" />
            <Bar className="w-1/2 h-3" />
            <div className="flex gap-2">
              {Array.from({ length: 3 }).map((_, j) => (
                <div key={j} className="h-5 w-14 rounded-full skeleton-shimmer" />
              ))}
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}

/** Skeleton placeholder for the history page (Phase 12.28d). */
export function SkeletonHistory() {
  return (
    <div className="space-y-4 animate-fade-in">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="card p-4">
          <div className="flex items-start justify-between mb-3">
            <div className="space-y-1 flex-1">
              <Bar className="w-1/2" />
              <Bar className="w-1/3 h-3" />
            </div>
            <div className="h-6 w-16 rounded-full skeleton-shimmer" />
          </div>
          <div className="flex gap-2">
            {Array.from({ length: 3 }).map((_, j) => (
              <div key={j} className="h-6 w-20 rounded-md skeleton-shimmer" />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

/** Skeleton placeholder for the image page (Phase 12.28d). */
export function SkeletonImage() {
  return (
    <div className="space-y-6 animate-fade-in">
      <div className="card p-8">
        <div className="flex flex-col items-center gap-3">
          <div className="h-16 w-16 rounded-2xl skeleton-shimmer" />
          <Bar className="w-1/3" />
          <Bar className="w-1/2 h-3" />
        </div>
      </div>
      <div className="grid gap-4 sm:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="card overflow-hidden">
            <div className="h-40 w-full skeleton-shimmer" />
            <div className="p-4 space-y-2">
              <Bar className="w-2/3" />
              <Bar className="w-1/2 h-3" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
