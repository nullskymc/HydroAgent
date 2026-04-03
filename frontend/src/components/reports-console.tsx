'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { ReportExportTask, Zone } from '@/lib/types'

function createTask(type: ReportExportTask['type'], downloadUrl: string): ReportExportTask {
  return {
    id: `${type}-${Date.now()}`,
    type,
    status: 'completed',
    downloadUrl,
  }
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
        <CardHeader><CardTitle>导出中心</CardTitle></CardHeader>
        <CardContent className="admin-list">
          <div className="admin-list-item">
            <strong>运营报表</strong>
            <Button size="sm" onClick={() => appendTask('operations', '/api/reports/operations/export')}>导出 CSV</Button>
          </div>
          <div className="admin-list-item">
            <strong>审计报表</strong>
            <Button size="sm" onClick={() => appendTask('audit', '/api/reports/audit/export')}>导出 CSV</Button>
          </div>
          {zones.map((zone) => (
            <div key={zone.zone_id} className="admin-list-item">
              <strong>{zone.name} 分区报表</strong>
              <Button size="sm" variant="secondary" onClick={() => appendTask('zone', `/api/reports/zones/${zone.zone_id}/export`)}>
                导出 CSV
              </Button>
            </div>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>最近任务</CardTitle></CardHeader>
        <CardContent className="admin-list">
          {tasks.length === 0 ? <div className="admin-list-item">暂无导出记录</div> : null}
          {tasks.map((task) => (
            <div key={task.id} className="admin-list-item">
              <div>
                <strong>{task.type}</strong>
                <p>{task.status}</p>
              </div>
              {task.downloadUrl ? <a className="admin-link" href={task.downloadUrl}>下载</a> : null}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
