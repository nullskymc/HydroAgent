'use client'

import { useMemo, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { AlertEvent, IrrigationLog, IrrigationPlan, UserProfile } from '@/lib/types'
import { formatDateTime } from '@/lib/utils'

export function OperationsConsole({
  plans,
  logs,
  alerts,
  currentUser,
}: {
  plans: IrrigationPlan[]
  logs: IrrigationLog[]
  alerts: AlertEvent[]
  currentUser: UserProfile
}) {
  const [pendingPlans, setPendingPlans] = useState(plans)
  const actionablePlans = useMemo(
    () => pendingPlans.filter((plan) => ['pending_approval', 'approved'].includes(plan.status)),
    [pendingPlans],
  )

  async function submitPlanAction(planId: string, action: 'approve' | 'reject' | 'execute') {
    const response = await fetch(`/api/plans/${planId}/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ actor: currentUser.username }),
    })
    if (!response.ok) {
      return
    }
    const payload = await response.json()
    setPendingPlans((current) => current.map((item) => (item.plan_id === planId ? payload.plan : item)))
  }

  return (
    <div className="admin-grid admin-grid-3">
      <Card>
        <CardHeader>
          <CardTitle>待审批计划</CardTitle>
        </CardHeader>
        <CardContent className="admin-list">
          {actionablePlans.map((plan) => (
            <div key={plan.plan_id} className="admin-list-item">
              <div>
                <strong>{plan.zone_name || plan.zone_id}</strong>
                <p>{plan.reasoning_summary}</p>
                <span>{plan.status} / {plan.execution_status}</span>
              </div>
              <div className="admin-action-row">
                {currentUser.permissions.includes('plans:approve') ? (
                  <>
                    <Button size="sm" onClick={() => submitPlanAction(plan.plan_id, 'approve')}>批准</Button>
                    <Button size="sm" variant="danger" onClick={() => submitPlanAction(plan.plan_id, 'reject')}>拒绝</Button>
                  </>
                ) : null}
                {currentUser.permissions.includes('plans:execute') ? (
                  <Button size="sm" variant="secondary" onClick={() => submitPlanAction(plan.plan_id, 'execute')}>执行</Button>
                ) : null}
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>最近执行</CardTitle>
        </CardHeader>
        <CardContent className="admin-list">
          {logs.map((log) => (
            <div key={log.id} className="admin-list-item">
              <div>
                <strong>{log.event}</strong>
                <p>{log.message || '无附加说明'}</p>
              </div>
              <span>{formatDateTime(log.created_at)}</span>
            </div>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>未处理告警</CardTitle>
        </CardHeader>
        <CardContent className="admin-list">
          {alerts.filter((item) => item.status !== 'resolved').map((alert) => (
            <div key={alert.alert_id} className="admin-list-item">
              <div>
                <strong>{alert.title}</strong>
                <p>{alert.message}</p>
              </div>
              <span>{alert.status}</span>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
