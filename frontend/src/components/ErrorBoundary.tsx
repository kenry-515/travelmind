import { Component, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw, Home } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

/**
 * React Error Boundary — catches rendering errors anywhere in the tree
 * and shows a helpful fallback UI with retry and navigation options.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    console.error('TravelMind UI Error:', error, info.componentStack)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center bg-slate-50 dark:bg-slate-800 px-4 text-center">
          <div className="w-full max-w-md rounded-2xl bg-white dark:bg-slate-900 p-6 shadow-lg sm:p-8">
            <AlertTriangle size={48} className="mx-auto mb-4 text-red-400" />
            <h2 className="mb-2 text-xl font-bold text-slate-800 dark:text-slate-200 sm:text-2xl">
              页面出错了
            </h2>
            <p className="mb-4 text-sm text-slate-500 dark:text-slate-400 sm:text-base">
              应用遇到了一个意外错误。请尝试刷新页面。
            </p>
            {this.state.error?.message && (
              <p className="mb-6 rounded-lg bg-slate-50 dark:bg-slate-800 px-3 py-2 text-xs text-slate-400 dark:text-slate-500 break-all font-mono">
                {this.state.error.message}
              </p>
            )}
            <div className="flex items-center justify-center gap-3">
              <a
                href="/"
                className="inline-flex items-center gap-1.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 px-4 py-2.5 text-sm font-medium text-slate-600 dark:text-slate-400 transition-colors hover:bg-slate-50 dark:hover:bg-slate-800"
              >
                <Home size={16} />
                返回首页
              </a>
              <button
                onClick={() => window.location.reload()}
                className="btn-primary inline-flex items-center gap-1.5 px-4 py-2.5 text-sm"
              >
                <RefreshCw size={16} />
                刷新页面
              </button>
            </div>
          </div>
        </div>
      )
    }

    return this.props.children
  }
}
