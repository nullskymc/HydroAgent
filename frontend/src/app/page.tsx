import { AppShell } from '@/components/app-shell'
import { DashboardConsole } from '@/components/dashboard-console'
import { requirePermission } from '@/lib/auth'
import { getDashboardData, getSettingsData } from '@/lib/server-data'

export default async function DashboardPage() {
  await requirePermission('dashboard:view')
  const [dashboard, settings] = await Promise.all([
    getDashboardData(),
    getSettingsData().catch(() => null),
  ])

  return (
    <AppShell currentPath="/">
      <DashboardConsole initialDashboard={dashboard} initialSettings={settings} />
    </AppShell>
  )
}
