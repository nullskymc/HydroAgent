import { cookies } from 'next/headers'
import {
  AlertEvent,
  AnalyticsOverview,
  AuditEvent,
  DashboardData,
  DecisionLog,
  HistoryData,
  IrrigationPlan,
  KnowledgeDocumentDetail,
  KnowledgeDocumentList,
  RuntimeSettings,
  Role,
  SensorSnapshot,
  SensorDevice,
  SystemStatus,
  UserProfile,
  WeatherData,
  IrrigationState,
  IrrigationLog,
  ConversationSummary,
  Zone,
  ToolTrace,
  Actuator,
} from '@/lib/types'
import { fetchBackendJson } from '@/lib/backend'
import { AUTH_COOKIE_NAME } from '@/lib/auth'

async function getAuthToken() {
  return (await cookies()).get(AUTH_COOKIE_NAME)?.value || null
}

export async function getDashboardData(): Promise<DashboardData> {
  const authToken = await getAuthToken()
  try {
    const [status, sensors, weather, irrigation, decisionsPayload, zonesPayload, plansPayload] = await Promise.all([
      fetchBackendJson<SystemStatus>('/api/status', { authToken }),
      fetchBackendJson<SensorSnapshot>('/api/sensors/current', { authToken }),
      fetchBackendJson<WeatherData>('/api/weather', { authToken }),
      fetchBackendJson<IrrigationState>('/api/irrigation/status', { authToken }),
      fetchBackendJson<{ decisions: DecisionLog[] }>('/api/decisions?limit=5', { authToken }),
      fetchBackendJson<{ zones: Zone[] }>('/api/zones', { authToken }),
      fetchBackendJson<{ plans: IrrigationPlan[] }>('/api/plans?limit=5', { authToken }),
    ])

    return {
      status,
      sensors,
      weather,
      irrigation,
      decisions: decisionsPayload.decisions || [],
      zones: zonesPayload.zones || [],
      plans: plansPayload.plans || [],
      backendReachable: true,
    }
  } catch (error) {
    return {
      status: null,
      sensors: null,
      weather: null,
      irrigation: null,
      decisions: [],
      zones: [],
      plans: [],
      backendReachable: false,
      error: error instanceof Error ? error.message : '后端暂时不可用',
    }
  }
}

export async function getHistoryData(): Promise<HistoryData> {
  const authToken = await getAuthToken()
  const [
    logsPayload,
    decisionsPayload,
    conversationsPayload,
    plansPayload,
    activePlansPayload,
    toolTracesPayload,
    auditsPayload,
  ] = await Promise.all([
    fetchBackendJson<{ logs: IrrigationLog[] }>('/api/irrigation/logs?limit=20', { authToken }),
    fetchBackendJson<{ decisions: DecisionLog[] }>('/api/decisions?limit=20', { authToken }),
    fetchBackendJson<{ conversations: ConversationSummary[] }>('/api/conversations', { authToken }),
    fetchBackendJson<{ plans: IrrigationPlan[] }>('/api/plans?limit=20', { authToken }),
    fetchBackendJson<{ plans: IrrigationPlan[] }>('/api/plans?limit=20&active_only=true', { authToken }),
    fetchBackendJson<{ tool_traces: ToolTrace[] }>('/api/tool-traces?limit=20', { authToken }),
    fetchBackendJson<{ audits: AuditEvent[] }>('/api/audits', { authToken }).catch(() => ({ audits: [] })),
  ])

  return {
    logs: logsPayload.logs || [],
    decisions: decisionsPayload.decisions || [],
    conversations: conversationsPayload.conversations || [],
    plans: plansPayload.plans || [],
    active_plans: activePlansPayload.plans || [],
    tool_traces: toolTracesPayload.tool_traces || [],
    audits: auditsPayload.audits || [],
  }
}

export async function getSettingsData(): Promise<RuntimeSettings> {
  return fetchBackendJson<RuntimeSettings>('/api/settings', { authToken: await getAuthToken() })
}

export async function getKnowledgeDocuments(page = 1, pageSize = 10): Promise<KnowledgeDocumentList> {
  return fetchBackendJson<KnowledgeDocumentList>(`/api/knowledge/documents?page=${page}&page_size=${pageSize}`, {
    authToken: await getAuthToken(),
  })
}

export async function getKnowledgeDocumentDetail(
  documentId: string,
  chunkPage = 1,
  chunkPageSize = 8,
): Promise<KnowledgeDocumentDetail> {
  return fetchBackendJson<KnowledgeDocumentDetail>(
    `/api/knowledge/documents/${documentId}?chunk_page=${chunkPage}&chunk_page_size=${chunkPageSize}`,
    { authToken: await getAuthToken() },
  )
}

export async function getAnalyticsOverview(range = '7d'): Promise<AnalyticsOverview> {
  return fetchBackendJson<AnalyticsOverview>(`/api/analytics/overview?range=${range}`, { authToken: await getAuthToken() })
}

export async function getAlerts(status?: string): Promise<AlertEvent[]> {
  const suffix = status ? `?status=${status}` : ''
  const payload = await fetchBackendJson<{ alerts: AlertEvent[] }>(`/api/alerts${suffix}`, { authToken: await getAuthToken() })
  return payload.alerts || []
}

export async function getAssetData(): Promise<{ zones: Zone[]; sensors: SensorDevice[]; actuators: Actuator[] }> {
  const authToken = await getAuthToken()
  const [zonesPayload, sensorsPayload, actuatorsPayload] = await Promise.all([
    fetchBackendJson<{ zones: Zone[] }>('/api/assets/zones', { authToken }),
    fetchBackendJson<{ sensors: SensorDevice[] }>('/api/assets/sensors', { authToken }),
    fetchBackendJson<{ actuators: Actuator[] }>('/api/assets/actuators', { authToken }),
  ])
  return {
    zones: zonesPayload.zones || [],
    sensors: sensorsPayload.sensors || [],
    actuators: actuatorsPayload.actuators || [],
  }
}

export async function getUserAdminData(): Promise<{ users: UserProfile[]; roles: Role[] }> {
  const authToken = await getAuthToken()
  const [usersPayload, rolesPayload] = await Promise.all([
    fetchBackendJson<{ users: UserProfile[] }>('/api/users', { authToken }),
    fetchBackendJson<{ roles: Role[] }>('/api/roles', { authToken }),
  ])
  return {
    users: usersPayload.users || [],
    roles: rolesPayload.roles || [],
  }
}

export async function getAuditEvents(): Promise<AuditEvent[]> {
  const payload = await fetchBackendJson<{ audits: AuditEvent[] }>('/api/audits', {
    authToken: await getAuthToken(),
  }).catch(() => ({ audits: [] }))
  return payload.audits || []
}
