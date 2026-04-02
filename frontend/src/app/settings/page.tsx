import { AppShell } from '@/components/app-shell'
import { SettingsForm } from '@/components/settings-form'
import { getSettingsData } from '@/lib/server-data'
import { RuntimeSettings } from '@/lib/types'

const validSections = new Set(['general', 'irrigation', 'alarm', 'context'])

export default async function SettingsPage({
  searchParams,
}: {
  searchParams?: Promise<{ section?: string }>
}) {
  const settings: RuntimeSettings = await getSettingsData().catch(() => ({
    soil_moisture_threshold: 40,
    default_duration_minutes: 30,
    alarm_threshold: 25,
    alarm_enabled: true,
    collection_interval_minutes: undefined,
    sensor_ids: [],
    model_name: undefined,
    db_type: undefined,
    config_source: undefined,
  }))
  const resolvedSearchParams = (await searchParams) || {}
  const initialSection = validSections.has(resolvedSearchParams.section || '')
    ? (resolvedSearchParams.section as 'general' | 'irrigation' | 'alarm' | 'context')
    : 'general'

  return (
    <AppShell currentPath="/settings">
      <div className="page-stack settings-console-page settings-console-page-plain">
        <SettingsForm initialSettings={settings} initialSection={initialSection} />
      </div>
    </AppShell>
  )
}
