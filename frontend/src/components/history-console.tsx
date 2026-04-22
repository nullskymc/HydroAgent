'use client'

import { useState } from 'react'
import { ConsoleEmptyState, ConsoleSectionHeader } from '@/components/console-primitives'
import { StructuredJsonSectionView } from '@/components/structured-json-view'
import { Badge } from '@/components/ui/badge'
import {
  adminAuditToAuditRecordDetail,
  buildAuditRecordGroups,
  conversationToAuditRecordDetail,
  decisionToAuditRecordDetail,
  irrigationLogToAuditRecordDetail,
  planToAuditRecordDetail,
  toolTraceToAuditRecordDetail,
} from '@/lib/presenters'
import { AuditRecordListItem, HistoryData } from '@/lib/types'
import { cn, formatDateTime } from '@/lib/utils'

type GroupKey = 'plans' | 'tool_traces' | 'logs' | 'decisions' | 'conversations' | 'audits'

const typeLabels: Record<AuditRecordListItem['type'], string> = {
  plan: '计划',
  tool_trace: '工具链',
  log: '执行',
  decision: '决策',
  conversation: '会话',
  audit: '审计',
}

function resolveDefaultSelection(history: HistoryData) {
  if (history.plans[0]) return { group: 'plans' as const, id: history.plans[0].plan_id }
  if (history.tool_traces[0]) return { group: 'tool_traces' as const, id: history.tool_traces[0].trace_id }
  if (history.logs[0]) return { group: 'logs' as const, id: String(history.logs[0].id) }
  if (history.decisions[0]) return { group: 'decisions' as const, id: history.decisions[0].decision_id }
  if (history.conversations[0]) return { group: 'conversations' as const, id: history.conversations[0].session_id }
  if (history.audits?.[0]) return { group: 'audits' as const, id: history.audits[0].audit_id }
  return { group: 'plans' as const, id: '' }
}

function resolveRecordDetail(history: HistoryData, activeGroup: GroupKey, selectedId: string) {
  switch (activeGroup) {
    case 'plans': {
      const selected = history.plans.find((item) => item.plan_id === selectedId) || history.plans[0]
      return selected ? planToAuditRecordDetail(selected) : null
    }
    case 'tool_traces': {
      const selected = history.tool_traces.find((item) => item.trace_id === selectedId) || history.tool_traces[0]
      return selected ? toolTraceToAuditRecordDetail(selected) : null
    }
    case 'logs': {
      const selected = history.logs.find((item) => String(item.id) === selectedId) || history.logs[0]
      return selected ? irrigationLogToAuditRecordDetail(selected) : null
    }
    case 'decisions': {
      const selected = history.decisions.find((item) => item.decision_id === selectedId) || history.decisions[0]
      return selected ? decisionToAuditRecordDetail(selected) : null
    }
    case 'conversations': {
      const selected = history.conversations.find((item) => item.session_id === selectedId) || history.conversations[0]
      return selected ? conversationToAuditRecordDetail(selected) : null
    }
    case 'audits': {
      const selected = history.audits?.find((item) => item.audit_id === selectedId) || history.audits?.[0]
      return selected ? adminAuditToAuditRecordDetail(selected) : null
    }
    default:
      return null
  }
}

function HistoryDataTable({
  items,
  selectedId,
  onSelect,
}: {
  items: AuditRecordListItem[]
  selectedId: string
  onSelect: (id: string) => void
}) {
  if (items.length === 0) {
    return <ConsoleEmptyState title="当前分组暂无记录" detail="切换到其他分组，或等待新的审计记录写入。" />
  }

  return (
    <div className="data-table-shell">
      <table className="min-w-[920px] w-full border-collapse text-sm">
        <thead className="bg-slate-50 text-left font-mono text-[0.64rem] uppercase tracking-widest text-slate-400">
          <tr>
            <th className="h-9 border-b border-slate-100 px-3 font-semibold">时间</th>
            <th className="h-9 border-b border-slate-100 px-3 font-semibold">类型</th>
            <th className="h-9 border-b border-slate-100 px-3 font-semibold">标题 / 摘要</th>
            <th className="h-9 border-b border-slate-100 px-3 font-semibold">状态</th>
            <th className="h-9 border-b border-slate-100 px-3 font-semibold">风险 / 动作</th>
            <th className="h-9 border-b border-slate-100 px-3 font-semibold">关联 ID</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const [statusBadge, secondaryBadge] = item.badges
            const active = item.id === selectedId
            return (
              <tr
                key={item.id}
                className={cn('cursor-pointer border-b border-slate-100 transition last:border-b-0 hover:bg-blue-50/40', active && 'bg-blue-50/70')}
                onClick={() => onSelect(item.id)}
              >
                <td className="h-10 whitespace-nowrap px-3 text-xs text-slate-500">{formatDateTime(item.time)}</td>
                <td className="h-10 whitespace-nowrap px-3">
                  <span className="font-medium text-slate-700">{typeLabels[item.type]}</span>
                </td>
                <td className="h-10 min-w-[280px] px-3">
                  <strong className="line-clamp-1 text-sm font-semibold text-slate-950">{item.title}</strong>
                  <p className="mt-0.5 line-clamp-1 text-xs text-slate-500">{item.summary}</p>
                </td>
                <td className="h-10 whitespace-nowrap px-3">
                  {statusBadge ? <Badge tone={statusBadge.tone}>{statusBadge.label}</Badge> : <span className="text-xs text-slate-400">--</span>}
                </td>
                <td className="h-10 whitespace-nowrap px-3">
                  {secondaryBadge ? <Badge tone={secondaryBadge.tone}>{secondaryBadge.label}</Badge> : <span className="text-xs text-slate-400">--</span>}
                </td>
                <td className="h-10 max-w-[220px] px-3">
                  <span className="block truncate font-mono text-[0.68rem] text-slate-400">{item.meta[0] || item.id}</span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function CompactTimeline({
  items,
  selectedId,
  onSelect,
}: {
  items: AuditRecordListItem[]
  selectedId: string
  onSelect: (id: string) => void
}) {
  if (items.length === 0) {
    return <ConsoleEmptyState title="当前分组暂无记录" detail="切换到其他分组，或等待新的审计记录写入。" />
  }

  return (
    <div className="compact-timeline">
      {items.map((item) => {
        const [statusBadge, secondaryBadge] = item.badges
        const active = item.id === selectedId
        return (
          <button
            key={item.id}
            type="button"
            className={cn('compact-timeline-item', active && 'is-active')}
            onClick={() => onSelect(item.id)}
            aria-pressed={active}
          >
            <span className="compact-timeline-node" aria-hidden="true" />
            <span className="compact-timeline-body">
              <span className="compact-timeline-head">
                <strong>{item.title}</strong>
                <time dateTime={item.time || undefined}>{formatDateTime(item.time)}</time>
              </span>
              <span className="compact-timeline-summary">{item.summary}</span>
              <span className="compact-timeline-meta">
                <span>{typeLabels[item.type]}</span>
                {statusBadge ? <span>{statusBadge.label}</span> : null}
                {secondaryBadge ? <span>{secondaryBadge.label}</span> : null}
                {item.meta[0] ? <span>{item.meta[0]}</span> : null}
              </span>
            </span>
          </button>
        )
      })}
    </div>
  )
}

export function HistoryConsole({ history }: { history: HistoryData }) {
  const defaults = resolveDefaultSelection(history)
  const [activeGroup, setActiveGroup] = useState<GroupKey>(defaults.group)
  const [selectedId, setSelectedId] = useState(defaults.id)

  const groups = buildAuditRecordGroups(history)
  const activeItems = groups.find((group) => group.key === activeGroup)?.items || []
  const resolvedSelectedId = activeItems.some((item) => item.id === selectedId) ? selectedId : (activeItems[0]?.id ?? '')
  const selectedDetail = resolveRecordDetail(history, activeGroup, resolvedSelectedId)

  const telemetryItems = [
    { label: '灌溉日志', value: `${history.logs.length}` },
    { label: '决策记录', value: `${history.decisions.length}` },
    { label: '会话数量', value: `${history.conversations.length}` },
    { label: '计划记录', value: `${history.plans.length}` },
    { label: '工具链', value: `${history.tool_traces.length}` },
    { label: '后台审计', value: `${history.audits?.length || 0}` },
  ]

  const hasAnyRecords = groups.some((group) => group.items.length > 0)

  return (
    <div className="page-stack audit-console-page">
      <section className="console-telemetry-bar audit-console-bar">
        <div className="console-telemetry-title">
          <p className="eyebrow">审计记录</p>
          <h2>灌溉因果链路</h2>
        </div>
        <div className="console-telemetry-stream audit-console-stream">
          {telemetryItems.map((item) => (
            <div key={item.label} className="console-telemetry-item">
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>
        <div className="console-telemetry-meta">
          <span>Audit Trail</span>
          <strong>Table / Structured Detail</strong>
        </div>
      </section>

      {!hasAnyRecords ? (
        <ConsoleEmptyState title="暂无审计记录" detail="当前还没有可浏览的计划、工具链、执行日志或会话记录。" />
      ) : (
        <div className="audit-record-layout">
          <section className="console-section audit-record-nav">
            <ConsoleSectionHeader eyebrow="记录" title="记录表格" meta={<span className="console-plain-meta">高密度浏览</span>} />

            <div className="audit-record-group-tabs">
              {groups.map((group) => (
                <button
                  key={group.key}
                  type="button"
                  className={cn('audit-record-group-tab', group.key === activeGroup && 'is-active')}
                  onClick={() => {
                    setActiveGroup(group.key as GroupKey)
                    setSelectedId(group.items[0]?.id ?? '')
                  }}
                >
                  <span>{group.label}</span>
                  <Badge>{group.items.length}</Badge>
                </button>
              ))}
            </div>

            {activeGroup === 'logs' ? (
              <CompactTimeline items={activeItems} selectedId={resolvedSelectedId} onSelect={setSelectedId} />
            ) : (
              <HistoryDataTable items={activeItems} selectedId={resolvedSelectedId} onSelect={setSelectedId} />
            )}
          </section>

          <section className="console-section audit-record-detail">
            <ConsoleSectionHeader eyebrow="详情" title="结构化详情" meta={<span className="console-plain-meta">业务摘要与技术明细</span>} />

            {selectedDetail ? (
              <div className="audit-detail-panel">
                <header className="audit-detail-head">
                  <div className="audit-detail-title">
                    <h3>{selectedDetail.title}</h3>
                    <p>{selectedDetail.summary}</p>
                  </div>
                  <div className="audit-record-badges">
                    {selectedDetail.badges.map((badge) => (
                      <Badge key={`${selectedDetail.id}-${badge.label}`} tone={badge.tone}>
                        {badge.label}
                      </Badge>
                    ))}
                  </div>
                </header>

                <div className="audit-detail-highlights">
                  {selectedDetail.highlights.map((item) => (
                    <div key={`${selectedDetail.id}-${item.label}`} className="audit-detail-highlight">
                      <span>{item.label}</span>
                      <strong className={item.tone ? `tone-${item.tone}` : ''}>{item.value}</strong>
                    </div>
                  ))}
                </div>

                <div className="audit-detail-meta-grid">
                  {selectedDetail.meta.map((entry) => (
                    <div key={`${selectedDetail.id}-${entry.label}`} className="audit-detail-meta-item">
                      <span>{entry.label}</span>
                      <strong>{entry.value}</strong>
                    </div>
                  ))}
                </div>

                <div className="audit-detail-sections">
                  {selectedDetail.sections.length === 0 ? (
                    <div className="audit-detail-empty">当前记录没有额外结构化详情。</div>
                  ) : (
                    selectedDetail.sections.map((section) => (
                      <StructuredJsonSectionView key={`${selectedDetail.id}-${section.title}`} section={section} />
                    ))
                  )}
                </div>
              </div>
            ) : (
              <ConsoleEmptyState title="暂无详情" detail="请从左侧选择一条记录查看完整信息。" />
            )}
          </section>
        </div>
      )}
    </div>
  )
}
