import { AppShell } from '@/components/app-shell'
import { AlertsConsole } from '@/components/alerts-console'
import { requirePermission } from '@/lib/auth'
import { getAlerts } from '@/lib/server-data'

export default async function AlertsPage() {
  const user = await requirePermission('alerts:view')
  const alerts = await getAlerts()

  return (
    <AppShell currentPath="/alerts">
      <div className="page-stack">
        <AlertsConsole initialAlerts={alerts} currentUser={user} />
      </div>
    </AppShell>
  )
}
