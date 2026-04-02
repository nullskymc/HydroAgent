import { AppShell } from '@/components/app-shell'
import { ConsoleEmptyState, ConsoleSectionHeader } from '@/components/console-primitives'
import { Badge } from '@/components/ui/badge'
import { getHistoryData } from '@/lib/server-data'
import { formatDateTime } from '@/lib/utils'

type Tone = 'default' | 'success' | 'warning' | 'danger'

function pickSubagent(decisionResult: Record<string, unknown> | null | undefined) {
  return typeof decisionResult?.subagent === 'string' ? decisionResult.subagent : null
}

function getRiskTone(value?: string | null): Tone {
  if (value === 'high') return 'danger'
  if (value === 'medium') return 'warning'
  if (value === 'low') return 'success'
  return 'default'
}

export default async function HistoryPage() {
  const history = await getHistoryData().catch(() => ({
    logs: [],
    decisions: [],
    conversations: [],
    plans: [],
    tool_traces: [],
  }))

  const telemetryItems = [
    { label: '灌溉日志', value: `${history.logs.length}` },
    { label: '决策记录', value: `${history.decisions.length}` },
    { label: '会话数量', value: `${history.conversations.length}` },
    { label: '计划轨迹', value: `${history.plans.length}` },
    { label: '工具链', value: `${history.tool_traces.length}` },
  ]

  return (
    <AppShell currentPath="/history">
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
            <strong>Plan Replay / Supervisor Trace</strong>
          </div>
        </section>

        <div className="console-stage audit-console-stage">
          <div className="console-main">
            <section className="console-section">
              <ConsoleSectionHeader
                eyebrow="执行"
                title="灌溉事件流"
                meta={<span className="console-plain-meta">start / stop / 状态变更</span>}
              />
              <div className="audit-console-list">
                {history.logs.length === 0 ? (
                  <ConsoleEmptyState title="暂无灌溉日志" detail="当前没有执行事件写入审计链路。" />
                ) : null}
                {history.logs.map((log) => (
                  <article key={log.id} className="audit-console-item">
                    <div className="audit-console-item-head">
                      <strong>
                        {log.event} · {log.status}
                      </strong>
                      <time>{formatDateTime(log.created_at)}</time>
                    </div>
                    <p>{log.message || '无附加说明'}</p>
                    <div className="audit-console-meta">
                      <span>分区 {log.zone_id || '--'}</span>
                      <span>计划 {log.plan_id || '无计划编号'}</span>
                      <span>执行器 {log.actuator_id || '--'}</span>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className="console-section">
              <ConsoleSectionHeader
                eyebrow="计划"
                title="计划轨迹"
                meta={<span className="console-plain-meta">审批与执行状态</span>}
              />
              <div className="audit-console-list">
                {history.plans.length === 0 ? (
                  <ConsoleEmptyState title="暂无计划记录" detail="还没有计划被写入审批与执行轨迹。" />
                ) : null}
                {history.plans.map((plan) => (
                  <article key={plan.plan_id} className="audit-console-item">
                    <div className="audit-console-item-head">
                      <div className="audit-console-headline">
                        <strong>{plan.zone_name || plan.zone_id || '--'}</strong>
                        <Badge tone={getRiskTone(plan.risk_level)}>{plan.risk_level}</Badge>
                      </div>
                      <time>{formatDateTime(plan.updated_at || plan.created_at)}</time>
                    </div>
                    <p>{plan.reasoning_summary || plan.plan_id}</p>
                    <div className="audit-console-meta">
                      <span>动作 {plan.proposed_action}</span>
                      <span>审批 {plan.approval_status}</span>
                      <span>执行 {plan.execution_status}</span>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className="console-section">
              <ConsoleSectionHeader
                eyebrow="工具链"
                title="工具链审计"
                meta={<span className="console-plain-meta">trace replay / latest step / duration</span>}
              />
              <div className="audit-console-list">
                {history.tool_traces.length === 0 ? (
                  <ConsoleEmptyState title="暂无工具链轨迹" detail="当前还没有可回放的工具调用链路。" />
                ) : null}
                {history.tool_traces.map((trace) => (
                  <article key={trace.trace_id} className="audit-console-item">
                    <div className="audit-console-item-head audit-console-item-head-top">
                      <div className="console-feed-tags">
                        <Badge tone={trace.status === 'error' ? 'danger' : trace.status === 'running' ? 'warning' : 'success'}>
                          {trace.status}
                        </Badge>
                        <Badge>{trace.tool_count || trace.steps.length} 步</Badge>
                      </div>
                      <time>{formatDateTime(trace.started_at)}</time>
                    </div>
                    <strong>{trace.conversation_title || trace.trace_id}</strong>
                    <p>{trace.latest_step?.detail || '暂无步骤摘要'}</p>
                    <div className="audit-console-meta">
                      <span>会话 {trace.conversation_id || '--'}</span>
                      <span>分区 {trace.zone_id || '--'}</span>
                      <span>计划 {trace.plan_id || '--'}</span>
                      <span>耗时 {trace.duration_ms ? `${trace.duration_ms}ms` : '--'}</span>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </div>

          <aside className="console-sidebar">
            <section className="console-section">
              <ConsoleSectionHeader
                eyebrow="决策"
                title="决策审计"
                meta={<span className="console-plain-meta">subagent / reasoning / reflection</span>}
              />
              <div className="audit-console-list">
                {history.decisions.length === 0 ? (
                  <ConsoleEmptyState title="暂无决策记录" detail="智能体还没有留下新的推理与反思日志。" />
                ) : null}
                {history.decisions.map((decision) => (
                  <article key={decision.decision_id} className="audit-console-item audit-console-item-highlight">
                    <div className="audit-console-item-head audit-console-item-head-top">
                      <div className="console-feed-tags">
                        <Badge>{decision.trigger}</Badge>
                        {pickSubagent(decision.decision_result) ? <Badge>{pickSubagent(decision.decision_result)}</Badge> : null}
                      </div>
                      <time>{formatDateTime(decision.created_at)}</time>
                    </div>
                    <strong>{decision.reasoning_chain || '无推理摘要'}</strong>
                    <p>{decision.reflection_notes || JSON.stringify(decision.decision_result || {})}</p>
                    <div className="audit-console-meta">
                      <span>分区 {decision.zone_id || '--'}</span>
                      <span>计划 {decision.plan_id || '无计划关联'}</span>
                    </div>
                  </article>
                ))}
              </div>
            </section>

            <section className="console-section">
              <ConsoleSectionHeader
                eyebrow="会话"
                title="最近会话"
                meta={<span className="console-plain-meta">审批来源索引</span>}
              />
              <div className="audit-console-list">
                {history.conversations.length === 0 ? (
                  <ConsoleEmptyState title="暂无会话记录" detail="没有可追溯到的对话上下文。" />
                ) : null}
                {history.conversations.map((conversation) => (
                  <article key={conversation.session_id} className="audit-console-item">
                    <div className="audit-console-item-head">
                      <strong>{conversation.title}</strong>
                      <time>{formatDateTime(conversation.updated_at)}</time>
                    </div>
                    <p>{conversation.message_count} 条消息</p>
                    <div className="audit-console-meta">
                      <span>会话 {conversation.session_id}</span>
                      <span>创建于 {formatDateTime(conversation.created_at)}</span>
                    </div>
                  </article>
                ))}
              </div>
            </section>
          </aside>
        </div>
      </div>
    </AppShell>
  )
}
