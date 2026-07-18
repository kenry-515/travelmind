interface ExampleQuestionsProps {
  onSelect: (question: string) => void
}

const EXAMPLES = [
  {
    id: 'chongqing-food',
    icon: '🏙️',
    text: '推荐重庆三日游路线，我喜欢美食和历史文化',
  },
  {
    id: 'chengdu-family',
    icon: '👨‍👩‍👧',
    text: '帮我规划成都亲子游，5天4晚，预算中等',
  },
  {
    id: 'photo-spots',
    icon: '📸',
    text: '我想去适合拍照的小众景点，有什么推荐？',
  },
  {
    id: 'guangzhou-weekend',
    icon: '🍜',
    text: '广州出发，周末短途旅行去哪里好？',
  },
]

export function ExampleQuestions({ onSelect }: ExampleQuestionsProps) {
  return (
    <div className="mt-10 w-full max-w-2xl">
      <p className="mb-4 text-center text-sm font-medium text-slate-500">
        试试这些问题
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {EXAMPLES.map((item) => (
          <button
            key={item.id}
            onClick={() => onSelect(item.text)}
            className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-700 shadow-sm transition-all hover:border-blue-300 hover:bg-blue-50 hover:shadow-md"
          >
            <span className="text-xl">{item.icon}</span>
            <span>{item.text}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
