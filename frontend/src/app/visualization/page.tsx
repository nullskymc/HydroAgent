import { AppShell } from '@/components/app-shell'
import { VisualizationConsole } from '@/components/visualization-console'
import { requirePermission } from '@/lib/auth'
import { getAnalyticsOverview, getDashboardData, getHistoryData } from '@/lib/server-data'

export default async function VisualizationPage() {
  await requirePermission('dashboard:view')
  const [dashboard, overview, history] = await Promise.all([
    getDashboardData(),
    getAnalyticsOverview('7d').catch(() => null),
    getHistoryData().catch(() => ({
      logs: [],
      decisions: [],
      conversations: [],
      plans: [],
      tool_traces: [],
      audits: [],
    })),
  ])

  return (
    <AppShell currentPath="/visualization">
      <VisualizationConsole dashboard={dashboard} overview={overview} history={history} />
    </AppShell>
  )
}
