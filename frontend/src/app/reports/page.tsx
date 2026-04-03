import { AppShell } from '@/components/app-shell'
import { ReportsConsole } from '@/components/reports-console'
import { requirePermission } from '@/lib/auth'
import { getAssetData } from '@/lib/server-data'

export default async function ReportsPage() {
  await requirePermission('reports:view')
  const assets = await getAssetData()

  return (
    <AppShell currentPath="/reports">
      <div className="page-stack">
        <ReportsConsole zones={assets.zones} />
      </div>
    </AppShell>
  )
}
