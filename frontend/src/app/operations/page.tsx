import { AppShell } from '@/components/app-shell'
import { OperationsConsole } from '@/components/operations-console'
import { requirePermission } from '@/lib/auth'
import { getDashboardData, getHistoryData } from '@/lib/server-data'

export default async function OperationsPage() {
  const user = await requirePermission('operations:view')
  const [history, dashboard] = await Promise.all([getHistoryData(), getDashboardData()])

  return (
    <AppShell currentPath="/operations">
      <OperationsConsole initialHistory={history} initialDashboard={dashboard} currentUser={user} />
    </AppShell>
  )
}
