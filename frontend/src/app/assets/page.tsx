import { AppShell } from '@/components/app-shell'
import { AssetsConsole } from '@/components/assets-console'
import { requirePermission } from '@/lib/auth'
import { getAssetData } from '@/lib/server-data'

export default async function AssetsPage() {
  const user = await requirePermission('assets:view')
  const assets = await getAssetData()

  return (
    <AppShell currentPath="/assets">
      <div className="page-stack">
        <AssetsConsole
          initialZones={assets.zones}
          initialSensors={assets.sensors}
          initialActuators={assets.actuators}
          currentUser={user}
        />
      </div>
    </AppShell>
  )
}
