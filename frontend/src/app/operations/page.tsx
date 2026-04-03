import { AppShell } from '@/components/app-shell'
import { OperationsConsole } from '@/components/operations-console'
import { requirePermission } from '@/lib/auth'
import { getAlerts, getHistoryData } from '@/lib/server-data'

export default async function OperationsPage() {
  const user = await requirePermission('operations:view')
  const [history, alerts] = await Promise.all([getHistoryData(), getAlerts()])

  return (
    <AppShell currentPath="/operations">
      <div className="page-stack">
        <OperationsConsole plans={history.plans} logs={history.logs} alerts={alerts} currentUser={user} />
      </div>
    </AppShell>
  )
}
