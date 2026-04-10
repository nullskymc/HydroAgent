'use client'

import ReactECharts from 'echarts-for-react'
import { Activity, AlertTriangle, Droplets, Gauge, GitBranch, RadioTower, Waves } from 'lucide-react'
import { AnalyticsOverview, DashboardData, HistoryData, IrrigationPlan } from '@/lib/types'
import { formatDateTime, formatNumber } from '@/lib/utils'

type MlForecastPoint = {
  label: string
  value: number
}

type MlPredictionView = {
  current: number | null
  predicted: number | null
  confidence: string
  sampleCount: number | null
  planLabel: string
  points: MlForecastPoint[]
}

type DecisionModelView = {
  action: string
  duration: number | null
  confidence: number | null
  sampleCount: number | null
  planLabel: string
  topFactors: string[]
}

type KpiItem = {
  label: string
  value: string
  detail: string
  icon: typeof Activity
  tone: 'ok' | 'warn' | 'danger' | 'muted'
}

function isPendingPlan(plan: IrrigationPlan) {
  return plan.status === 'pending_approval'
}

function isApprovedPlan(plan: IrrigationPlan) {
  return plan.status === 'approved'
}

function isExecutedPlan(plan: IrrigationPlan) {
  return plan.status === 'executing' || plan.status === 'completed'
}

function toNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim()) {
    const parsed = Number(value)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function readRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null
}

function buildFallbackOverview(dashboard: DashboardData): AnalyticsOverview {
  const zones = dashboard.zones
  const sensorRows = dashboard.sensors?.sensors || []
  const labels = zones.map((zone) => zone.name)
  const zoneHealth = zones.map((zone) => {
    const reading = sensorRows.find((item) => String(item.zone_id || '') === zone.zone_id)
    const moisture = toNumber(reading?.soil_moisture) || 0
    const threshold = zone.soil_moisture_threshold || 40
    return {
      zone_id: zone.zone_id,
      zone_name: zone.name,
      soil_moisture: Number(moisture.toFixed(2)),
      deficit: Number(Math.max(0, threshold - moisture).toFixed(2)),
      actuator_status: zone.actuators[0]?.status || 'unknown',
      alert_count: moisture < threshold ? 1 : 0,
    }
  })

  return {
    range: '7d',
    kpis: {
      zone_count: zones.length,
      pending_plan_count: dashboard.plans.filter((plan) => isPendingPlan(plan)).length,
      active_alert_count: zoneHealth.reduce((total, item) => total + item.alert_count, 0),
      executed_plan_count: dashboard.plans.filter((plan) => isExecutedPlan(plan)).length,
    },
    soil_trend: {
      zone_id: 'visualization',
      zone_name: '分区湿度',
      range: '7d',
      labels,
      soil_moisture: zoneHealth.map((item) => item.soil_moisture),
      threshold: zones.map((zone) => zone.soil_moisture_threshold || 40),
    },
    plan_funnel: {
      range: '7d',
      items: [
        { stage: 'generated', count: dashboard.plans.length },
        { stage: 'pending', count: dashboard.plans.filter((plan) => isPendingPlan(plan)).length },
        { stage: 'approved', count: dashboard.plans.filter((plan) => isApprovedPlan(plan)).length },
        { stage: 'executed', count: dashboard.plans.filter((plan) => isExecutedPlan(plan)).length },
        { stage: 'completed_or_rejected', count: dashboard.plans.filter((plan) => ['completed', 'rejected', 'superseded', 'cancelled'].includes(plan.status)).length },
      ],
    },
    alert_trend: {
      range: '7d',
      labels,
      series: {
        high: zoneHealth.map((item) => (item.deficit > 15 ? 1 : 0)),
        medium: zoneHealth.map((item) => (item.deficit > 5 && item.deficit <= 15 ? 1 : 0)),
        low: zoneHealth.map((item) => (item.deficit > 0 && item.deficit <= 5 ? 1 : 0)),
      },
    },
    zone_health: zoneHealth,
  }
}

function readMlPrediction(plan: IrrigationPlan): MlPredictionView | null {
  const evidence = readRecord(plan.evidence_summary)
  const rawPrediction = readRecord(evidence?.ml_prediction)
  if (!rawPrediction) return null

  const current = toNumber(rawPrediction.current_soil_moisture)
  const predicted = toNumber(rawPrediction.predicted_soil_moisture_24h)
  const sampleCount = toNumber(rawPrediction.sample_count)
  const confidenceValue = rawPrediction.confidence
  const confidence = typeof confidenceValue === 'string'
    ? confidenceValue
    : confidenceValue === null || confidenceValue === undefined
      ? '待校准'
      : String(confidenceValue)

  const rawSeries = Array.isArray(rawPrediction.forecast_series)
    ? rawPrediction.forecast_series
    : Array.isArray(rawPrediction.forecast_data)
      ? rawPrediction.forecast_data
      : []
  const points = rawSeries
    .map((item, index) => {
      const row = readRecord(item)
      const value = toNumber(row?.predicted_soil_moisture) ?? toNumber(row?.predicted_value) ?? toNumber(row?.soil_moisture) ?? toNumber(row?.value)
      if (value === null) return null
      return {
        label: typeof row?.timestamp === 'string' ? formatDateTime(row.timestamp) : `${index + 1}h`,
        value,
      }
    })
    .filter((item): item is MlForecastPoint => Boolean(item))

  if (points.length === 0 && current !== null && predicted !== null) {
    points.push({ label: '当前', value: current }, { label: '24h', value: predicted })
  }

  if (current === null && predicted === null && points.length === 0) return null

  return {
    current,
    predicted,
    confidence,
    sampleCount,
    planLabel: plan.zone_name || plan.zone_id || plan.plan_id,
    points,
  }
}

function readDecisionModel(plan: IrrigationPlan): DecisionModelView | null {
  const evidence = readRecord(plan.evidence_summary)
  const rawModel = readRecord(evidence?.decision_model)
  if (!rawModel) return null

  const actionValue = rawModel.recommended_action
  const action = typeof actionValue === 'string' && actionValue.trim() ? actionValue : '待校准'
  const duration = toNumber(rawModel.recommended_duration_minutes)
  const confidence = toNumber(rawModel.confidence)
  const sampleCount = toNumber(rawModel.sample_count)
  const topFactors = Array.isArray(rawModel.top_factors)
    ? rawModel.top_factors.map((item) => String(item)).filter(Boolean).slice(0, 3)
    : []

  return {
    action,
    duration,
    confidence,
    sampleCount,
    planLabel: plan.zone_name || plan.zone_id || plan.plan_id,
    topFactors,
  }
}

function findLatestMlPrediction(plans: IrrigationPlan[]): MlPredictionView | null {
  const sortedPlans = [...plans].sort((left, right) => {
    const leftTime = new Date(left.created_at || '').getTime() || 0
    const rightTime = new Date(right.created_at || '').getTime() || 0
    return rightTime - leftTime
  })
  for (const plan of sortedPlans) {
    const prediction = readMlPrediction(plan)
    if (prediction) return prediction
  }
  return null
}

function findLatestDecisionModel(plans: IrrigationPlan[]): DecisionModelView | null {
  const sortedPlans = [...plans].sort((left, right) => {
    const leftTime = new Date(left.created_at || '').getTime() || 0
    const rightTime = new Date(right.created_at || '').getTime() || 0
    return rightTime - leftTime
  })
  for (const plan of sortedPlans) {
    const decisionModel = readDecisionModel(plan)
    if (decisionModel) return decisionModel
  }
  return null
}

function buildKpis(dashboard: DashboardData, overview: AnalyticsOverview, history: HistoryData): KpiItem[] {
  const runningActuatorCount = dashboard.zones.reduce(
    (total, zone) => total + zone.actuators.filter((actuator) => actuator.status === 'running').length,
    0,
  )
  const lastLog = history.logs[0]
  const averageSoil = dashboard.sensors?.average.soil_moisture ?? null

  return [
    {
      label: '核心状态',
      value: dashboard.backendReachable ? 'ONLINE' : 'OFFLINE',
      detail: dashboard.status?.version || 'HydroAgent',
      icon: RadioTower,
      tone: dashboard.backendReachable ? 'ok' : 'danger',
    },
    {
      label: '平均湿度',
      value: formatNumber(averageSoil, '%'),
      detail: dashboard.weather?.city || '未知城市',
      icon: Droplets,
      tone: averageSoil !== null && averageSoil < 35 ? 'warn' : 'ok',
    },
    {
      label: '待审批',
      value: String(overview.kpis.pending_plan_count),
      detail: `${dashboard.plans.length} 个计划`,
      icon: GitBranch,
      tone: overview.kpis.pending_plan_count > 0 ? 'warn' : 'ok',
    },
    {
      label: '运行执行器',
      value: String(runningActuatorCount),
      detail: `${dashboard.zones.length} 个分区`,
      icon: Gauge,
      tone: runningActuatorCount > 0 ? 'warn' : 'muted',
    },
    {
      label: '活跃告警',
      value: String(overview.kpis.active_alert_count),
      detail: `最近 ${formatDateTime(lastLog?.created_at)}`,
      icon: AlertTriangle,
      tone: overview.kpis.active_alert_count > 0 ? 'danger' : 'ok',
    },
  ]
}

function chartTextStyle() {
  return { color: 'rgba(220, 252, 231, 0.74)', fontSize: 11 }
}

function chartAxisLine() {
  return { lineStyle: { color: 'rgba(148, 163, 184, 0.22)' } }
}

export function VisualizationConsole({
  dashboard,
  overview,
  history,
}: {
  dashboard: DashboardData
  overview: AnalyticsOverview | null
  history: HistoryData
}) {
  const dataOverview = overview || buildFallbackOverview(dashboard)
  const planPool = [...history.plans, ...dashboard.plans]
  const mlPrediction = findLatestMlPrediction(planPool)
  const decisionModel = findLatestDecisionModel(planPool)
  const kpis = buildKpis(dashboard, dataOverview, history)
  const lastUpdated = formatDateTime(dashboard.status?.timestamp || dashboard.sensors?.timestamp)

  const sharedGrid = { left: 42, right: 18, top: 42, bottom: 36 }
  const moistureOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { top: 4, textStyle: chartTextStyle(), data: ['湿度', '阈值'] },
    grid: sharedGrid,
    xAxis: { type: 'category', data: dataOverview.soil_trend.labels, axisLabel: chartTextStyle(), axisLine: chartAxisLine() },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: chartTextStyle(), splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.12)' } } },
    series: [
      { name: '湿度', type: 'line', smooth: true, symbolSize: 6, data: dataOverview.soil_trend.soil_moisture, lineStyle: { width: 3, color: '#34d399' }, itemStyle: { color: '#34d399' }, areaStyle: { color: 'rgba(52, 211, 153, 0.14)' } },
      { name: '阈值', type: 'line', smooth: true, symbol: 'none', data: dataOverview.soil_trend.threshold, lineStyle: { width: 2, type: 'dashed', color: '#f59e0b' } },
    ],
  }

  const funnelOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item' },
    grid: sharedGrid,
    xAxis: { type: 'category', data: dataOverview.plan_funnel.items.map((item) => item.stage), axisLabel: chartTextStyle(), axisLine: chartAxisLine() },
    yAxis: { type: 'value', axisLabel: chartTextStyle(), splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.12)' } } },
    series: [
      {
        type: 'bar',
        data: dataOverview.plan_funnel.items.map((item) => item.count),
        barWidth: 18,
        itemStyle: { color: '#14b8a6', borderRadius: 4 },
      },
    ],
  }

  const alertOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { top: 4, textStyle: chartTextStyle(), data: ['high', 'medium', 'low'] },
    grid: sharedGrid,
    xAxis: { type: 'category', data: dataOverview.alert_trend.labels, axisLabel: chartTextStyle(), axisLine: chartAxisLine() },
    yAxis: { type: 'value', axisLabel: chartTextStyle(), splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.12)' } } },
    series: [
      { name: 'high', type: 'line', smooth: true, data: dataOverview.alert_trend.series.high || [], lineStyle: { color: '#f97316', width: 3 }, itemStyle: { color: '#f97316' } },
      { name: 'medium', type: 'line', smooth: true, data: dataOverview.alert_trend.series.medium || [], lineStyle: { color: '#facc15', width: 2 }, itemStyle: { color: '#facc15' } },
      { name: 'low', type: 'line', smooth: true, data: dataOverview.alert_trend.series.low || [], lineStyle: { color: '#22c55e', width: 2 }, itemStyle: { color: '#22c55e' } },
    ],
  }

  const heatmapMax = Math.max(100, ...dataOverview.zone_health.map((item) => Math.max(item.soil_moisture, item.deficit, item.alert_count)))
  const heatmapOption = {
    backgroundColor: 'transparent',
    tooltip: {},
    grid: { left: 82, right: 20, top: 28, bottom: 56 },
    xAxis: { type: 'category', data: ['湿度', '缺口', '告警'], axisLabel: chartTextStyle(), axisLine: chartAxisLine() },
    yAxis: { type: 'category', data: dataOverview.zone_health.map((item) => item.zone_name), axisLabel: chartTextStyle(), axisLine: chartAxisLine() },
    visualMap: {
      min: 0,
      max: heatmapMax,
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 4,
      textStyle: chartTextStyle(),
      inRange: { color: ['#05251f', '#0f766e', '#34d399'] },
    },
    series: [
      {
        type: 'heatmap',
        data: dataOverview.zone_health.flatMap((item, index) => [
          [0, index, item.soil_moisture],
          [1, index, item.deficit],
          [2, index, item.alert_count],
        ]),
        label: { show: true, color: '#ecfdf5' },
      },
    ],
  }

  const mlOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    grid: sharedGrid,
    xAxis: { type: 'category', data: mlPrediction?.points.map((item) => item.label) || [], axisLabel: chartTextStyle(), axisLine: chartAxisLine() },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: chartTextStyle(), splitLine: { lineStyle: { color: 'rgba(148, 163, 184, 0.12)' } } },
    series: [
      {
        name: '预测湿度',
        type: 'line',
        smooth: true,
        data: mlPrediction?.points.map((item) => item.value) || [],
        lineStyle: { width: 3, color: '#2dd4bf' },
        itemStyle: { color: '#2dd4bf' },
        areaStyle: { color: 'rgba(45, 212, 191, 0.16)' },
      },
    ],
  }

  return (
    <div className="visualization-screen">
      <section className="visualization-hero">
        <div>
          <p className="eyebrow">Visualization</p>
          <h2>数据大屏</h2>
          <span>更新时间 {lastUpdated}</span>
        </div>
        <div className="visualization-hero-status">
          <Waves size={18} />
          <strong>{dashboard.irrigation?.status || 'standby'}</strong>
        </div>
      </section>

      <section className="visualization-kpis">
        {kpis.map((item) => {
          const Icon = item.icon
          return (
            <div key={item.label} className={`visualization-kpi visualization-kpi-${item.tone}`}>
              <Icon size={18} />
              <span>{item.label}</span>
              <strong>{item.value}</strong>
              <p>{item.detail}</p>
            </div>
          )
        })}
      </section>

      <section className="visualization-grid">
        <div className="visualization-panel visualization-panel-wide">
          <div className="visualization-panel-heading">
            <span>Moisture</span>
            <strong>湿度趋势</strong>
          </div>
          <ReactECharts option={moistureOption} style={{ height: 320 }} />
        </div>

        <div className="visualization-panel">
          <div className="visualization-panel-heading">
            <span>Prediction</span>
            <strong>ML 预测</strong>
          </div>
          {mlPrediction ? (
            <>
              <div className="visualization-ml-strip">
                <div>
                  <span>当前</span>
                  <strong>{formatNumber(mlPrediction.current, '%')}</strong>
                </div>
                <div>
                  <span>24h</span>
                  <strong>{formatNumber(mlPrediction.predicted, '%')}</strong>
                </div>
                <div>
                  <span>置信度</span>
                  <strong>{mlPrediction.confidence}</strong>
                </div>
                <div>
                  <span>样本</span>
                  <strong>{formatNumber(mlPrediction.sampleCount)}</strong>
                </div>
              </div>
              <p className="visualization-note">{mlPrediction.planLabel}</p>
              <ReactECharts option={mlOption} style={{ height: 240 }} />
            </>
          ) : (
            <div className="visualization-empty">
              <strong>等待模型预测数据</strong>
              <p>暂无 ml_prediction，当前以运营数据为准。</p>
            </div>
          )}
          <div className="visualization-decision">
            <div className="visualization-panel-heading">
              <span>Decision</span>
              <strong>决策模型建议</strong>
            </div>
            {decisionModel ? (
              <>
                <div className="visualization-ml-strip visualization-decision-strip">
                  <div>
                    <span>动作</span>
                    <strong>{decisionModel.action}</strong>
                  </div>
                  <div>
                    <span>时长</span>
                    <strong>{formatNumber(decisionModel.duration, ' 分钟')}</strong>
                  </div>
                  <div>
                    <span>置信度</span>
                    <strong>{formatNumber(decisionModel.confidence)}</strong>
                  </div>
                  <div>
                    <span>样本</span>
                    <strong>{formatNumber(decisionModel.sampleCount)}</strong>
                  </div>
                </div>
                <p className="visualization-note">{decisionModel.planLabel}</p>
                <div className="visualization-factor-list">
                  {(decisionModel.topFactors.length ? decisionModel.topFactors : ['等待关键因子']).map((factor) => (
                    <span key={factor}>{factor}</span>
                  ))}
                </div>
              </>
            ) : (
              <p className="visualization-note">暂无 decision_model，等待历史计划样本。</p>
            )}
          </div>
        </div>

        <div className="visualization-panel">
          <div className="visualization-panel-heading">
            <span>Plan</span>
            <strong>计划漏斗</strong>
          </div>
          <ReactECharts option={funnelOption} style={{ height: 280 }} />
        </div>

        <div className="visualization-panel">
          <div className="visualization-panel-heading">
            <span>Alert</span>
            <strong>告警趋势</strong>
          </div>
          <ReactECharts option={alertOption} style={{ height: 280 }} />
        </div>

        <div className="visualization-panel visualization-panel-wide">
          <div className="visualization-panel-heading">
            <span>Zone</span>
            <strong>分区健康热力</strong>
          </div>
          <ReactECharts option={heatmapOption} style={{ height: 320 }} />
        </div>
      </section>
    </div>
  )
}
