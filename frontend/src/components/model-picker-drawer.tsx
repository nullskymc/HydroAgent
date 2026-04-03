'use client'

import { useEffect, useMemo, useState, useTransition } from 'react'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { OpenAiModelListItem } from '@/lib/types'

type ModelPickerDrawerProps = {
  open: boolean
  title: string
  selectedModel?: string
  onClose: () => void
  onSelect: (modelId: string) => void
}

export function ModelPickerDrawer({
  open,
  title,
  selectedModel,
  onClose,
  onSelect,
}: ModelPickerDrawerProps) {
  const [models, setModels] = useState<OpenAiModelListItem[]>([])
  const [query, setQuery] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [source, setSource] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  useEffect(() => {
    if (!open) {
      return
    }

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
  }, [open])

  const filteredModels = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase()
    if (!normalizedQuery) {
      return models
    }
    return models.filter((item) => item.id.toLowerCase().includes(normalizedQuery))
  }, [models, query])

  if (!open) {
    return null
  }

  return (
    <div className="settings-drawer-backdrop" role="presentation" onClick={onClose}>
      <aside
        className="settings-drawer"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="settings-drawer-header">
          <div className="settings-drawer-copy">
            <p className="eyebrow">模型目录</p>
            <h3>{title}</h3>
            <p>从当前后端配置的 OpenAI 兼容 `/models` 接口读取可用模型。</p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="关闭模型抽屉">
            <X size={16} />
          </Button>
        </header>

        <div className="settings-drawer-toolbar">
          <Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="筛选模型，例如 gpt-4o" />
          <Button variant="secondary" disabled={isPending} onClick={() => setQuery('')}>
            清空筛选
          </Button>
        </div>

        {source ? <p className="settings-drawer-source">{source}</p> : null}
        {error ? <p className="settings-drawer-error">{error}</p> : null}

        <div className="settings-drawer-list">
          {filteredModels.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`settings-drawer-item ${selectedModel === item.id ? 'is-active' : ''}`}
              onClick={() => onSelect(item.id)}
            >
              <div className="settings-drawer-item-copy">
                <strong>{item.id}</strong>
                <span>{item.owned_by || 'openai-compatible'}</span>
              </div>
              {selectedModel === item.id ? <Badge tone="success">已选中</Badge> : <Badge>选择</Badge>}
            </button>
          ))}
          {!isPending && filteredModels.length === 0 ? (
            <div className="settings-drawer-empty">当前没有可选模型。请先确认 endpoint 和 key 配置正确。</div>
          ) : null}
        </div>
      </aside>
    </div>
  )
}
