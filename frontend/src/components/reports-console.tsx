'use client'

import { useState } from 'react'
import { Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge, StatusDot } from '@/components/ui/badge'
import { EmptyState } from '@/components/ui/empty-state'
import { SectionBadge } from '@/components/ui/section-badge'
import { ReportExportTask, Zone } from '@/lib/types'
import { labelFor } from '@/lib/labels'
import { formatDateTime } from '@/lib/utils'

type ExportItem = {
  id: string
  label: string
  description: string
  type: ReportExportTask['type']
  downloadUrl: string
}

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

function taskCreatedAt(taskId: string) {
  const segments = taskId.split('-')
  const timestamp = Number(segments[segments.length - 1])
  if (!Number.isFinite(timestamp)) return null
  return new Date(timestamp).toISOString()
}

export function ReportsConsole({ zones }: { zones: Zone[] }) {
  const [tasks, setTasks] = useState<ReportExportTask[]>([])
  const exportItems: ExportItem[] = [
    {
      id: 'operations',
      label: '运营报表',
      description: '导出计划、执行、分区运行相关运营数据。',
      type: 'operations',
      downloadUrl: '/api/reports/operations/export',
    },
    {
      id: 'audit',
      label: '审计报表',
      description: '导出审批、工具链、用户操作相关审计数据。',
      type: 'audit',
      downloadUrl: '/api/reports/audit/export',
    },
    ...zones.map((zone) => ({
      id: zone.zone_id,
      label: `${zone.name} 分区报表`,
      description: `${zone.location} · ${zone.crop_type || '未配置作物'}`,
      type: 'zone' as const,
      downloadUrl: `/api/reports/zones/${zone.zone_id}/export`,
    })),
  ]

  function appendTask(type: ReportExportTask['type'], downloadUrl: string) {
    setTasks((current) => [createTask(type, downloadUrl), ...current])
    window.open(downloadUrl, '_blank', 'noopener,noreferrer')
  }

  return (
    <div className="page-stack">
      <section className="console-telemetry-bar">
        <div className="console-telemetry-title">
          <p className="eyebrow">Export Center</p>
          <h2>报表导出中心</h2>
        </div>
        <div className="console-telemetry-stream">
          {[
            { label: '固定报表', value: 2 },
            { label: '分区报表', value: zones.length },
            { label: '本次导出', value: tasks.length },
            { label: '完成任务', value: tasks.filter((item) => item.status === 'completed').length },
          ].map((item) => (
            <div key={item.label} className="console-telemetry-item">
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>
        <div className="console-telemetry-meta">
          <span>CSV</span>
          <strong>Audit / Operations / Zone</strong>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(360px,0.75fr)]">
        <section className="surface-panel flex min-w-0 flex-col gap-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <SectionBadge label="Available Exports" />
              <h2 className="m-0 mt-2 text-base font-semibold text-slate-950">可导出报表</h2>
            </div>
            <Badge>{exportItems.length} 项</Badge>
          </div>

          {exportItems.length === 2 && zones.length === 0 ? (
            <div className="rounded-md bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-700">当前没有可导出的分区报表，仍可导出运营与审计报表。</div>
          ) : null}

          <div className="data-table-shell">
            <table className="min-w-[760px] w-full border-collapse text-sm">
              <thead className="bg-slate-50 text-left font-mono text-[0.64rem] font-semibold tracking-normal text-slate-400">
                <tr>
                  <th className="h-9 border-b border-slate-100 px-3">报表</th>
                  <th className="h-9 border-b border-slate-100 px-3">类型</th>
                  <th className="h-9 border-b border-slate-100 px-3">格式</th>
                  <th className="h-9 border-b border-slate-100 px-3 text-right">操作</th>
                </tr>
              </thead>
              <tbody>
                {exportItems.map((item) => (
                  <tr key={item.id} className="border-b border-slate-100 last:border-b-0 hover:bg-blue-50/40">
                    <td className="h-12 px-3">
                      <strong className="block truncate text-sm font-semibold text-slate-950">{item.label}</strong>
                      <span className="block truncate text-xs text-slate-500">{item.description}</span>
                    </td>
                    <td className="h-12 px-3">
                      <Badge>{reportTypeLabel(item.type)}</Badge>
                    </td>
                    <td className="h-12 px-3 text-xs text-slate-500">CSV</td>
                    <td className="h-12 px-3 text-right">
                      <Button size="sm" variant={item.type === 'zone' ? 'secondary' : 'primary'} onClick={() => appendTask(item.type, item.downloadUrl)}>
                        <Download className="size-4" aria-hidden="true" />
                        导出
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="surface-panel flex min-w-0 flex-col gap-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <SectionBadge label="Recent Exports" />
              <h2 className="m-0 mt-2 text-base font-semibold text-slate-950">最近导出</h2>
            </div>
            <Badge>{tasks.length} 条</Badge>
          </div>
          {tasks.length === 0 ? (
            <EmptyState title="暂无导出记录" description="导出任务会在这里显示。" icon={Download} />
          ) : (
            <div className="flex flex-col gap-2">
              {tasks.map((task) => (
                <div key={task.id} className="surface-row flex items-center justify-between gap-3 rounded-md">
                  <div className="min-w-0">
                    <strong className="block truncate text-sm font-semibold text-slate-950">{reportTypeLabel(task.type)}</strong>
                    <span className="block text-xs text-slate-500">{formatDateTime(taskCreatedAt(task.id))}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={task.status === 'completed' ? 'success' : 'default'}>
                      <StatusDot tone={task.status === 'completed' ? 'success' : 'default'} />
                      {labelFor(task.status)}
                    </Badge>
                    {task.downloadUrl ? <a className="admin-link" href={task.downloadUrl}>下载</a> : null}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  )
}
