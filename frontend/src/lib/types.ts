export type SystemStatus = {
  status: string
  timestamp: string
  agent_initialized: boolean
  irrigation_status: string
  version: string
  features: string[]
}

export type UiTone = 'default' | 'success' | 'warning' | 'danger'

export type SensorAverage = {
  soil_moisture: number
  temperature: number
  light_intensity: number
  rainfall: number
}

export type SensorSnapshot = {
  timestamp: string
  sensors: Array<Record<string, unknown>>
  average: SensorAverage
}

export type WeatherData = {
  city: string
  live: {
    weather: string
    temperature: string
    wind_direction: string
    wind_power: string
  }
  forecast: Array<{
    date: string
    day_weather: string
    day_temp: string
    night_temp: string
  }>
  note?: string
}

export type IrrigationState = {
  status: string
  start_time: string | null
  duration_minutes: number
  elapsed_minutes?: number
  remaining_minutes?: number
}

export type IrrigationLog = {
  id: number
  event: string
  zone_id?: string | null
  actuator_id?: string | null
  plan_id?: string | null
  status: string
  start_time: string | null
  end_time: string | null
  duration_planned: number | null
  message: string | null
  created_at: string | null
}

export type DecisionLog = {
  decision_id: string
  trigger: string
  zone_id?: string | null
  plan_id?: string | null
  trace_id?: string | null
  source?: 'chat_agent' | 'service_layer' | null
  skill_ids?: string[] | null
  input_context: Record<string, unknown> | null
  reasoning_chain: string | null
  tools_used: string[] | null
  decision_result: Record<string, unknown> | null
  evidence_refs?: Record<string, unknown> | null
  reflection_notes: string | null
  effectiveness_score: number | null
  created_at: string | null
}

export type WorkingMemory = {
  last_inferred_mode?: ChatMode
  active_skills?: string[]
  active_zone_ids?: string[]
  latest_plan_ids?: string[]
  latest_pending_plan_ids?: string[]
  latest_approved_plan_ids?: string[]
  open_risks?: string[]
  last_user_goal?: string
  last_decision_summary?: string
  last_sensor_anomalies?: Array<Record<string, unknown>>
  skill_reason?: string
  last_updated_at?: string | null
}

export type SkillCatalogItem = {
  id: string
  name: string
  description: string
  trigger_hints?: string[]
  mode_allowlist?: ChatMode[]
  tool_allowlist?: string[]
  resources?: string[]
  workflow?: Record<string, string>
  workflow_phases?: Array<'evidence' | 'analysis' | 'planning' | 'approval' | 'execution' | 'audit'>
  source_type?: 'local' | 'imported' | 'generated'
  source_url?: string | null
  managed_by?: string | null
  wrapper_kind?: string | null
  tool_bundle?: string[]
  installed_at?: string | null
  updated_at?: string | null
  instruction_append?: string
  source_path?: string | null
}

export type ImportSkillRequest = {
  url: string
  overwrite?: boolean
}

export type ImportSkillResponse = {
  skill: SkillCatalogItem
  import_result: 'installed' | 'updated'
}

export type ConversationSummary = {
  session_id: string
  title: string
  message_count: number
  created_at: string | null
  updated_at: string | null
}

export type ToolTraceStep = {
  step_index: number
  event_type: string
  status: string
  tool_name?: string | null
  subagent_name?: string | null
  title: string
  detail: string
  input_preview?: string | null
  output_preview?: string | null
  zone_id?: string | null
  plan_id?: string | null
  created_at?: string | null
  duration_ms?: number | null
  agent_name?: string | null
  node_name?: string | null
  phase?: 'evidence' | 'analysis' | 'planning' | 'approval' | 'execution' | 'audit' | null
  active_skills?: string[] | null
  layer?: 'supervisor' | 'subagent' | 'tool' | 'legacy' | null
  tone?: 'default' | 'success' | 'warning' | 'danger' | null
}

export type ToolTrace = {
  trace_id: string
  conversation_id?: string | null
  conversation_title?: string | null
  status: string
  steps: ToolTraceStep[]
  started_at?: string | null
  ended_at?: string | null
  duration_ms?: number | null
  tool_count?: number
  latest_step?: ToolTraceStep | null
  zone_id?: string | null
  plan_id?: string | null
}

export type ChatMessage = {
  id?: number
  role: 'user' | 'assistant' | 'tool'
  content: string | null
  plan?: IrrigationPlan | null
  suggestion?: IrrigationSuggestion | null
  trace_id?: string | null
  tool_calls?: string[] | null
  tool_name?: string | null
  tool_call_id?: string | null
  tool_trace?: ToolTrace | null
  created_at?: string | null
}

export type ConversationDetail = {
  conversation: ConversationSummary
  messages: ChatMessage[]
  working_memory?: WorkingMemory | null
}

export type ChatMode = 'advisor' | 'planner' | 'operator' | 'auditor'

export type RuntimeSettings = {
  soil_moisture_threshold: number
  default_duration_minutes: number
  alarm_threshold: number
  alarm_enabled: boolean
  model_name?: string
  embedding_model_name?: string
  openai_base_url?: string | null
  knowledge_top_k?: number
  knowledge_chunk_size?: number
  knowledge_chunk_overlap?: number
  openai_api_key_status?: SecretStatus
  embedding_api_key_status?: SecretStatus
  collection_interval_minutes?: number
  db_type?: string
  config_source?: string
  yaml_settings?: {
    model_name?: string
    embedding_model_name?: string
    openai_base_url?: string | null
    openai_api_key_status?: SecretStatus
    embedding_api_key_status?: SecretStatus
    db_type?: string
    config_source?: string
  }
  business_settings?: {
    default_soil_moisture_threshold?: number
    default_duration_minutes?: number
    alarm_threshold?: number
    alarm_enabled?: boolean
    collection_interval_minutes?: number
    knowledge_top_k?: number
    knowledge_chunk_size?: number
    knowledge_chunk_overlap?: number
  }
}

export type SecretStatus = {
  configured: boolean
  masked_value?: string | null
}

export type OpenAiModelListItem = {
  id: string
  owned_by?: string | null
  created?: number | null
}

export type Pagination = {
  page: number
  page_size: number
  total: number
  total_pages: number
  has_prev: boolean
  has_next: boolean
}

export type KnowledgeDocumentSummary = {
  document_id: string
  title: string
  source_uri?: string | null
  status: string
  chunk_count: number
  checksum: string
  metadata?: Record<string, unknown> | null
  created_by?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type KnowledgeChunk = {
  chunk_id: string
  document_id: string
  chunk_index: number
  content: string
  metadata?: Record<string, unknown> | null
  created_at?: string | null
  updated_at?: string | null
}

export type KnowledgeDocumentDetail = {
  document: KnowledgeDocumentSummary & {
    preview?: string | null
  }
  chunks: KnowledgeChunk[]
  pagination: Pagination
}

export type KnowledgeDocumentList = {
  documents: KnowledgeDocumentSummary[]
  pagination: Pagination
}

export type Permission = {
  permission_key: string
  name: string
  description?: string | null
  category?: string | null
}

export type Role = {
  role_key: string
  name: string
  description?: string | null
  is_system?: boolean
  permissions: string[]
}

export type UserProfile = {
  id: number
  username: string
  email?: string | null
  display_name?: string | null
  phone?: string | null
  is_active: boolean
  is_admin: boolean
  created_by?: string | null
  last_login?: string | null
  password_changed_at?: string | null
  roles: string[]
  permissions: string[]
}

export type Actuator = {
  actuator_id: string
  zone_id: string
  name: string
  actuator_type: string
  status: string
  capabilities?: Record<string, unknown>
  is_enabled: boolean
  last_command_at?: string | null
  serial_number?: string | null
  firmware_version?: string | null
  health_status?: string | null
  last_seen_at?: string | null
}

export type SensorDevice = {
  sensor_device_id: string
  sensor_id: string
  name: string
  model?: string | null
  location?: string | null
  status: string
  is_enabled: boolean
  last_seen_at?: string | null
  calibration_due_at?: string | null
  notes?: string | null
}

export type ZoneSensorDeviceBinding = {
  zone_id: string
  sensor_id: string
  sensor_device_id?: string | null
  role: string
  is_enabled: boolean
  sensor_name?: string | null
}

export type Zone = {
  zone_id: string
  name: string
  location: string
  crop_type: string
  soil_moisture_threshold: number
  default_duration_minutes: number
  is_enabled: boolean
  notes?: string | null
  sensor_ids: string[]
  sensor_devices?: ZoneSensorDeviceBinding[]
  actuators: Actuator[]
  created_at?: string | null
  updated_at?: string | null
}

export type PlanApproval = {
  approval_id: string
  plan_id: string
  decision: string
  actor: string
  comment?: string | null
  decided_at?: string | null
}

export type IrrigationSuggestion = {
  suggestion_id: string
  zone_id: string | null
  zone_name?: string | null
  conversation_id?: string | null
  trigger: string
  requested_by?: string | null
  proposed_action: string
  urgency: string
  risk_level: string
  recommended_duration_minutes: number
  reasoning_summary?: string | null
  evidence_summary?: Record<string, unknown> | null
  safety_review?: Record<string, unknown> | null
  created_at?: string | null
}

export type IrrigationPlan = {
  plan_id: string
  zone_id: string | null
  zone_name?: string | null
  actuator_id?: string | null
  actuator_name?: string | null
  conversation_id?: string | null
  trigger: string
  status: string
  approval_status: string
  execution_status: string
  proposed_action: string
  urgency: string
  risk_level: string
  recommended_duration_minutes: number
  requires_approval: boolean
  reasoning_summary?: string | null
  evidence_summary?: Record<string, unknown> | null
  safety_review?: Record<string, unknown> | null
  execution_result?: Record<string, unknown> | null
  workspace_path?: string | null
  requested_by?: string | null
  latest_approval?: PlanApproval | null
  created_at?: string | null
  updated_at?: string | null
}

export type DashboardData = {
  status: SystemStatus | null
  sensors: SensorSnapshot | null
  weather: WeatherData | null
  irrigation: IrrigationState | null
  decisions: DecisionLog[]
  zones: Zone[]
  plans: IrrigationPlan[]
  backendReachable: boolean
  error?: string
}

export type HistoryData = {
  logs: IrrigationLog[]
  decisions: DecisionLog[]
  conversations: ConversationSummary[]
  plans: IrrigationPlan[]
  active_plans?: IrrigationPlan[]
  tool_traces: ToolTrace[]
  audits?: AuditEvent[]
}

export type AlertEvent = {
  alert_id: string
  rule_key?: string | null
  severity: 'high' | 'medium' | 'low' | string
  status: 'open' | 'acknowledged' | 'resolved' | string
  title: string
  message: string
  zone_id?: string | null
  zone_name?: string | null
  sensor_device_id?: string | null
  sensor_name?: string | null
  actuator_id?: string | null
  actuator_name?: string | null
  plan_id?: string | null
  object_type?: string | null
  object_id?: string | null
  assignee?: string | null
  acknowledged_at?: string | null
  resolved_at?: string | null
  context?: Record<string, unknown> | null
  created_at?: string | null
  updated_at?: string | null
}

export type AuditEvent = {
  audit_id: string
  event_type: string
  actor: string
  object_type: string
  object_id?: string | null
  result: string
  comment?: string | null
  details?: Record<string, unknown> | null
  occurred_at?: string | null
}

export type AnalyticsOverview = {
  range: string
  kpis: {
    zone_count: number
    pending_plan_count: number
    active_alert_count: number
    executed_plan_count: number
  }
  soil_trend: ZoneTrendSeries
  plan_funnel: {
    range: string
    items: Array<{ stage: string; count: number }>
  }
  alert_trend: {
    range: string
    labels: string[]
    series: Record<string, number[]>
  }
  zone_health: Array<{
    zone_id: string
    zone_name: string
    soil_moisture: number
    deficit: number
    actuator_status: string
    alert_count: number
  }>
}

export type ZoneTrendSeries = {
  zone_id: string
  zone_name: string
  range: string
  labels: string[]
  soil_moisture: number[]
  threshold: number[]
}

export type ReportExportTask = {
  id: string
  type: 'operations' | 'audit' | 'zone'
  status: 'idle' | 'running' | 'completed' | 'error'
  downloadUrl?: string
  error?: string | null
}

export type StructuredJsonNode = {
  key: string
  label: string
  kind: 'primitive' | 'object' | 'array' | 'empty'
  value?: string | number | boolean | null
  summary?: string | null
  children?: StructuredJsonNode[]
}

export type StructuredJsonSection = {
  title: string
  description?: string | null
  nodes: StructuredJsonNode[]
}

export type PlanCardMetric = {
  label: string
  value: string
  tone?: UiTone
}

export type PlanCardBullet = {
  label: string
  detail: string
  tone?: UiTone
}

export type PlanCardSection = {
  title: string
  items: PlanCardMetric[]
}

export type PlanCardViewModel = {
  planId: string
  title: string
  summary: string
  actionLabel: string
  actionTone: UiTone
  riskLabel: string
  riskTone: UiTone
  statusLabel: string
  statusTone: UiTone
  metrics: PlanCardMetric[]
  reasons: string[]
  evidenceSections: PlanCardSection[]
  safetyItems: PlanCardBullet[]
  canApprove: boolean
  canReject: boolean
  canExecute: boolean
  approveDisabledReason: string | null
  rejectDisabledReason: string | null
  executeDisabledReason: string | null
}

export type SuggestionCardViewModel = {
  suggestionId: string
  title: string
  summary: string
  actionLabel: string
  actionTone: UiTone
  riskLabel: string
  riskTone: UiTone
  reasons: string[]
  evidenceSections: PlanCardSection[]
  safetyItems: PlanCardBullet[]
}

export type ToolProgressStepViewModel = {
  id: string
  title: string
  detail: string
  tone?: UiTone
  meta: string[]
  phase?: 'evidence' | 'analysis' | 'planning' | 'approval' | 'execution' | 'audit' | null
  activeSkills?: string[]
}

export type ToolProgressViewModel = {
  traceId?: string
  status: 'running' | 'completed' | 'error'
  headline: string
  summary: string
  steps: ToolProgressStepViewModel[]
}

export type AuditRecordType = 'plan' | 'tool_trace' | 'log' | 'decision' | 'conversation' | 'audit'

export type AuditRecordBadge = {
  label: string
  tone?: UiTone
}

export type AuditRecordListItem = {
  id: string
  type: AuditRecordType
  title: string
  summary: string
  time: string | null
  badges: AuditRecordBadge[]
  meta: string[]
}

export type AuditRecordDetail = {
  id: string
  type: AuditRecordType
  title: string
  summary: string
  badges: AuditRecordBadge[]
  meta: Array<{ label: string; value: string }>
  highlights: PlanCardMetric[]
  sections: StructuredJsonSection[]
}

export type StreamEvent =
  | {
      type: 'text'
      content: string
      agent_name?: string | null
      node_name?: string | null
      active_skills?: string[] | null
    }
  | {
      type: 'tool_call'
      tool?: string
      content?: string
      trace_id?: string
      run_id?: string
      args?: Record<string, unknown> | null
      normalized_args?: Record<string, unknown> | null
      zone_id?: string | null
      plan_id?: string | null
      phase?: 'evidence' | 'analysis' | 'planning' | 'approval' | 'execution' | 'audit' | null
      active_skills?: string[] | null
      agent_name?: string | null
      node_name?: string | null
    }
  | {
      type: 'tool_result'
      tool?: string
      content?: string
      trace_id?: string
      run_id?: string
      args?: Record<string, unknown> | null
      normalized_args?: Record<string, unknown> | null
      zone_id?: string | null
      plan_id?: string | null
      output_preview?: string | null
      duration_ms?: number | null
      result?: unknown
      phase?: 'evidence' | 'analysis' | 'planning' | 'approval' | 'execution' | 'audit' | null
      active_skills?: string[] | null
      agent_name?: string | null
      node_name?: string | null
    }
  | { type: 'plan_proposed'; plan: IrrigationPlan; agent_name?: string | null; node_name?: string | null; phase?: string | null; active_skills?: string[] | null }
  | { type: 'plan_updated'; plan: IrrigationPlan; agent_name?: string | null; node_name?: string | null; phase?: string | null; active_skills?: string[] | null }
  | { type: 'suggestion_result'; suggestion: IrrigationSuggestion; agent_name?: string | null; node_name?: string | null; phase?: string | null; active_skills?: string[] | null }
  | { type: 'approval_requested'; tool?: string; details?: Record<string, unknown>; agent_name?: string | null; node_name?: string | null; phase?: string | null; active_skills?: string[] | null }
  | { type: 'approval_result'; plan: IrrigationPlan; decision: string; agent_name?: string | null; node_name?: string | null; phase?: string | null; active_skills?: string[] | null }
  | { type: 'execution_result'; plan: IrrigationPlan; agent_name?: string | null; node_name?: string | null; phase?: string | null; active_skills?: string[] | null }
  | { type: 'error'; content: string }
  | { type: 'done'; inferred_mode?: ChatMode; active_skills?: string[] | null; working_memory?: WorkingMemory | null }
