import { AppShell } from '@/components/app-shell'
import { SettingsForm } from '@/components/settings-form'
import { PageHeader } from '@/components/ui/page-header'
import { getSettingsData } from '@/lib/server-data'

export default async function SettingsPage() {
  const settings = await getSettingsData().catch(() => ({
    soil_moisture_threshold: 40,
    default_duration_minutes: 30,
    alarm_threshold: 25,
    alarm_enabled: true,
  }))

  return (
    <AppShell currentPath="/settings">
      <div className="page-stack">
        <PageHeader
          eyebrow="系统设置"
          title="系统设置"
          description="管理阈值、默认灌溉时长和运行元数据，所有配置都会立即影响前台工作台。"
          meta={['Runtime', 'Metadata']}
          compact
        />
        <SettingsForm initialSettings={settings} />
      </div>
    </AppShell>
  )
}
