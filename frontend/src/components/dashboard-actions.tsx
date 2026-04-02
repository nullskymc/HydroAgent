'use client'

import { useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'

type ActionFeedback = {
  tone: 'default' | 'success' | 'danger'
  message: string
}

export function DashboardActions({
  running,
  defaultDuration,
  disabled = false,
  disabledReason,
}: {
  running: boolean
  defaultDuration: number
  disabled?: boolean
  disabledReason?: string | null
}) {
  const router = useRouter()
  const [isPending, startTransition] = useTransition()
  const [feedback, setFeedback] = useState<ActionFeedback | null>(null)

  function getActionLabel(action: 'start' | 'stop') {
    return action === 'start' ? '启动灌溉' : '停止灌溉'
  }

  function normalizeErrorMessage(error: unknown, action: 'start' | 'stop') {
    if (error instanceof DOMException && error.name === 'AbortError') {
      return `${getActionLabel(action)}请求超时，请检查前后端连接状态后重试。`
    }
    if (error instanceof Error && error.message.trim()) {
      return error.message
    }
    return `${getActionLabel(action)}失败，请稍后重试。`
  }

  async function mutate(action: 'start' | 'stop') {
    startTransition(async () => {
      setFeedback(null)

      const controller = new AbortController()
      const timeoutId = window.setTimeout(() => controller.abort(), 15000)

      try {
        const response = await fetch('/api/irrigation/control', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action,
            duration_minutes: defaultDuration,
          }),
          signal: controller.signal,
        })

        const payload = (await response.json().catch(() => null)) as
          | { detail?: string; message?: string }
          | null

        if (!response.ok) {
          throw new Error(payload?.detail || payload?.message || `${getActionLabel(action)}失败`)
        }

        setFeedback({
          tone: 'success',
          message: payload?.message || `${getActionLabel(action)}已完成。`,
        })
        router.refresh()
      } catch (error) {
        setFeedback({
          tone: 'danger',
          message: normalizeErrorMessage(error, action),
        })
      } finally {
        window.clearTimeout(timeoutId)
      }
    })
  }

  return (
    <div className="console-action-block">
      <div className="action-row console-action-row">
        <Button className="console-action-primary" disabled={disabled || isPending || running} onClick={() => mutate('start')}>
          {isPending ? '处理中...' : '启动灌溉'}
        </Button>
        <Button
          variant="secondary"
          className="console-action-secondary"
          disabled={disabled || isPending || !running}
          onClick={() => mutate('stop')}
        >
          {isPending ? '处理中...' : '停止灌溉'}
        </Button>
      </div>
      {feedback ? (
        <p
          className={feedback.tone === 'danger' ? 'console-action-feedback is-danger' : 'console-action-feedback is-success'}
          role="status"
          aria-live="polite"
        >
          {feedback.message}
        </p>
      ) : null}
      <p className="console-action-hint">{disabledReason || '手动控制不会绕过计划与审批约束。'}</p>
    </div>
  )
}
