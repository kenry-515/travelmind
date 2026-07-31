interface ExampleQuestionsProps {
  onSelect: (question: string) => void
}

const EXAMPLES = [
  {
    id: 'guangzhou-cultural',
    icon: '🏛️',
    text: '广州一日游，想体验西关文化和陈家祠',
  },
  {
    id: 'guangzhou-food',
    icon: '🍵',
    text: '推荐广州早茶文化和地道粤菜餐厅',
  },
  {
    id: 'guangzhou-night',
    icon: '🌃',
    text: '珠江夜游和广州塔夜景攻略',
  },
  {
    id: 'guangzhou-family',
    icon: '👨‍👩‍👧',
    text: '广州亲子两日游，想去长隆',
  },
]

export function ExampleQuestions({ onSelect }: ExampleQuestionsProps) {
  return (
    <div className="mt-4 w-full max-w-2xl">
      <p className="mb-3 text-center text-sm font-medium text-slate-500 dark:text-slate-400">
        试试这些广州旅行问题
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {EXAMPLES.map((item) => (
          <button
            key={item.id}
            onClick={() => onSelect(item.text)}
            className="hover-lift flex items-center gap-3 rounded-2xl border border-border bg-white/80 dark:bg-slate-900/70 px-4 py-3 text-left text-sm text-slate-700 dark:text-slate-300 shadow-card hover:border-brand-300 hover:bg-brand-50/50 dark:hover:bg-brand-900/30 backdrop-blur transition-all"
          >
            <span className="text-xl">{item.icon}</span>
            <span>{item.text}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
