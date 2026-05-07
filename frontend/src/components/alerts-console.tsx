'use client'

import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge, StatusDot } from '@/components/ui/badge'
import { EmptyState } from '@/components/ui/empty-state'
import { SectionBadge } from '@/components/ui/section-badge'
import { apiGet, apiSend } from '@/lib/api-client'
import { AlertEvent, UserProfile } from '@/lib/types'
import { labelFor } from '@/lib/labels'
import { cn, formatDateTime } from '@/lib/utils'

const alertGroups = ['open', 'acknowledged', 'resolved'] as const

function severityTone(value?: string | null): 'default' | 'success' | 'warning' | 'danger' {
  if (value === 'high') return 'danger'
  if (value === 'medium') return 'warning'
  if (value === 'low') return 'success'
  return 'default'
}

function statusTone(value?: string | null): 'default' | 'success' | 'warning' | 'danger' {
  if (value === 'open') return 'danger'
  if (value === 'acknowledged') return 'warning'
  if (value === 'resolved') return 'success'
  return 'default'
}

export function AlertsConsole({ initialAlerts, currentUser }: { initialAlerts: AlertEvent[]; currentUser: UserProfile }) {
  const queryClient = useQueryClient()
  const [activeStatus, setActiveStatus] = useState<(typeof alertGroups)[number]>('open')
  const alertsQuery = useQuery({
    queryKey: ['alerts'],
    queryFn: () => apiGet<{ alerts: AlertEvent[] }>('/api/alerts').then((payload) => payload.alerts || []),
    initialData: initialAlerts,
    refetchInterval: 10_000,
  })
  const updateMutation = useMutation({
    mutationFn: ({ alertId, action }: { alertId: string; action: 'acknowledge' | 'resolve' }) =>
      apiSend(`/api/alerts/${alertId}/${action}`, 'POST', { comment: `${currentUser.username} ${action}` }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['alerts'] }),
  })

  const alerts = alertsQuery.data
  const counts = useMemo(
    () => ({
      open: alerts.filter((item) => item.status === 'open').length,
      acknowledged: alerts.filter((item) => item.status === 'acknowledged').length,
      resolved: alerts.filter((item) => item.status === 'resolved').length,
      high: alerts.filter((item) => item.severity === 'high' && item.status !== 'resolved').length,
    }),
    [alerts],
  )
  const activeItems = alerts.filter((item) => item.status === activeStatus)

  return (
    <div className="page-stack">
      <section className={cn('console-telemetry-bar', counts.high > 0 && 'ring-rose-200')}>
        <div className="console-telemetry-title">
          <p className="eyebrow">Alert Center</p>
          <h2>告警处理台</h2>
        </div>
        <div className="console-telemetry-stream">
          {[
            { label: '打开', value: counts.open, tone: counts.open > 0 ? 'danger' : 'success' },
            { label: '已确认', value: counts.acknowledged, tone: counts.acknowledged > 0 ? 'warning' : 'default' },
            { label: '已关闭', value: counts.resolved, tone: 'success' },
            { label: '高风险未关', value: counts.high, tone: counts.high > 0 ? 'danger' : 'success' },
          ].map((item) => (
            <div key={item.label} className="console-telemetry-item">
              <span>{item.label}</span>
              <strong className={item.tone === 'danger' ? 'text-rose-700' : item.tone === 'warning' ? 'text-amber-700' : undefined}>
                {item.value}
              </strong>
            </div>
          ))}
        </div>
        <div className="console-telemetry-meta">
          <span>{alertsQuery.isFetching ? 'Syncing' : 'Risk Monitor'}</span>
          <strong>{counts.high > 0 ? 'Needs action' : 'Stable'}</strong>
        </div>
      </section>

      <section className="surface-panel flex flex-col gap-3">
        <div className="flex flex-col justify-between gap-3 md:flex-row md:items-center">
          <div>
            <SectionBadge label="Alert Queue" />
            <h2 className="m-0 mt-2 text-base font-semibold text-slate-950">告警队列</h2>
          </div>
          <div className="flex flex-wrap gap-2">
            {alertGroups.map((status) => (
              <button
                key={status}
                type="button"
                className={cn(
                  'inline-flex h-8 items-center gap-2 rounded-md px-3 text-sm font-medium transition',
                  activeStatus === status ? 'bg-blue-50 text-[#0052FF]' : 'bg-slate-50 text-slate-600 hover:bg-slate-100',
                )}
                onClick={() => setActiveStatus(status)}
              >
                {labelFor(status)}
                <Badge tone={statusTone(status)}>{counts[status]}</Badge>
              </button>
            ))}
          </div>
        </div>

        {alertsQuery.isLoading && activeItems.length === 0 ? (
          <EmptyState title="正在加载告警" description="正在读取最新告警状态。" />
        ) : activeItems.length === 0 ? (
          <EmptyState
            title={`暂无${labelFor(activeStatus)}告警`}
            description="当前分组没有告警记录。"
            icon={activeStatus === 'resolved' ? CheckCircle2 : AlertTriangle}
          />
        ) : (
          <div className="data-table-shell">
            <table className="min-w-[980px] w-full border-collapse text-sm">
              <thead className="bg-slate-50 text-left font-mono text-[0.64rem] font-semibold tracking-normal text-slate-400">
                <tr>
                  <th className="h-9 border-b border-slate-100 px-3">告警</th>
                  <th className="h-9 border-b border-slate-100 px-3">对象</th>
                  <th className="h-9 border-b border-slate-100 px-3">风险</th>
                  <th className="h-9 border-b border-slate-100 px-3">时间</th>
                  <th className="h-9 border-b border-slate-100 px-3 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {activeItems.map((alert) => {
                  const highOpen = alert.severity === 'high' && alert.status === 'open'
                  return (
                    <tr key={alert.alert_id} className={cn('border-b border-slate-100 last:border-b-0 hover:bg-blue-50/40', highOpen && 'bg-rose-50/70')}>
                      <td className="h-12 px-3">
                        <strong className="block truncate text-sm font-semibold text-slate-950">{alert.title}</strong>
                        <span className="block max-w-xl truncate text-xs text-slate-500">{alert.message}</span>
                      </td>
                      <td className="h-12 px-3 text-xs text-slate-600">
                        {alert.zone_name || alert.sensor_name || alert.actuator_name || alert.object_id || '--'}
                      </td>
                      <td className="h-12 px-3">
                        <div className="flex flex-wrap items-center gap-1.5">
                          <Badge tone={severityTone(alert.severity)}>
                            <StatusDot tone={severityTone(alert.severity)} />
                            {labelFor(alert.severity)}
                          </Badge>
                          <Badge tone={statusTone(alert.status)}>{labelFor(alert.status)}</Badge>
                        </div>
                      </td>
                      <td className="h-12 whitespace-nowrap px-3 text-xs text-slate-500">{formatDateTime(alert.created_at)}</td>
                      <td className="h-12 px-3 text-right">
                        <div className="flex justify-end gap-2">
                          {alert.status === 'open' ? (
                            <Button size="sm" disabled={updateMutation.isPending} onClick={() => updateMutation.mutate({ alertId: alert.alert_id, action: 'acknowledge' })}>
                              确认
                            </Button>
                          ) : null}
                          {alert.status !== 'resolved' ? (
                            <Button size="sm" variant="secondary" disabled={updateMutation.isPending} onClick={() => updateMutation.mutate({ alertId: alert.alert_id, action: 'resolve' })}>
                              关闭
                            </Button>
                          ) : null}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
