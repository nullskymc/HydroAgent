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
import { HistoryData } from '@/lib/types'
import { formatDateTime } from '@/lib/utils'

type GroupKey = 'plans' | 'tool_traces' | 'logs' | 'decisions' | 'conversations' | 'audits'

function resolveDefaultSelection(history: HistoryData) {
  if (history.plans[0]) return { group: 'plans' as const, id: history.plans[0].plan_id }
  if (history.tool_traces[0]) return { group: 'tool_traces' as const, id: history.tool_traces[0].trace_id }
  if (history.logs[0]) return { group: 'logs' as const, id: String(history.logs[0].id) }
  if (history.decisions[0]) return { group: 'decisions' as const, id: history.decisions[0].decision_id }
  if (history.conversations[0]) return { group: 'conversations' as const, id: history.conversations[0].session_id }
  if (history.audits?.[0]) return { group: 'audits' as const, id: history.audits[0].audit_id }
  return { group: 'plans' as const, id: '' }
}

export function HistoryConsole({ history }: { history: HistoryData }) {
  const defaults = resolveDefaultSelection(history)
  const [activeGroup, setActiveGroup] = useState<GroupKey>(defaults.group)
  const [selectedId, setSelectedId] = useState(defaults.id)

  const groups = buildAuditRecordGroups(history)
  const activeItems = groups.find((group) => group.key === activeGroup)?.items || []
  const resolvedSelectedId = activeItems.some((item) => item.id === selectedId) ? selectedId : (activeItems[0]?.id ?? '')

  const telemetryItems = [
    { label: '灌溉日志', value: `${history.logs.length}` },
    { label: '决策记录', value: `${history.decisions.length}` },
    { label: '会话数量', value: `${history.conversations.length}` },
    { label: '计划记录', value: `${history.plans.length}` },
    { label: '工具链', value: `${history.tool_traces.length}` },
    { label: '后台审计', value: `${history.audits?.length || 0}` },
  ]

  const selectedDetail =
    activeGroup === 'plans'
      ? (() => {
          const selected = history.plans.find((item) => item.plan_id === resolvedSelectedId) || history.plans[0]
          return selected ? planToAuditRecordDetail(selected) : null
        })()
      : activeGroup === 'tool_traces'
        ? (() => {
            const selected = history.tool_traces.find((item) => item.trace_id === resolvedSelectedId) || history.tool_traces[0]
            return selected ? toolTraceToAuditRecordDetail(selected) : null
          })()
        : activeGroup === 'logs'
          ? (() => {
              const selected = history.logs.find((item) => String(item.id) === resolvedSelectedId) || history.logs[0]
              return selected ? irrigationLogToAuditRecordDetail(selected) : null
            })()
          : activeGroup === 'decisions'
            ? (() => {
                const selected = history.decisions.find((item) => item.decision_id === resolvedSelectedId) || history.decisions[0]
                return selected ? decisionToAuditRecordDetail(selected) : null
              })()
            : activeGroup === 'conversations'
              ? (() => {
                const selected = history.conversations.find((item) => item.session_id === resolvedSelectedId) || history.conversations[0]
                return selected ? conversationToAuditRecordDetail(selected) : null
              })()
              : (() => {
                  const selected = history.audits?.find((item) => item.audit_id === resolvedSelectedId) || history.audits?.[0]
                  return selected ? adminAuditToAuditRecordDetail(selected) : null
                })()

  const hasAnyRecords =
    history.plans.length > 0 ||
    history.tool_traces.length > 0 ||
    history.logs.length > 0 ||
    history.decisions.length > 0 ||
    history.conversations.length > 0 ||
    Boolean(history.audits?.length)

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
          <strong>Record Explorer / Structured Detail</strong>
        </div>
      </section>

      {!hasAnyRecords ? (
        <ConsoleEmptyState title="暂无审计记录" detail="当前还没有可浏览的计划、工具链、执行日志或会话记录。" />
      ) : (
        <div className="audit-record-layout">
          <section className="console-section audit-record-nav">
            <ConsoleSectionHeader
              eyebrow="记录"
              title="记录浏览"
              meta={<span className="console-plain-meta">列表与筛选</span>}
            />

            <div className="audit-record-group-tabs">
              {groups.map((group) => (
                <button
                  key={group.key}
                  type="button"
                  className={`audit-record-group-tab ${group.key === activeGroup ? 'is-active' : ''}`}
                  onClick={() => setActiveGroup(group.key as GroupKey)}
                >
                  <span>{group.label}</span>
                  <Badge>{group.items.length}</Badge>
                </button>
              ))}
            </div>

            <div className="audit-record-list">
              {activeItems.length === 0 ? (
                <ConsoleEmptyState title="当前分组暂无记录" detail="切换到其他分组，或等待新的审计记录写入。" />
              ) : (
                activeItems.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    className={`audit-record-item ${item.id === resolvedSelectedId ? 'is-active' : ''}`}
                    onClick={() => setSelectedId(item.id)}
                  >
                    <div className="audit-record-item-head">
                      <strong>{item.title}</strong>
                      <time>{formatDateTime(item.time)}</time>
                    </div>
                    <p>{item.summary}</p>
                    <div className="audit-record-badges">
                      {item.badges.map((badge) => (
                        <Badge key={`${item.id}-${badge.label}`} tone={badge.tone}>
                          {badge.label}
                        </Badge>
                      ))}
                    </div>
                    <div className="audit-record-meta">
                      {item.meta.map((entry) => (
                        <span key={`${item.id}-${entry}`}>{entry}</span>
                      ))}
                    </div>
                  </button>
                ))
              )}
            </div>
          </section>

          <section className="console-section audit-record-detail">
            <ConsoleSectionHeader
              eyebrow="详情"
              title="结构化详情"
              meta={<span className="console-plain-meta">业务摘要与技术明细</span>}
            />

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
