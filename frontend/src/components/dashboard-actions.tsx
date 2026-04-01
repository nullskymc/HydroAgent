'use client'

import { useTransition } from 'react'
import { Button } from '@/components/ui/button'

export function DashboardActions({
  running,
  defaultDuration,
}: {
  running: boolean
  defaultDuration: number
}) {
  const [isPending, startTransition] = useTransition()

  async function mutate(action: 'start' | 'stop') {
    startTransition(async () => {
      await fetch('/api/irrigation/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          duration_minutes: defaultDuration,
        }),
      })

      window.location.reload()
    })
  }

  return (
    <div className="action-row">
      <Button disabled={isPending || running} onClick={() => mutate('start')}>
        {isPending ? '处理中...' : '启动灌溉'}
      </Button>
      <Button variant="secondary" disabled={isPending || !running} onClick={() => mutate('stop')}>
        {isPending ? '处理中...' : '停止灌溉'}
      </Button>
    </div>
  )
}
