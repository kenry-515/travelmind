/**
 * TravelMind Agent — IntentBar (意图状态条)
 *
 * 常驻对话页顶部，实时显示已识别槽位；点击任意槽位内联编辑，
 * 变更即时通过 slot_override 同步到后端状态机。
 */

import { useState } from 'react'
import { Pencil } from 'lucide-react'
import type { DialogSlots } from '../lib/api'

interface IntentBarProps {
  slots: DialogSlots
  onSlotChange: (override: Partial<DialogSlots>) => void
  disabled?: boolean
}

interface ChipDef {
  key: keyof DialogSlots
  label: string
  format: (v: unknown) => string
  editable: boolean
  inputType: 'text' | 'number'
}

const CHIP_DEFS: ChipDef[] = [
  { key: 'city', label: '目的地', format: (v) => (v ? String(v) : '未定'), editable: true, inputType: 'text' },
  { key: 'days', label: '天数', format: (v) => (v ? `${v} 天` : '未定'), editable: true, inputType: 'number' },
  { key: 'companions', label: '同行', format: (v) => String(v || '不限'), editable: true, inputType: 'text' },
  { key: 'tags', label: '偏好', format: (v) => (Array.isArray(v) && v.length ? (v as string[]).join('/') : '不限'), editable: true, inputType: 'text' },
  { key: 'budget_level', label: '预算', format: (v) => String(v || '舒适'), editable: true, inputType: 'text' },
  { key: 'pace', label: '节奏', format: (v) => String(v || '休闲'), editable: true, inputType: 'text' },
]

export function IntentBar({ slots, onSlotChange, disabled }: IntentBarProps) {
  const [editing, setEditing] = useState<ChipDef | null>(null)
  const [draft, setDraft] = useState('')

  const openEditor = (chip: ChipDef) => {
    if (disabled || !chip.editable) return
    const raw = slots[chip.key]
    setDraft(Array.isArray(raw) ? raw.join('、') : raw == null ? '' : String(raw))
    setEditing(chip)
  }

  const submit = () => {
    if (!editing) return
    const value = draft.trim()
    let override: Partial<DialogSlots> = {}
    if (editing.key === 'days') {
      const n = parseInt(value, 10)
      if (!Number.isNaN(n) && n >= 1 && n <= 14) override = { days: n }
    } else if (editing.key === 'tags') {
      override = { tags: value ? value.split(/[、,，\s]+/).filter(Boolean) : [] }
    } else if (editing.key === 'city') {
      override = { city: value || null }
    } else {
      override = { [editing.key]: value } as Partial<DialogSlots>
    }
    if (Object.keys(override).length > 0) onSlotChange(override)
    setEditing(null)
  }

  return (
    <div className="glass border-b border-border-light px-4 py-2">
      <div className="mx-auto flex max-w-3xl flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-slate-400">意图</span>
        {CHIP_DEFS.map((chip) => {
          const value = chip.format(slots[chip.key])
          const isEmpty = value === '未定'
          return (
            <button
              key={chip.key}
              onClick={() => openEditor(chip)}
              disabled={disabled}
              className={`group flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs transition-all ${
                isEmpty
                  ? 'border-dashed border-slate-300 text-slate-400 hover:border-brand-300 hover:text-brand-600'
                  : 'border-border bg-surface-secondary text-slate-700 hover:border-brand-300 hover:bg-brand-50 hover:text-brand-700'
              }`}
              title={`点击修改${chip.label}`}
            >
              <span className="text-slate-400">{chip.label}</span>
              <span className="font-medium">{value}</span>
              <Pencil size={10} className="opacity-0 transition-opacity group-hover:opacity-50" />
            </button>
          )
        })}
      </div>

      {/* Inline editor */}
      {editing && (
        <div className="mx-auto mt-2 flex max-w-3xl items-center gap-2">
          <input
            type={editing.inputType}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            placeholder={`输入${editing.label}${editing.key === 'tags' ? '（顿号分隔）' : ''}`}
            className="w-56 rounded-xl border border-border px-2.5 py-1.5 text-xs focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
            autoFocus
          />
          <button
            onClick={submit}
            className="btn-primary rounded-xl px-3 py-1.5 text-xs"
          >
            确定
          </button>
          <button
            onClick={() => setEditing(null)}
            className="rounded-lg px-2 py-1.5 text-xs text-slate-400 hover:text-slate-600"
          >
            取消
          </button>
        </div>
      )}
    </div>
  )
}
