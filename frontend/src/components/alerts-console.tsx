'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { AlertEvent, UserProfile } from '@/lib/types'
import { formatDateTime } from '@/lib/utils'

export function AlertsConsole({ initialAlerts, currentUser }: { initialAlerts: AlertEvent[]; currentUser: UserProfile }) {
  const [alerts, setAlerts] = useState(initialAlerts)

  async function updateAlert(alertId: string, action: 'acknowledge' | 'resolve') {
    const response = await fetch(`/api/alerts/${alertId}/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ comment: `${currentUser.username} ${action}` }),
    })
    if (!response.ok) {
      return
    }
    const payload = await response.json()
    setAlerts((current) => current.map((item) => (item.alert_id === alertId ? payload.alert : item)))
  }

  return (
    <div className="admin-grid">
      {['open', 'acknowledged', 'resolved'].map((status) => (
        <Card key={status}>
          <CardHeader>
            <CardTitle>{status === 'open' ? '打开' : status === 'acknowledged' ? '已确认' : '已解决'} 告警</CardTitle>
          </CardHeader>
          <CardContent className="admin-list">
            {alerts.filter((item) => item.status === status).map((alert) => (
              <div key={alert.alert_id} className="admin-list-item">
                <div>
                  <strong>{alert.title}</strong>
                  <p>{alert.message}</p>
                  <span>{alert.zone_name || alert.object_id} · {formatDateTime(alert.created_at)}</span>
                </div>
                <div className="admin-action-row">
                  {status === 'open' ? <Button size="sm" onClick={() => updateAlert(alert.alert_id, 'acknowledge')}>确认</Button> : null}
                  {status !== 'resolved' ? <Button size="sm" variant="secondary" onClick={() => updateAlert(alert.alert_id, 'resolve')}>关闭</Button> : null}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}
