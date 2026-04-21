'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { SectionBadge } from '@/components/ui/section-badge'
import { apiGet, apiSend } from '@/lib/api-client'
import { AlertEvent, UserProfile } from '@/lib/types'
import { labelFor } from '@/lib/labels'
import { formatDateTime } from '@/lib/utils'

const alertGroups = ['open', 'acknowledged', 'resolved'] as const

export function AlertsConsole({ initialAlerts, currentUser }: { initialAlerts: AlertEvent[]; currentUser: UserProfile }) {
  const queryClient = useQueryClient()
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

  return (
    <div className="admin-grid">
      {alertGroups.map((status) => {
        const items = (alertsQuery.data || []).filter((item) => item.status === status)
        return (
          <Card key={status}>
            <CardContent className="flex flex-col gap-3 p-4">
              <div className="flex items-center justify-between gap-3">
                <SectionBadge label={`${labelFor(status)} Alerts`} />
                <Badge>{items.length}</Badge>
              </div>
              {alertsQuery.isLoading && items.length === 0 ? (
                <EmptyState title="正在加载告警" description="正在读取最新告警状态。" />
              ) : items.length === 0 ? (
                <EmptyState title={`暂无${labelFor(status)}告警`} description="当前分组没有告警记录。" />
              ) : (
                <div className="admin-list">
                  {items.map((alert) => (
                    <div key={alert.alert_id} className="admin-list-item">
                      <div>
                        <strong>{alert.title}</strong>
                        <p>{alert.message}</p>
                        <span>{alert.zone_name || alert.object_id || '--'} · {formatDateTime(alert.created_at)}</span>
                      </div>
                      <div className="admin-action-row">
                        <Badge tone={alert.severity === 'high' ? 'danger' : alert.severity === 'medium' ? 'warning' : 'success'}>
                          {labelFor(alert.severity)}
                        </Badge>
                        {status === 'open' ? <Button size="sm" disabled={updateMutation.isPending} onClick={() => updateMutation.mutate({ alertId: alert.alert_id, action: 'acknowledge' })}>确认</Button> : null}
                        {status !== 'resolved' ? <Button size="sm" variant="secondary" disabled={updateMutation.isPending} onClick={() => updateMutation.mutate({ alertId: alert.alert_id, action: 'resolve' })}>关闭</Button> : null}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
