import { AppShell } from '@/components/app-shell'
import { HistoryConsole } from '@/components/history-console'
import { requirePermission } from '@/lib/auth'
import { getHistoryData } from '@/lib/server-data'

export default async function HistoryPage() {
  await requirePermission('history:view')
  const history = await getHistoryData().catch(() => ({
    logs: [],
    decisions: [],
    conversations: [],
    plans: [],
    tool_traces: [],
    audits: [],
  }))

  return (
    <AppShell currentPath="/history">
      <HistoryConsole history={history} />
    </AppShell>
  )
}
