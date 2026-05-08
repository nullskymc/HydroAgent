import {
  AuditEvent,
  AuditRecordBadge,
  AuditRecordDetail,
  AuditRecordListItem,
  ConversationSummary,
  DecisionLog,
  HistoryData,
  IrrigationLog,
  IrrigationPlan,
  IrrigationSuggestion,
  PlanCardBullet,
  PlanCardMetric,
  PlanCardSection,
  PlanCardViewModel,
  SuggestionCardViewModel,
  StructuredJsonNode,
  StructuredJsonSection,
  ToolProgressStepViewModel,
  ToolProgressViewModel,
  ToolTrace,
  UiTone,
} from '@/lib/types'
import { labelFor } from '@/lib/labels'
import { formatDateTime } from '@/lib/utils'

const FIELD_LABELS: Record<string, string> = {
  action: '动作',
  actuator: '执行器',
  actuator_id: '执行器编号',
  actuator_name: '执行器名称',
  actor: '操作人',
  approval_id: '审批编号',
  approval_required: '需要审批',
  approval_status: '审批状态',
  average: '平均值',
  blockers: '阻塞项',
  can_execute: '可执行',
  capabilities: '能力',
  city: '城市',
  comment: '备注',
  condition: '天气状况',
  conversation_id: '会话编号',
  created_at: '创建时间',
  crop_type: '作物',
  current_plan: '当前计划',
  date: '日期',
  day_temp: '白天温度',
  day_weather: '白天天气',
  decision: '审批结论',
  decision_result: '决策结果',
  default_duration_minutes: '默认时长',
  details: '详细信息',
  duration_minutes: '持续时长',
  elapsed_minutes: '已运行时长',
  end_time: '结束时间',
  event: '事件',
  executed_at: '执行时间',
  executed_by: '执行人',
  execution_result: '执行回执',
  execution_status: '执行状态',
  forecast_days: '天气预报',
  humidity: '湿度',
  input_context: '输入上下文',
  irrigation_advice: '灌溉建议',
  is_enabled: '是否启用',
  latest_approval: '最近审批',
  light_intensity: '光照强度',
  location: '位置',
  message: '说明',
  moisture_delta: '湿度差值',
  name: '名称',
  night_temp: '夜间温度',
  notes: '备注',
  pending_plan: '待处理计划',
  plan_id: '计划编号',
  precipitation: '降水量',
  proposed_action: '建议动作',
  rainfall: '降雨量',
  rain_expected: '近期是否有雨',
  raw_data: '原始数据',
  raw_readings: '原始读数',
  readings: '读数',
  reason: '原因',
  reasoning_chain: '推理摘要',
  reasoning_summary: '摘要',
  recommended_duration_minutes: '建议时长',
  reflection_notes: '反思记录',
  requires_approval: '是否需要审批',
  response: '响应',
  result: '结果',
  risk_factors: '风险因素',
  risk_level: '风险等级',
  role: '角色',
  sensor_id: '传感器编号',
  sensor_ids: '传感器',
  sensor_summary: '传感器概览',
  soil_moisture: '土壤湿度',
  soil_moisture_threshold: '湿度阈值',
  source: '来源',
  start_time: '开始时间',
  status: '状态',
  status_assessment: '状态评估',
  temperature: '温度',
  threshold: '阈值',
  timestamp: '时间',
  tools_used: '工具列表',
  trigger: '触发方式',
  units: '单位',
  updated_at: '更新时间',
  urgency: '紧急程度',
  weather: '天气',
  weather_summary: '天气概览',
  wind_direction: '风向',
  wind_power: '风力',
  wind_speed: '风速',
  workspace_path: '工作区路径',
  zone: '分区',
  zone_id: '分区编号',
  zone_name: '分区名称',
}

const TOOL_LABELS: Record<string, { title: string; detail: string }> = {
  list_farm_zones: {
    title: '读取分区与设备信息',
    detail: '正在确认可用的分区、传感器和阀门。',
  },
  query_sensor_data: {
    title: '检查土壤与传感器状态',
    detail: '正在读取当前湿度、温度和环境读数。',
  },
  query_weather: {
    title: '检查天气风险',
    detail: '正在查看未来天气和降雨风险。',
  },
  get_zone_operating_status: {
    title: '检查分区运行状态',
    detail: '正在确认执行器、当前计划和现场状态。',
  },
  create_irrigation_plan: {
    title: '生成灌溉计划',
    detail: '正在整理证据并生成结构化灌溉建议。',
  },
  get_plan_status: {
    title: '读取计划状态',
    detail: '正在确认当前计划是否待批、已批或已执行。',
  },
  approve_irrigation_plan: {
    title: '记录审批结果',
    detail: '正在写入批准结果并更新计划状态。',
  },
  reject_irrigation_plan: {
    title: '记录拒绝结果',
    detail: '正在写入拒绝结果并停止执行路径。',
  },
  control_irrigation: {
    title: '执行灌溉动作',
    detail: '正在校验执行条件并回写执行结果。',
  },
}

function looksLikeStructuredPayload(value?: string | null) {
  if (!value) return false
  const trimmed = value.trim()
  return trimmed.startsWith('{') || trimmed.startsWith('[') || /"\w+"\s*:/.test(trimmed)
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : []
}

function asNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function asBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

function asString(value: unknown): string | null {
  return typeof value === 'string' && value.trim().length > 0 ? value : null
}

function asStringArray(value: unknown): string[] {
  return asArray(value).map((item) => asString(item)).filter(Boolean) as string[]
}

function humanizeKey(key: string) {
  return FIELD_LABELS[key] || key.replace(/_/g, ' ')
}

function formatBoolean(value: boolean) {
  return value ? '是' : '否'
}

function formatRiskLabel(value?: string | null) {
  if (value === 'high') return '高风险'
  if (value === 'medium') return '中风险'
  if (value === 'low') return '低风险'
  return '未标记'
}

export function getRiskTone(value?: string | null): UiTone {
  if (value === 'high') return 'danger'
  if (value === 'medium') return 'warning'
  if (value === 'low') return 'success'
  return 'default'
}

function formatActionLabel(value?: string | null) {
  if (value === 'start') return '建议灌溉'
  if (value === 'hold') return '建议暂缓'
  if (value === 'defer') return '建议延后'
  if (value === 'stop') return '建议停止'
  return '建议观察'
}

function formatApprovalLabel(value?: string | null) {
  if (value === 'pending') return '待审批'
  if (value === 'approved') return '已批准'
  if (value === 'rejected') return '已拒绝'
  if (value === 'not_required') return '无需审批'
  return '未知'
}

function formatExecutionLabel(value?: string | null) {
  if (value === 'not_started') return '未执行'
  if (value === 'running') return '执行中'
  if (value === 'executed') return '已执行'
  if (value === 'stopped' || value === 'completed') return '已结束'
  return '未知'
}

function formatPlanStatusLabel(value?: string | null) {
  if (value === 'pending_approval') return '待审批'
  if (value === 'approved') return '已批准'
  if (value === 'executing') return '执行中'
  if (value === 'executed' || value === 'completed') return '已完成'
  if (value === 'rejected') return '已拒绝'
  if (value === 'superseded') return '已替换'
  if (value === 'cancelled') return '已取消'
  if (value === 'ready') return '已记录'
  return '处理中'
}

function toneFromApproval(value?: string | null): UiTone {
  if (value === 'approved') return 'success'
  if (value === 'pending') return 'warning'
  if (value === 'rejected') return 'danger'
  return 'default'
}

function toneFromStatus(value?: string | null): UiTone {
  if (value === 'approved' || value === 'completed' || value === 'executed') return 'success'
  if (value === 'executing') return 'warning'
  if (value === 'pending_approval') return 'warning'
  if (value === 'rejected' || value === 'cancelled' || value === 'superseded') return 'danger'
  return 'default'
}

function splitSummary(text?: string | null) {
  return String(text || '')
    .split(/[。！？]/)
    .map((part) => part.trim())
    .filter(Boolean)
}

function formatForecastSummary(forecastDays: unknown[]) {
  const visibleDays = forecastDays
    .map((item) => asRecord(item))
    .filter(Boolean)
    .slice(0, 3)
    .map((item) => {
      const date = asString(item?.date)
      const weather = asString(item?.day_weather) || '未知天气'
      const temp = asString(item?.day_temp)
      return [date ? date.slice(5) : null, weather, temp ? `${temp}°C` : null].filter(Boolean).join(' · ')
    })
  return visibleDays.length > 0 ? visibleDays.join(' / ') : '暂无天气预报'
}

function formatDisplayValue(value: unknown, key?: string): string {
  if (value === null || value === undefined || value === '') return '--'
  if (typeof value === 'boolean') return formatBoolean(value)
  if (typeof value === 'number') {
    if (key && ['soil_moisture', 'soil_moisture_threshold', 'humidity'].includes(key)) {
      return `${value.toFixed(2)}%`
    }
    if (key && ['temperature', 'day_temp', 'night_temp'].includes(key)) {
      return `${value.toFixed(2)}°C`
    }
    if (key === 'rainfall') {
      return `${value.toFixed(2)} mm/h`
    }
    if (key === 'light_intensity') {
      return `${value.toFixed(2)} lux`
    }
    return `${value}`
  }
  if (typeof value === 'string') {
    if (/^\d{4}-\d{2}-\d{2}T/.test(value)) {
      return formatDateTime(value)
    }
    return value
  }
  if (Array.isArray(value)) {
    return value.length === 0 ? '无数据' : `${value.length} 项`
  }
  if (typeof value === 'object') {
    return value && Object.keys(value as Record<string, unknown>).length > 0 ? `${Object.keys(value as Record<string, unknown>).length} 个字段` : '无数据'
  }
  return String(value)
}

function buildJsonNode(key: string, value: unknown): StructuredJsonNode {
  const arrayIndexMatch = key.match(/_(\d+)$/)
  const label = arrayIndexMatch ? `第 ${Number(arrayIndexMatch[1]) + 1} 项` : humanizeKey(key)
  if (value === null || value === undefined) {
    return { key, label, kind: 'empty', summary: '无数据' }
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return { key, label, kind: 'empty', summary: '无数据' }
    }
    return {
      key,
      label,
      kind: 'array',
      summary: `${value.length} 项`,
      children: value.map((item, index) => buildJsonNode(`${key}_${index}`, item)),
    }
  }
  if (typeof value === 'object') {
    const record = asRecord(value)
    if (!record || Object.keys(record).length === 0) {
      return { key, label, kind: 'empty', summary: '无数据' }
    }
    return {
      key,
      label,
      kind: 'object',
      summary: `${Object.keys(record).length} 个字段`,
      children: Object.entries(record).map(([childKey, childValue]) => buildJsonNode(childKey, childValue)),
    }
  }
  return {
    key,
    label,
    kind: 'primitive',
    value: formatDisplayValue(value, key),
  }
}

export function toStructuredJsonSection(
  title: string,
  value: unknown,
  description?: string | null,
): StructuredJsonSection | null {
  const record = asRecord(value)
  if (!record || Object.keys(record).length === 0) return null
  return {
    title,
    description,
    nodes: Object.entries(record).map(([key, item]) => buildJsonNode(key, item)),
  }
}

function buildMetric(label: string, value: string, tone: UiTone = 'default'): PlanCardMetric {
  return { label, value, tone }
}

function buildBullet(label: string, detail: string, tone: UiTone = 'default'): PlanCardBullet {
  return { label, detail, tone }
}

function extractPlanEvidence(plan: IrrigationPlan) {
  const evidence = asRecord(plan.evidence_summary)
  const zone = asRecord(evidence?.zone)
  const sensorSummary = asRecord(evidence?.sensor_summary)
  const sensorAverage = asRecord(sensorSummary?.average)
  const weatherSummary = asRecord(evidence?.weather_summary)
  const safetyReview = asRecord(plan.safety_review)
  const actuator = asRecord(asArray(zone?.actuators)[0])

  return {
    zone,
    sensorSummary,
    sensorAverage,
    weatherSummary,
    safetyReview,
    actuator,
    blockers: asStringArray(safetyReview?.blockers),
    riskFactors: asStringArray(safetyReview?.risk_factors),
  }
}

function extractSuggestionEvidence(suggestion: IrrigationSuggestion) {
  const evidence = asRecord(suggestion.evidence_summary)
  const zone = asRecord(evidence?.zone)
  const sensorSummary = asRecord(evidence?.sensor_summary)
  const sensorAverage = asRecord(sensorSummary?.average)
  const weatherSummary = asRecord(evidence?.weather_summary)
  const safetyReview = asRecord(suggestion.safety_review)
  const actuator = asRecord(asArray(zone?.actuators)[0])

  return {
    zone,
    sensorSummary,
    sensorAverage,
    weatherSummary,
    safetyReview,
    actuator,
    blockers: asStringArray(safetyReview?.blockers),
    riskFactors: asStringArray(safetyReview?.risk_factors),
  }
}

function buildPlanReasons(plan: IrrigationPlan) {
  const { zone, sensorAverage, weatherSummary, blockers, riskFactors, actuator } = extractPlanEvidence(plan)
  const threshold = asNumber(zone?.soil_moisture_threshold)
  const moisture = asNumber(sensorAverage?.soil_moisture)
  const reasons: string[] = []

  if (moisture !== null && threshold !== null) {
    reasons.push(`当前土壤湿度 ${moisture.toFixed(2)}%，阈值 ${threshold.toFixed(2)}%。`)
  }

  const rainExpected = asBoolean(weatherSummary?.rain_expected)
  if (rainExpected !== null) {
    reasons.push(rainExpected ? '未来 48 小时存在降雨风险。' : '未来 48 小时暂无明显降雨风险。')
  }

  if (blockers.length > 0) {
    reasons.push(`当前阻塞项：${blockers.join('、')}。`)
  } else if (riskFactors.length > 0) {
    reasons.push(`主要风险：${riskFactors.join('、')}。`)
  } else if (actuator) {
    const actuatorStatus = asString(actuator.status)
    if (actuatorStatus) {
      reasons.push(`执行器当前状态：${actuatorStatus === 'idle' ? '空闲' : actuatorStatus}。`)
    }
  }

  if (reasons.length > 0) return reasons
  const summarySentences = splitSummary(plan.reasoning_summary)
  return summarySentences.length > 0 ? summarySentences : ['系统已整理当前证据并给出建议。']
}

function buildSuggestionReasons(suggestion: IrrigationSuggestion) {
  const { zone, sensorAverage, weatherSummary, blockers, riskFactors, actuator } = extractSuggestionEvidence(suggestion)
  const threshold = asNumber(zone?.soil_moisture_threshold)
  const moisture = asNumber(sensorAverage?.soil_moisture)
  const reasons: string[] = []

  if (moisture !== null && threshold !== null) {
    reasons.push(`当前土壤湿度 ${moisture.toFixed(2)}%，阈值 ${threshold.toFixed(2)}%。`)
  }

  const rainExpected = asBoolean(weatherSummary?.rain_expected)
  if (rainExpected !== null) {
    reasons.push(rainExpected ? '未来 48 小时存在降雨风险。' : '未来 48 小时暂无明显降雨风险。')
  }

  if (blockers.length > 0) {
    reasons.push(`当前阻塞项：${blockers.join('、')}。`)
  } else if (riskFactors.length > 0) {
    reasons.push(`主要风险：${riskFactors.join('、')}。`)
  } else if (actuator) {
    const actuatorStatus = asString(actuator.status)
    if (actuatorStatus) {
      reasons.push(`执行器当前状态：${actuatorStatus === 'idle' ? '空闲' : actuatorStatus}。`)
    }
  }

  if (reasons.length > 0) return reasons
  const summarySentences = splitSummary(suggestion.reasoning_summary)
  return summarySentences.length > 0 ? summarySentences : ['系统已整理当前证据并给出非执行型建议。']
}

function buildEvidenceSections(plan: IrrigationPlan): PlanCardSection[] {
  const { zone, sensorSummary, sensorAverage, weatherSummary, actuator } = extractPlanEvidence(plan)
  const threshold = asNumber(zone?.soil_moisture_threshold)
  const moisture = asNumber(sensorAverage?.soil_moisture)
  const rainfall = asNumber(sensorAverage?.rainfall)
  const temperature = asNumber(sensorAverage?.temperature)
  const forecastDays = asArray(weatherSummary?.forecast_days)
  const rainExpected = asBoolean(weatherSummary?.rain_expected)

  const sections: PlanCardSection[] = [
    {
      title: '传感器概览',
      items: [
        buildMetric('当前湿度', moisture !== null ? `${moisture.toFixed(2)}%` : '--'),
        buildMetric('目标阈值', threshold !== null ? `${threshold.toFixed(2)}%` : '--'),
        buildMetric('温度', temperature !== null ? `${temperature.toFixed(2)}°C` : '--'),
        buildMetric('降雨', rainfall !== null ? `${rainfall.toFixed(2)} mm/h` : '--'),
      ],
    },
    {
      title: '天气概览',
      items: [
        buildMetric('近期降雨', rainExpected === null ? '--' : rainExpected ? '有风险' : '风险较低', rainExpected ? 'warning' : 'success'),
        buildMetric('预报摘要', formatForecastSummary(forecastDays)),
      ],
    },
    {
      title: '执行条件',
      items: [
        buildMetric('执行器', asString(actuator?.name) || '未配置'),
        buildMetric(
          '运行状态',
          asString(actuator?.status) === 'running'
            ? '运行中'
            : asString(actuator?.status) === 'idle'
              ? '空闲'
              : asString(actuator?.status) || '未知',
          asString(actuator?.status) === 'running' ? 'warning' : 'success',
        ),
        buildMetric('是否启用', asBoolean(actuator?.is_enabled) === null ? '--' : asBoolean(actuator?.is_enabled) ? '已启用' : '已禁用'),
        buildMetric('传感器状态', asString(sensorSummary?.status) === 'ok' ? '数据正常' : '数据缺失'),
      ],
    },
  ]

  return sections
}

function buildSuggestionEvidenceSections(suggestion: IrrigationSuggestion): PlanCardSection[] {
  const { zone, sensorSummary, sensorAverage, weatherSummary, actuator } = extractSuggestionEvidence(suggestion)
  const threshold = asNumber(zone?.soil_moisture_threshold)
  const moisture = asNumber(sensorAverage?.soil_moisture)
  const rainfall = asNumber(sensorAverage?.rainfall)
  const temperature = asNumber(sensorAverage?.temperature)
  const forecastDays = asArray(weatherSummary?.forecast_days)
  const rainExpected = asBoolean(weatherSummary?.rain_expected)

  return [
    {
      title: '传感器概览',
      items: [
        buildMetric('当前湿度', moisture !== null ? `${moisture.toFixed(2)}%` : '--'),
        buildMetric('目标阈值', threshold !== null ? `${threshold.toFixed(2)}%` : '--'),
        buildMetric('温度', temperature !== null ? `${temperature.toFixed(2)}°C` : '--'),
        buildMetric('降雨', rainfall !== null ? `${rainfall.toFixed(2)} mm/h` : '--'),
      ],
    },
    {
      title: '天气概览',
      items: [
        buildMetric('近期降雨', rainExpected === null ? '--' : rainExpected ? '有风险' : '风险较低', rainExpected ? 'warning' : 'success'),
        buildMetric('预报摘要', formatForecastSummary(forecastDays)),
      ],
    },
    {
      title: '现场条件',
      items: [
        buildMetric('执行器', asString(actuator?.name) || '未配置'),
        buildMetric(
          '运行状态',
          asString(actuator?.status) === 'running'
            ? '运行中'
            : asString(actuator?.status) === 'idle'
              ? '空闲'
              : asString(actuator?.status) || '未知',
          asString(actuator?.status) === 'running' ? 'warning' : 'success',
        ),
        buildMetric('是否启用', asBoolean(actuator?.is_enabled) === null ? '--' : asBoolean(actuator?.is_enabled) ? '已启用' : '已禁用'),
        buildMetric('传感器状态', asString(sensorSummary?.status) === 'ok' ? '数据正常' : '数据缺失'),
      ],
    },
  ]
}

function buildSafetyItems(plan: IrrigationPlan): PlanCardBullet[] {
  const { safetyReview, blockers, riskFactors } = extractPlanEvidence(plan)
  const canExecute = asBoolean(safetyReview?.can_execute)
  const approvalRequired = asBoolean(safetyReview?.approval_required)

  const items: PlanCardBullet[] = [
    buildBullet('可执行性', canExecute === null ? '系统未返回执行判断。' : canExecute ? '当前满足执行条件。' : '当前不满足执行条件。', canExecute ? 'success' : 'warning'),
    buildBullet('审批要求', approvalRequired === null ? '未标记审批要求。' : approvalRequired ? '执行前需要人工审批。' : '当前无需审批。'),
  ]

  if (blockers.length > 0) {
    blockers.forEach((blocker) => items.push(buildBullet('阻塞项', blocker, 'danger')))
  } else {
    items.push(buildBullet('阻塞项', '当前没有阻塞项。', 'success'))
  }

  if (riskFactors.length > 0) {
    riskFactors.forEach((risk) => items.push(buildBullet('风险因素', risk, 'warning')))
  } else {
    items.push(buildBullet('风险因素', '当前没有额外风险因素。', 'success'))
  }

  return items
}

function buildSuggestionSafetyItems(suggestion: IrrigationSuggestion): PlanCardBullet[] {
  const { safetyReview, blockers, riskFactors } = extractSuggestionEvidence(suggestion)
  const canExecute = asBoolean(safetyReview?.can_execute)

  const items: PlanCardBullet[] = [
    buildBullet(
      '执行性结论',
      canExecute === null
        ? '系统未返回执行判断。'
        : canExecute
          ? '当前条件允许执行，但本轮建议未生成 start 计划。'
          : '当前条件不适合直接执行灌溉。',
      canExecute ? 'warning' : 'success',
    ),
  ]

  if (blockers.length > 0) {
    blockers.forEach((blocker) => items.push(buildBullet('阻塞项', blocker, 'danger')))
  } else {
    items.push(buildBullet('阻塞项', '当前没有阻塞项。', 'success'))
  }

  if (riskFactors.length > 0) {
    riskFactors.forEach((risk) => items.push(buildBullet('风险因素', risk, 'warning')))
  } else {
    items.push(buildBullet('风险因素', '当前没有额外风险因素。', 'success'))
  }

  return items
}

export function toPlanCardViewModel(plan: IrrigationPlan): PlanCardViewModel {
  const actionTone = plan.proposed_action === 'start' ? 'success' : plan.proposed_action === 'hold' ? 'warning' : 'default'
  const statusTone = toneFromStatus(plan.status)
  const riskTone = getRiskTone(plan.risk_level)
  return {
    planId: plan.plan_id,
    title: plan.zone_name || plan.zone_id || '未命名分区',
    summary: plan.reasoning_summary || buildPlanReasons(plan)[0] || '系统已生成灌溉建议。',
    actionLabel: formatActionLabel(plan.proposed_action),
    actionTone,
    riskLabel: formatRiskLabel(plan.risk_level),
    riskTone,
    statusLabel: formatPlanStatusLabel(plan.status),
    statusTone,
    metrics: [
      buildMetric('审批', formatApprovalLabel(plan.approval_status), toneFromApproval(plan.approval_status)),
      buildMetric('执行', formatExecutionLabel(plan.execution_status), toneFromStatus(plan.execution_status)),
      buildMetric('建议时长', `${plan.recommended_duration_minutes} 分钟`),
      buildMetric('当前状态', formatPlanStatusLabel(plan.status), statusTone),
    ],
    reasons: buildPlanReasons(plan),
    evidenceSections: buildEvidenceSections(plan),
    safetyItems: buildSafetyItems(plan),
    canApprove: plan.status === 'pending_approval',
    canReject: plan.status === 'pending_approval',
    canExecute: plan.status === 'approved' && plan.proposed_action === 'start',
    approveDisabledReason: plan.status === 'pending_approval' ? null : '仅待审批状态的计划可批准',
    rejectDisabledReason: plan.status === 'pending_approval' ? null : '仅待审批状态的计划可驳回',
    executeDisabledReason: plan.status === 'approved' && plan.proposed_action === 'start' ? null : '仅已批准且建议开启的计划可执行',
  }
}

export function toSuggestionCardViewModel(suggestion: IrrigationSuggestion): SuggestionCardViewModel {
  return {
    suggestionId: suggestion.suggestion_id,
    title: suggestion.zone_name || suggestion.zone_id || '未命名分区',
    summary: suggestion.reasoning_summary || buildSuggestionReasons(suggestion)[0] || '系统已生成非执行型灌溉建议。',
    actionLabel: formatActionLabel(suggestion.proposed_action),
    actionTone: suggestion.proposed_action === 'hold' ? 'warning' : suggestion.proposed_action === 'defer' ? 'default' : 'success',
    riskLabel: formatRiskLabel(suggestion.risk_level),
    riskTone: getRiskTone(suggestion.risk_level),
    reasons: buildSuggestionReasons(suggestion),
    evidenceSections: buildSuggestionEvidenceSections(suggestion),
    safetyItems: buildSuggestionSafetyItems(suggestion),
  }
}

type ToolActivityInput = {
  id: string
  title?: string | null
  detail?: string | null
  toolName?: string | null
  agentName?: string | null
  subagentName?: string | null
  phase?: string | null
  activeSkills?: string[] | null
  durationMs?: number | null
  tone?: UiTone
}

export function toToolProgressStep(input: ToolActivityInput): ToolProgressStepViewModel {
  const toolCopy = input.toolName ? TOOL_LABELS[input.toolName] : null
  const title = toolCopy?.title || input.title || '处理步骤'
  const detail =
    input.detail && !looksLikeStructuredPayload(input.detail)
      ? input.detail
      : toolCopy?.detail || '系统正在处理当前请求。'
  const meta = [
    input.subagentName ? `代理 ${input.subagentName}` : null,
    input.phase ? `阶段 ${input.phase}` : null,
    input.toolName ? `工具 ${input.toolName}` : null,
    input.activeSkills && input.activeSkills.length > 0 ? `技能 ${input.activeSkills.join(' / ')}` : null,
    input.agentName && input.agentName !== 'hydro-supervisor' ? `来源 ${input.agentName}` : null,
    input.durationMs ? `耗时 ${input.durationMs}ms` : null,
  ].filter(Boolean) as string[]

  return {
    id: input.id,
    title,
    detail,
    tone: input.tone || 'default',
    meta,
    phase: (input.phase as ToolProgressStepViewModel['phase']) || null,
    activeSkills: input.activeSkills?.filter(Boolean) || [],
  }
}

function formatTraceHeadline(status: ToolProgressViewModel['status']) {
  if (status === 'error') return '处理出现问题'
  if (status === 'running') return '正在分析灌溉条件'
  return '分析与计划已完成'
}

export function toToolProgressViewModel(trace: ToolTrace): ToolProgressViewModel {
  const steps = trace.steps.map((step) =>
    toToolProgressStep({
      id: `${trace.trace_id}-${step.step_index}`,
      title: step.title,
      detail: step.detail,
      toolName: step.tool_name,
      agentName: step.agent_name,
      subagentName: step.subagent_name,
      phase: step.phase,
      activeSkills: step.active_skills,
      durationMs: step.duration_ms,
      tone: step.tone || (step.status === 'error' ? 'danger' : step.status === 'running' ? 'warning' : 'success'),
    }),
  )
  const summary = steps.at(-1)?.detail || (trace.status === 'running' ? '系统正在等待更多处理结果。' : '本轮没有工具事件。')
  return {
    traceId: trace.trace_id,
    status: trace.status === 'error' ? 'error' : trace.status === 'running' ? 'running' : 'completed',
    headline: formatTraceHeadline(trace.status === 'error' ? 'error' : trace.status === 'running' ? 'running' : 'completed'),
    summary,
    steps,
  }
}

function buildBadges(...badges: Array<AuditRecordBadge | null>): AuditRecordBadge[] {
  return badges.filter(Boolean) as AuditRecordBadge[]
}

export function planToAuditRecordListItem(plan: IrrigationPlan): AuditRecordListItem {
  const view = toPlanCardViewModel(plan)
  return {
    id: plan.plan_id,
    type: 'plan',
    title: `${view.title} · ${view.actionLabel}`,
    summary: view.summary,
    time: plan.updated_at || plan.created_at || null,
    badges: buildBadges(
      { label: view.riskLabel, tone: view.riskTone },
      { label: formatApprovalLabel(plan.approval_status), tone: toneFromApproval(plan.approval_status) },
      { label: formatExecutionLabel(plan.execution_status), tone: toneFromStatus(plan.execution_status) },
    ),
    meta: [`计划 ${plan.plan_id}`, `建议时长 ${plan.recommended_duration_minutes} 分钟`],
  }
}

export function toolTraceToAuditRecordListItem(trace: ToolTrace): AuditRecordListItem {
  const progress = toToolProgressViewModel(trace)
  return {
    id: trace.trace_id,
    type: 'tool_trace',
    title: trace.conversation_title || progress.headline,
    summary: progress.summary,
    time: trace.started_at || null,
    badges: buildBadges(
      { label: trace.status === 'running' ? '进行中' : trace.status === 'error' ? '失败' : '完成', tone: progress.status === 'error' ? 'danger' : progress.status === 'running' ? 'warning' : 'success' },
      { label: `${trace.tool_count || trace.steps.length} 步` },
    ),
    meta: [`分区 ${trace.zone_id || '--'}`, `计划 ${trace.plan_id || '--'}`],
  }
}

export function irrigationLogToAuditRecordListItem(log: IrrigationLog): AuditRecordListItem {
  return {
    id: String(log.id),
    type: 'log',
    title: `${log.event} · ${labelFor(log.status)}`,
    summary: log.message || '无附加说明',
    time: log.created_at || log.start_time || null,
    badges: buildBadges({ label: labelFor(log.status), tone: log.status === 'completed' ? 'success' : log.status === 'running' ? 'warning' : 'default' }),
    meta: [`分区 ${log.zone_id || '--'}`, `计划 ${log.plan_id || '--'}`, `执行器 ${log.actuator_id || '--'}`],
  }
}

export function decisionToAuditRecordListItem(decision: DecisionLog): AuditRecordListItem {
  return {
    id: decision.decision_id,
    type: 'decision',
    title: decision.reasoning_chain || '决策记录',
    summary: decision.reflection_notes || '查看详情以了解这次推理与记录。',
    time: decision.created_at || null,
    badges: buildBadges({ label: decision.trigger }),
    meta: [`分区 ${decision.zone_id || '--'}`, `计划 ${decision.plan_id || '--'}`],
  }
}

export function conversationToAuditRecordListItem(conversation: ConversationSummary): AuditRecordListItem {
  return {
    id: conversation.session_id,
    type: 'conversation',
    title: conversation.title,
    summary: `${conversation.message_count} 条消息`,
    time: conversation.updated_at || conversation.created_at || null,
    badges: buildBadges({ label: '会话' }),
    meta: [`会话 ${conversation.session_id}`],
  }
}

export function adminAuditToAuditRecordListItem(audit: AuditEvent): AuditRecordListItem {
  return {
    id: audit.audit_id,
    type: 'audit',
    title: audit.event_type,
    summary: audit.comment || `${audit.actor} 对 ${audit.object_type} 执行了操作`,
    time: audit.occurred_at || null,
    badges: buildBadges({ label: audit.result, tone: audit.result === 'success' ? 'success' : 'danger' }),
    meta: [`对象 ${audit.object_type}:${audit.object_id || '--'}`, `操作人 ${audit.actor}`],
  }
}

function buildMetaPairs(entries: Record<string, string | null | undefined>) {
  return Object.entries(entries)
    .filter(([, value]) => value && value !== '--')
    .map(([label, value]) => ({ label, value: value as string }))
}

export function planToAuditRecordDetail(plan: IrrigationPlan): AuditRecordDetail {
  const view = toPlanCardViewModel(plan)
  const sections = [
    toStructuredJsonSection('证据明细', plan.evidence_summary, '系统采集到的证据对象，已转换为结构化字段。'),
    toStructuredJsonSection('安全复核', plan.safety_review, '阻塞项、风险因素与可执行判断。'),
    toStructuredJsonSection('执行回执', plan.execution_result, '执行完成后回写的结果。'),
    toStructuredJsonSection('审批记录', plan.latest_approval, '最近一次审批结论。'),
  ].filter(Boolean) as StructuredJsonSection[]

  return {
    id: plan.plan_id,
    type: 'plan',
    title: `${view.title} · ${view.actionLabel}`,
    summary: view.summary,
    badges: buildBadges(
      { label: view.riskLabel, tone: view.riskTone },
      { label: formatApprovalLabel(plan.approval_status), tone: toneFromApproval(plan.approval_status) },
      { label: formatExecutionLabel(plan.execution_status), tone: toneFromStatus(plan.execution_status) },
    ),
    meta: buildMetaPairs({
      计划编号: plan.plan_id,
      分区编号: plan.zone_id,
      执行器编号: plan.actuator_id,
      触发方式: plan.trigger,
      请求来源: plan.requested_by,
      创建时间: formatDateTime(plan.created_at),
      更新时间: formatDateTime(plan.updated_at),
    }),
    highlights: view.metrics,
    sections,
  }
}

export function toolTraceToAuditRecordDetail(trace: ToolTrace): AuditRecordDetail {
  const progress = toToolProgressViewModel(trace)
  const sections: StructuredJsonSection[] = [
    {
      title: '处理步骤',
      description: '按时间顺序展示本轮处理的关键步骤。',
      nodes: progress.steps.map((step, index) =>
        buildJsonNode(`step_${index + 1}`, {
          title: step.title,
          detail: step.detail,
          meta: step.meta,
        }),
      ),
    },
  ]

  return {
    id: trace.trace_id,
    type: 'tool_trace',
    title: trace.conversation_title || progress.headline,
    summary: progress.summary,
    badges: buildBadges(
      { label: trace.status === 'running' ? '进行中' : trace.status === 'error' ? '失败' : '完成', tone: progress.status === 'error' ? 'danger' : progress.status === 'running' ? 'warning' : 'success' },
      { label: `${trace.tool_count || trace.steps.length} 步` },
    ),
    meta: buildMetaPairs({
      轨迹编号: trace.trace_id,
      会话编号: trace.conversation_id || '--',
      分区编号: trace.zone_id || '--',
      计划编号: trace.plan_id || '--',
      开始时间: formatDateTime(trace.started_at),
      结束时间: formatDateTime(trace.ended_at),
      总耗时: trace.duration_ms ? `${trace.duration_ms}ms` : '--',
    }),
    highlights: [
      buildMetric('当前状态', trace.status === 'running' ? '进行中' : trace.status === 'error' ? '失败' : '完成', progress.status === 'error' ? 'danger' : progress.status === 'running' ? 'warning' : 'success'),
      buildMetric('步骤数量', `${trace.tool_count || trace.steps.length} 步`),
    ],
    sections,
  }
}

export function irrigationLogToAuditRecordDetail(log: IrrigationLog): AuditRecordDetail {
  return {
    id: String(log.id),
    type: 'log',
    title: `${log.event} · ${labelFor(log.status)}`,
    summary: log.message || '无附加说明',
    badges: buildBadges({ label: labelFor(log.status), tone: log.status === 'completed' ? 'success' : log.status === 'running' ? 'warning' : 'default' }),
    meta: buildMetaPairs({
      记录编号: String(log.id),
      分区编号: log.zone_id || '--',
      计划编号: log.plan_id || '--',
      执行器编号: log.actuator_id || '--',
      开始时间: formatDateTime(log.start_time),
      结束时间: formatDateTime(log.end_time),
      创建时间: formatDateTime(log.created_at),
    }),
    highlights: [
      buildMetric('事件', log.event),
      buildMetric('状态', labelFor(log.status), log.status === 'completed' ? 'success' : log.status === 'running' ? 'warning' : 'default'),
      buildMetric('计划时长', log.duration_planned !== null ? `${log.duration_planned} 秒` : '--'),
    ],
    sections: [],
  }
}

export function decisionToAuditRecordDetail(decision: DecisionLog): AuditRecordDetail {
  const sections = [
    toStructuredJsonSection('输入上下文', decision.input_context, '决策时携带的上下文参数。'),
    toStructuredJsonSection('决策结果', decision.decision_result, '本次推理最终产生的结构化结果。'),
  ].filter(Boolean) as StructuredJsonSection[]

  return {
    id: decision.decision_id,
    type: 'decision',
    title: decision.reasoning_chain || '决策记录',
    summary: decision.reflection_notes || '无反思摘要',
    badges: buildBadges({ label: decision.trigger }),
    meta: buildMetaPairs({
      决策编号: decision.decision_id,
      分区编号: decision.zone_id || '--',
      计划编号: decision.plan_id || '--',
      创建时间: formatDateTime(decision.created_at),
    }),
    highlights: [
      buildMetric('触发方式', decision.trigger),
      buildMetric('使用工具', decision.tools_used?.join('、') || '--'),
      buildMetric('效果分数', decision.effectiveness_score !== null ? `${decision.effectiveness_score}` : '--'),
    ],
    sections,
  }
}

export function conversationToAuditRecordDetail(conversation: ConversationSummary): AuditRecordDetail {
  return {
    id: conversation.session_id,
    type: 'conversation',
    title: conversation.title,
    summary: `${conversation.message_count} 条消息`,
    badges: buildBadges({ label: '会话' }),
    meta: buildMetaPairs({
      会话编号: conversation.session_id,
      创建时间: formatDateTime(conversation.created_at),
      更新时间: formatDateTime(conversation.updated_at),
    }),
    highlights: [
      buildMetric('消息数量', `${conversation.message_count}`),
    ],
    sections: [],
  }
}

export function adminAuditToAuditRecordDetail(audit: AuditEvent): AuditRecordDetail {
  const sections = [toStructuredJsonSection('事件详情', audit.details, '管理员操作产生的结构化上下文。')].filter(Boolean) as StructuredJsonSection[]
  return {
    id: audit.audit_id,
    type: 'audit',
    title: audit.event_type,
    summary: audit.comment || `${audit.actor} 执行了后台管理动作。`,
    badges: buildBadges({ label: audit.result, tone: audit.result === 'success' ? 'success' : 'danger' }),
    meta: buildMetaPairs({
      审计编号: audit.audit_id,
      操作人: audit.actor,
      对象类型: audit.object_type,
      对象编号: audit.object_id || '--',
      发生时间: formatDateTime(audit.occurred_at),
    }),
    highlights: [
      buildMetric('结果', audit.result, audit.result === 'success' ? 'success' : 'danger'),
      buildMetric('对象', `${audit.object_type} / ${audit.object_id || '--'}`),
    ],
    sections,
  }
}

export function buildAuditRecordGroups(history: HistoryData) {
  return [
    { key: 'plans', label: '计划记录', items: history.plans.map(planToAuditRecordListItem) },
    { key: 'tool_traces', label: '工具链记录', items: history.tool_traces.map(toolTraceToAuditRecordListItem) },
    { key: 'logs', label: '执行日志', items: history.logs.map(irrigationLogToAuditRecordListItem) },
    { key: 'decisions', label: '决策审计', items: history.decisions.map(decisionToAuditRecordListItem) },
    { key: 'conversations', label: '会话记录', items: history.conversations.map(conversationToAuditRecordListItem) },
    { key: 'audits', label: '管理员操作', items: (history.audits || []).map(adminAuditToAuditRecordListItem) },
  ] as const
}
