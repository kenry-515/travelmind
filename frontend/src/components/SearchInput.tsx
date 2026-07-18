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
          placeholder={placeholder || '你想去哪里旅行？输入你的需求...'}
          className="w-full rounded-xl border border-slate-300 bg-white px-5 py-4 pr-12 text-lg text-slate-800 shadow-sm transition-all placeholder:text-slate-400 focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200"
        />
        <button
          type="submit"
          aria-label="搜索"
          className="absolute right-3 rounded-lg p-2 text-slate-400 transition-colors hover:bg-blue-50 hover:text-blue-600"
        >
          <Search size={22} />
        </button>
      </div>
    </form>
  )
}
