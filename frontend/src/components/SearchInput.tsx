import { useState, type FormEvent } from 'react'
import { Search } from 'lucide-react'

interface SearchInputProps {
  onSearch: (query: string) => void
  placeholder?: string
}

export function SearchInput({ onSearch, placeholder }: SearchInputProps) {
  const [query, setQuery] = useState('')

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (query.trim()) {
      onSearch(query.trim())
    }
  }

  return (
    <form onSubmit={handleSubmit} className="w-full max-w-2xl">
      <div className="relative flex items-center">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={placeholder || '描述你想要的广州旅行，如：周末带家人游西关...'}
          className="w-full rounded-2xl border border-border bg-white/90 dark:bg-slate-900/90 px-4 py-3.5 pr-14 text-base text-slate-800 dark:text-slate-200 shadow-card transition-all placeholder:text-slate-400 dark:placeholder:text-slate-500 focus:border-brand-400 focus:outline-none focus:ring-4 focus:ring-brand-100 dark:focus:ring-brand-900/40 sm:px-5 sm:py-4 sm:text-lg backdrop-blur"
        />
        <button
          type="submit"
          aria-label="搜索"
          className="btn-primary absolute right-2 rounded-xl p-2.5"
        >
          <Search size={20} />
        </button>
      </div>
    </form>
  )
}
