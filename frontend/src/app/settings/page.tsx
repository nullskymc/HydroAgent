import { AppShell } from '@/components/app-shell'
import { SettingsForm } from '@/components/settings-form'
import { requirePermission } from '@/lib/auth'
import { getSettingsData } from '@/lib/server-data'
import { RuntimeSettings } from '@/lib/types'

const validSections = new Set(['general', 'knowledge', 'irrigation', 'alarm', 'context', 'skills'])

export default async function SettingsPage({
  searchParams,
}: {
  searchParams?: Promise<{ section?: string }>
}) {
  await requirePermission('settings:view')
  const settings: RuntimeSettings = await getSettingsData().catch(() => ({
    soil_moisture_threshold: 40,
    default_duration_minutes: 30,
    alarm_threshold: 25,
    alarm_enabled: true,
    collection_interval_minutes: undefined,
    model_name: undefined,
    embedding_model_name: undefined,
    openai_base_url: undefined,
    knowledge_top_k: 4,
    knowledge_chunk_size: 1200,
    knowledge_chunk_overlap: 180,
    openai_api_key_status: { configured: false },
    embedding_api_key_status: { configured: false },
    db_type: undefined,
    config_source: undefined,
  }))
  const resolvedSearchParams = (await searchParams) || {}
  const initialSection = validSections.has(resolvedSearchParams.section || '')
    ? (resolvedSearchParams.section as 'general' | 'knowledge' | 'irrigation' | 'alarm' | 'context' | 'skills')
    : 'general'

  return (
    <AppShell currentPath="/settings">
      <div className="page-stack settings-console-page settings-console-page-plain">
        <SettingsForm initialSettings={settings} initialSection={initialSection} />
      </div>
    </AppShell>
  )
}
