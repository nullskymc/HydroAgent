'use client'

import { useEffect, useMemo, useState, useTransition } from 'react'
import { motion } from 'framer-motion'
import { Check, Search, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { OpenAiModelListItem } from '@/lib/types'
import { cn } from '@/lib/utils'

type ModelPickerDrawerProps = {
  open: boolean
  title: string
  selectedModel?: string
  onClose: () => void
  onSelect: (modelId: string) => void
}

const MODEL_DESCRIPTIONS: Array<{ pattern: RegExp; description: string }> = [
  { pattern: /gpt-4|gpt4|o3|o4/i, description: 'High reasoning capacity' },
  { pattern: /gpt-5|gpt5/i, description: 'Frontier reasoning and tool use' },
  { pattern: /embedding|text-embedding/i, description: 'Semantic retrieval and knowledge indexing' },
  { pattern: /llama|mistral|qwen|gemma|deepseek/i, description: 'Run completely locally or on your own endpoint' },
  { pattern: /mini|small|nano/i, description: 'Fast response with lower operating cost' },
]

function formatModelName(modelId: string) {
  return modelId
    .replace(/^openai[_:-]/i, 'OpenAI ')
    .replace(/^azure[_:-]/i, 'Azure ')
    .replace(/^local[_:-]/i, 'Local ')
    .replace(/[_-]+/g, ' ')
    .replace(/\b(gpt|llm|api|ml)\b/gi, (value) => value.toUpperCase())
    .replace(/\bo(\d)\b/gi, 'o$1')
    .replace(/\b\w/g, (value) => value.toUpperCase())
}

function describeModel(model: OpenAiModelListItem) {
  const matched = MODEL_DESCRIPTIONS.find((item) => item.pattern.test(model.id))
  if (matched) return matched.description
  if (model.owned_by && /local|ollama|lmstudio/i.test(model.owned_by)) return 'Run completely locally'
  if (model.owned_by) return `${model.owned_by} compatible model`
  return 'OpenAI-compatible model endpoint'
}

function isRecommendedModel(modelId: string, selectedModel?: string) {
  if (selectedModel === modelId) return true
  return /gpt-4o|gpt-4\.1|gpt-5|o3/i.test(modelId)
}

function ModelOptionCard({
  model,
  active,
  recommended,
  onSelect,
}: {
  model: OpenAiModelListItem
  active: boolean
  recommended: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      className={cn(
        'relative cursor-pointer rounded-xl border border-slate-200 bg-white p-4 text-left transition-all hover:border-blue-300 hover:bg-slate-50',
        active && 'border-2 border-[#0052FF] bg-blue-50/50',
      )}
      onClick={onSelect}
      aria-pressed={active}
    >
      {recommended ? (
        <span className="absolute right-3 top-3 rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-[#0052FF]">
          Recommended
        </span>
      ) : null}
      <div className="flex min-w-0 items-start gap-3 pr-24">
        <span
          className={cn(
            'mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white text-white transition-colors',
            active && 'border-[#0052FF] bg-[#0052FF]',
          )}
          aria-hidden="true"
        >
          {active ? <Check className="size-3.5" /> : null}
        </span>
        <span className="min-w-0">
          <span className="block truncate text-sm font-medium text-slate-900">{formatModelName(model.id)}</span>
          <span className="mt-1 block text-xs leading-5 text-slate-500">{describeModel(model)}</span>
          <span className="mt-2 block truncate font-mono text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            {model.id}
          </span>
        </span>
      </div>
    </button>
  )
}

export function ModelPickerDrawer({
  open,
  title,
  selectedModel,
  onClose,
  onSelect,
}: ModelPickerDrawerProps) {
  if (!open) {
    return null
  }

  return <ModelPickerDialog title={title} selectedModel={selectedModel} onClose={onClose} onSelect={onSelect} />
}

function ModelPickerDialog({
  title,
  selectedModel,
  onClose,
  onSelect,
}: Omit<ModelPickerDrawerProps, 'open'>) {
  const [models, setModels] = useState<OpenAiModelListItem[]>([])
  const [draftModel, setDraftModel] = useState(selectedModel || '')
  const [query, setQuery] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [source, setSource] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  useEffect(() => {
    startTransition(async () => {
      setError(null)
      try {
        const response = await fetch('/api/settings/openai-models', { cache: 'no-store' })
        const payload = (await response.json().catch(() => null)) as
          | { detail?: unknown; source?: string; models?: OpenAiModelListItem[] }
          | null

        if (!response.ok) {
          const detail = typeof payload?.detail === 'string' ? payload.detail : JSON.stringify(payload?.detail || '读取模型列表失败')
          setError(detail)
          return
        }

        setModels(payload?.models || [])
        setSource(payload?.source || null)
      } catch (requestError) {
        setError(requestError instanceof Error ? requestError.message : '读取模型列表失败')
      }
    })
  }, [])

  const filteredModels = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    if (!normalizedQuery) {
      return models
    }
    return models.filter((item) => {
      const searchableText = `${item.id} ${formatModelName(item.id)} ${item.owned_by || ''}`.toLowerCase()
      return searchableText.includes(normalizedQuery)
    })
  }, [models, query])

  function confirmSelection() {
    if (!draftModel) return
    onSelect(draftModel)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/20 p-4 backdrop-blur-sm" role="presentation" onClick={onClose}>
      <motion.aside
        className="w-full max-w-md rounded-lg border border-slate-100 bg-white shadow-lg"
        role="dialog"
        aria-modal="true"
        aria-label="Select ML Model"
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.14, ease: 'easeOut' }}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-4 border-b border-slate-100 px-5 pb-4 pt-5">
          <div className="min-w-0">
            <h3 className="m-0 text-lg font-semibold text-slate-900">Select ML Model</h3>
            <p className="mt-1 text-xs leading-5 text-slate-500">{title || 'Choose the runtime model for HydroAgent.'}</p>
          </div>
          <button
            type="button"
            className="rounded-md p-1 text-slate-400 transition-colors hover:bg-slate-100 hover:text-slate-700"
            onClick={onClose}
            aria-label="Close model selection"
          >
            <X className="size-4" />
          </button>
        </header>

        <div className="space-y-4 px-5 py-4">
          <label className="flex h-9 items-center gap-2 rounded-lg bg-slate-50 px-3 ring-1 ring-slate-100 transition focus-within:bg-white focus-within:ring-2 focus-within:ring-[#0052FF]/20">
            <Search className="size-4 shrink-0 text-slate-400" aria-hidden="true" />
            <Input
              className="h-full border-0 bg-transparent px-0 shadow-none focus-visible:ring-0"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Filter models, e.g. gpt-4o"
            />
          </label>

          {source ? <p className="m-0 truncate font-mono text-[10px] font-semibold uppercase tracking-wider text-slate-400">{source}</p> : null}
          {error ? <p className="m-0 rounded-lg border border-rose-100 bg-rose-50 px-3 py-2 text-xs leading-5 text-rose-700">{error}</p> : null}

          <div className="flex max-h-[22rem] flex-col gap-3 overflow-y-auto pr-1">
            {filteredModels.map((item) => (
              <ModelOptionCard
                key={item.id}
                model={item}
                active={draftModel === item.id}
                recommended={isRecommendedModel(item.id, selectedModel)}
                onSelect={() => setDraftModel(item.id)}
              />
            ))}
            {isPending ? <div className="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-500">Loading models...</div> : null}
            {!isPending && filteredModels.length === 0 ? (
              <div className="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-500">当前没有可选模型。请先确认 endpoint 和 key 配置正确。</div>
            ) : null}
          </div>
        </div>

        <footer className="flex justify-end gap-3 border-t border-slate-100 px-5 py-4">
          <button
            type="button"
            className="h-9 rounded-lg bg-white px-4 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100"
            onClick={onClose}
          >
            Cancel
          </button>
          <Button
            className="h-9 rounded-md bg-[#0052FF] px-6 text-sm font-medium text-white shadow-sm shadow-blue-500/10 transition-colors hover:bg-[#0047DB]"
            disabled={!draftModel}
            onClick={confirmSelection}
          >
            Confirm
          </Button>
        </footer>
      </motion.aside>
    </div>
  )
}
