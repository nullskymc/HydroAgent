import { AppShell } from '@/components/app-shell'
import { PageHeader } from '@/components/ui/page-header'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getHistoryData } from '@/lib/server-data'
import { formatDateTime } from '@/lib/utils'

export default async function HistoryPage() {
  const history = await getHistoryData().catch(() => ({
    logs: [],
    decisions: [],
    conversations: [],
  }))

  return (
    <AppShell currentPath="/history">
      <div className="page-stack">
        <PageHeader
          eyebrow="历史审计"
          title="历史审计"
          description="集中查看运行日志、决策链路与最近会话，便于快速追溯系统行为。"
          meta={['Audit Trail', 'Logs']}
          compact
        />

        <div className="history-grid">
          <Card className="table-shell">
            <CardHeader><CardTitle>灌溉日志</CardTitle></CardHeader>
            <CardContent className="table-card">
            {history.logs.length === 0 ? <p className="inline-muted">暂无灌溉日志</p> : null}
            {history.logs.map((log) => (
              <div key={log.id} className="table-row">
                <strong>{log.event} · {log.status}</strong>
                <p>{log.message || '无附加说明'}</p>
                <time>{formatDateTime(log.created_at)}</time>
              </div>
            ))}
            </CardContent>
          </Card>

          <Card className="table-shell">
            <CardHeader><CardTitle>决策审计</CardTitle></CardHeader>
            <CardContent className="table-card">
            {history.decisions.length === 0 ? <p className="inline-muted">暂无决策记录</p> : null}
            {history.decisions.map((decision) => (
              <div key={decision.decision_id} className="table-row">
                <strong>{decision.trigger}</strong>
                <p>{decision.reasoning_chain || JSON.stringify(decision.decision_result || {})}</p>
                <time>{formatDateTime(decision.created_at)}</time>
              </div>
            ))}
            </CardContent>
          </Card>

          <Card className="table-shell">
            <CardHeader><CardTitle>最近会话</CardTitle></CardHeader>
            <CardContent className="table-card">
            {history.conversations.length === 0 ? <p className="inline-muted">暂无会话记录</p> : null}
            {history.conversations.map((conversation) => (
              <div key={conversation.session_id} className="table-row">
                <strong>{conversation.title}</strong>
                <p>{conversation.message_count} 条消息</p>
                <time>{formatDateTime(conversation.updated_at)}</time>
              </div>
            ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  )
}
