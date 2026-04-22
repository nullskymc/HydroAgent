'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { SectionBadge } from '@/components/ui/section-badge'
import { ReportExportTask, Zone } from '@/lib/types'
import { labelFor } from '@/lib/labels'

function createTask(type: ReportExportTask['type'], downloadUrl: string): ReportExportTask {
  return {
    id: `${type}-${Date.now()}`,
    type,
    status: 'completed',
    downloadUrl,
  }
}

function reportTypeLabel(type: ReportExportTask['type']) {
  if (type === 'operations') return '运营报表'
  if (type === 'audit') return '审计报表'
  return '分区报表'
}

export function ReportsConsole({ zones }: { zones: Zone[] }) {
  const [tasks, setTasks] = useState<ReportExportTask[]>([])

  function appendTask(type: ReportExportTask['type'], downloadUrl: string) {
    setTasks((current) => [createTask(type, downloadUrl), ...current])
    window.open(downloadUrl, '_blank', 'noopener,noreferrer')
  }

  return (
    <div className="admin-grid admin-grid-2">
      <Card>
        <CardContent className="flex flex-col gap-3 p-4">
          <SectionBadge label="Export Center" />
          <div className="admin-list">
            <div className="admin-list-item">
              <strong>运营报表</strong>
              <Button size="sm" onClick={() => appendTask('operations', '/api/reports/operations/export')}>导出 CSV</Button>
            </div>
            <div className="admin-list-item">
              <strong>审计报表</strong>
              <Button size="sm" onClick={() => appendTask('audit', '/api/reports/audit/export')}>导出 CSV</Button>
            </div>
            {zones.length === 0 ? <EmptyState title="暂无分区" description="当前没有可导出的分区报表。" /> : null}
            {zones.map((zone) => (
              <div key={zone.zone_id} className="admin-list-item">
                <strong>{zone.name} 分区报表</strong>
                <Button size="sm" variant="secondary" onClick={() => appendTask('zone', `/api/reports/zones/${zone.zone_id}/export`)}>
                  导出 CSV
                </Button>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="flex flex-col gap-3 p-4">
          <SectionBadge label="Recent Exports" />
          {tasks.length === 0 ? (
            <EmptyState title="暂无导出记录" description="导出任务会在这里显示。" />
          ) : (
            <div className="admin-list">
              {tasks.map((task) => (
                <div key={task.id} className="admin-list-item">
                  <div>
                    <strong>{reportTypeLabel(task.type)}</strong>
                    <Badge className="mt-2">{labelFor(task.status)}</Badge>
                  </div>
                  {task.downloadUrl ? <a className="admin-link" href={task.downloadUrl}>下载</a> : null}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
