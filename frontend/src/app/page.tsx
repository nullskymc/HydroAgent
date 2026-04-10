import { AppShell } from '@/components/app-shell'
import { AnalyticsOverviewPanel } from '@/components/analytics-overview'
import { ConsoleEmptyState, ConsoleSectionHeader } from '@/components/console-primitives'
import { DashboardChatLauncher } from '@/components/dashboard-chat-launcher'
import { Badge, StatusDot } from '@/components/ui/badge'
import { requirePermission } from '@/lib/auth'
import { getDashboardData, getSettingsData } from '@/lib/server-data'
import { AnalyticsOverview, DecisionLog, IrrigationPlan, Zone } from '@/lib/types'
import { formatDateTime, formatNumber } from '@/lib/utils'

type Tone = 'default' | 'success' | 'warning' | 'danger'

type ZoneView = {
  zone: Zone
  soilMoisture: number
  threshold: number
  deficit: number
  latestPlan?: IrrigationPlan
  actuator?: Zone['actuators'][number]
}

function isPendingPlan(plan?: IrrigationPlan | null) {
  return plan?.status === 'pending_approval'
}

function isApprovedPlan(plan?: IrrigationPlan | null) {
  return plan?.status === 'approved'
}

function isExecutedPlan(plan?: IrrigationPlan | null) {
  return plan?.status === 'executing' || plan?.status === 'completed'
}

function getRiskTone(value?: string | null): Tone {
  if (value === 'high') return 'danger'
  if (value === 'medium') return 'warning'
  if (value === 'low') return 'success'
  return 'default'
}

function getStateTone(value?: string | null): Tone {
  if (value === 'running') return 'warning'
  if (value === 'idle') return 'success'
  return 'default'
}

// 将传感器快照和分区配置对齐，避免渲染层重复处理业务拼装。
function findZoneReading(zoneId: string, sensorRows: Array<Record<string, unknown>>) {
  return sensorRows.find((row) => String(row.zone_id || '') === zoneId)
}

function summarizeDecision(decision: DecisionLog) {
  const result = decision.decision_result || {}
  const subagent = typeof result.subagent === 'string' ? result.subagent : null
  const status = typeof result.status === 'string' ? result.status : null
  if (subagent && status) {
    return `${subagent} · ${status}`
  }
  return decision.reasoning_chain || JSON.stringify(result)
}

// 将表格需要的分区视图模型统一在这里生成，保持页面结构和数据逻辑解耦。
function buildZoneView(zone: Zone, sensorRows: Array<Record<string, unknown>>, plans: IrrigationPlan[]): ZoneView {
  const reading = findZoneReading(zone.zone_id, sensorRows)
  const soilMoisture = Number(reading?.soil_moisture || 0)
  const threshold = zone.soil_moisture_threshold || 40
  const deficit = Math.max(0, threshold - soilMoisture)
  const latestPlan = plans.find((plan) => plan.zone_id === zone.zone_id)
  const actuator = zone.actuators[0]

  return {
    zone,
    soilMoisture,
    threshold,
    deficit,
    latestPlan,
    actuator,
  }
}

function buildOverviewFromDashboard(
  zoneRows: ZoneView[],
  dashboard: Awaited<ReturnType<typeof getDashboardData>>,
): AnalyticsOverview {
  const labels = zoneRows.map((item) => item.zone.name)
  const alertTrendSeed = zoneRows.reduce<Record<string, number[]>>(
    (accumulator, item) => {
      accumulator.high.push(item.latestPlan?.risk_level === 'high' ? 1 : 0)
      accumulator.medium.push(item.latestPlan?.risk_level === 'medium' ? 1 : 0)
      accumulator.low.push(item.latestPlan?.risk_level === 'low' ? 1 : 0)
      return accumulator
    },
    { high: [], medium: [], low: [] },
  )

  return {
    range: '7d',
    kpis: {
      zone_count: dashboard.zones.length,
      pending_plan_count: dashboard.plans.filter((plan) => isPendingPlan(plan)).length,
      active_alert_count: zoneRows.filter((item) => item.latestPlan?.risk_level === 'high' || item.deficit > 5).length,
      executed_plan_count: dashboard.plans.filter((plan) => isExecutedPlan(plan)).length,
    },
    soil_trend: {
      zone_id: 'dashboard',
      zone_name: '分区湿度概览',
      range: '7d',
      labels,
      soil_moisture: zoneRows.map((item) => Number(item.soilMoisture.toFixed(2))),
      threshold: zoneRows.map((item) => Number(item.threshold.toFixed(2))),
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
      series: alertTrendSeed,
    },
    zone_health: zoneRows.map((item) => ({
      zone_id: item.zone.zone_id,
      zone_name: item.zone.name,
      soil_moisture: Number(item.soilMoisture.toFixed(2)),
      deficit: Number(item.deficit.toFixed(2)),
      actuator_status: item.actuator?.status || 'unknown',
      alert_count: item.latestPlan?.risk_level === 'high' || item.deficit > 5 ? 1 : 0,
    })),
  }
}

export default async function DashboardPage() {
  await requirePermission('dashboard:view')
  const [dashboard, settings] = await Promise.all([
    getDashboardData(),
    getSettingsData().catch(() => null),
  ])
  const sensorRows = (dashboard.sensors?.sensors || []) as Array<Record<string, unknown>>
  const forecastRows = dashboard.weather?.forecast || []
  const pendingPlans = dashboard.plans.filter((item) => isPendingPlan(item))
  const zoneRows = dashboard.zones.map((zone) => buildZoneView(zone, sensorRows, dashboard.plans))
  const running = dashboard.irrigation?.status === 'running'
  const backendOnline = dashboard.backendReachable
  const currentMode = running ? '运行中' : '待命'
  const averageSoil = dashboard.sensors?.average.soil_moisture ?? null
  const rainfall = dashboard.sensors?.average.rainfall ?? null
  const attentionCount = zoneRows.filter((zone) => zone.deficit > 5 || isPendingPlan(zone.latestPlan)).length
  const overview = buildOverviewFromDashboard(zoneRows, dashboard)
  const lastUpdated = formatDateTime(dashboard.status?.timestamp || dashboard.sensors?.timestamp)

  const telemetryItems = [
    {
      label: '运行总览',
      value: (
        <>
          <StatusDot tone={backendOnline ? 'success' : 'danger'} />
          {backendOnline ? 'Core Online' : 'Core Offline'}
        </>
      ),
    },
    { label: '模式', value: currentMode },
    { label: '平均湿度', value: formatNumber(averageSoil, '%') },
    { label: '待审批', value: String(pendingPlans.length) },
    { label: '注意分区', value: String(attentionCount) },
    { label: '天气', value: `${dashboard.weather?.live.weather || '--'} (${formatNumber(rainfall, 'mm')})` },
  ]

  return (
    <AppShell currentPath="/">
      <div className="page-stack console-dashboard">
        <section className="console-telemetry-bar">
          <div className="console-telemetry-title">
            <p className="eyebrow">运行总览</p>
            <h2>灌溉中枢</h2>
          </div>
          <div className="console-telemetry-stream">
            {telemetryItems.map((item) => (
              <div key={item.label} className="console-telemetry-item">
                <span>{item.label}</span>
                <strong>{item.value}</strong>
              </div>
            ))}
          </div>
          <div className="console-telemetry-meta">
            <span>城市 {dashboard.weather?.city || '--'}</span>
            <strong>更新时间 {lastUpdated}</strong>
          </div>
        </section>

        <div className="console-stage">
          <div className="console-main">
            <section className="console-section">
              <ConsoleSectionHeader
                eyebrow="分区"
                title="分区状态"
                meta={<span className="console-plain-meta">{dashboard.zones.length} 个分区</span>}
              />
              <div className="console-table">
                <div className="console-table-head">
                  <span>分区名称</span>
                  <span>湿度</span>
                  <span>阈值</span>
                  <span>缺口</span>
                  <span>执行器</span>
                </div>
                {zoneRows.length === 0 ? (
                  <ConsoleEmptyState title="暂无分区数据" detail="核心未返回分区与传感器信息，表格保持只读占位。" />
                ) : null}
                {zoneRows.map((item) => (
                  <div key={item.zone.zone_id} className="console-table-row">
                    <div className="console-zone-cell">
                      <strong>{item.zone.name}</strong>
                      <p>{item.zone.location}</p>
                      <em>计划 {item.latestPlan?.status || '无计划'}</em>
                    </div>
                    <span>{formatNumber(item.soilMoisture, '%')}</span>
                    <span>{item.threshold}%</span>
                    <span>{formatNumber(item.deficit, '%')}</span>
                    <div className="console-actuator-cell">
                      <Badge tone={getStateTone(item.actuator?.status)}>{item.actuator?.status || 'unknown'}</Badge>
                      <p>{item.actuator?.name || '未绑定执行器'}</p>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="console-section">
              <div className="console-support-grid">
                <div className="console-support-panel">
                  <ConsoleSectionHeader eyebrow="天气" title="天气窗口" />
                  <div className="console-feed">
                    {forecastRows.length === 0 ? (
                      <ConsoleEmptyState title="暂无预报" detail="天气服务未返回未来窗口，自动灌溉将保持谨慎。" />
                    ) : null}
                    {forecastRows.slice(0, 4).map((forecast) => (
                      <div key={forecast.date} className="console-feed-row">
                        <div>
                          <strong>{forecast.date}</strong>
                          <p>{forecast.day_weather}</p>
                        </div>
                        <span>
                          {forecast.day_temp}° / {forecast.night_temp}°
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="console-support-panel">
                  <ConsoleSectionHeader eyebrow="系统" title="系统状态" />
                  <div className="console-stat-grid">
                    <div className="console-stat-card">
                      <span>核心状态</span>
                      <strong>{backendOnline ? '已连通' : '离线'}</strong>
                    </div>
                    <div className="console-stat-card">
                      <span>采集周期</span>
                      <strong>{settings?.collection_interval_minutes || '--'} 分钟</strong>
                    </div>
                    <div className="console-stat-card">
                      <span>节点数量</span>
                      <strong>{sensorRows.length}</strong>
                    </div>
                    <div className="console-stat-card">
                      <span>当前模型</span>
                      <strong>{settings?.model_name || dashboard.status?.version || '--'}</strong>
                    </div>
                  </div>
                </div>
              </div>
            </section>

            {overview ? (
              <section className="console-section">
                <ConsoleSectionHeader eyebrow="分析" title="运营图表" meta={<span className="console-plain-meta">7 天窗口</span>} />
                <AnalyticsOverviewPanel overview={overview} />
              </section>
            ) : null}
          </div>

          <aside className="console-sidebar">
            <DashboardChatLauncher />

            <section className="console-section">
              <ConsoleSectionHeader
                eyebrow="审批"
                title="待处理计划"
                meta={<span className="console-plain-meta">高优待办</span>}
              />
              <div className="console-feed">
                {pendingPlans.length === 0 ? (
                  <ConsoleEmptyState title="当前没有待审批计划" detail="计划队列为空，审批侧栏保持清空状态。" />
                ) : null}
                {pendingPlans.map((plan) => (
                  <div key={plan.plan_id} className="console-feed-row console-feed-row-stack">
                    <div>
                      <strong>{plan.zone_name || plan.zone_id}</strong>
                      <p>{plan.plan_id}</p>
                    </div>
                    <div className="console-feed-tags">
                      <Badge tone={getRiskTone(plan.risk_level)}>{plan.risk_level}</Badge>
                      <Badge>{plan.proposed_action}</Badge>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            <section className="console-section">
              <ConsoleSectionHeader eyebrow="审计" title="最近决策" />
              <div className="console-feed">
                {dashboard.decisions.length === 0 ? (
                  <ConsoleEmptyState title="暂无决策日志" detail="智能体还没有生成新的决策记录。" />
                ) : null}
                {dashboard.decisions.map((decision) => (
                  <div key={decision.decision_id} className="console-feed-row console-feed-row-tall">
                    <div>
                      <strong>{summarizeDecision(decision)}</strong>
                      <p>{decision.reflection_notes || decision.trigger}</p>
                    </div>
                    <span>{formatDateTime(decision.created_at)}</span>
                  </div>
                ))}
              </div>
            </section>

            <section className="console-section">
              <ConsoleSectionHeader eyebrow="系统" title="系统信息" />
              <div className="console-info-grid">
                <div className="console-info-row">
                  <span>系统模型</span>
                  <strong>{settings?.model_name || dashboard.status?.version || '--'}</strong>
                </div>
                <div className="console-info-row">
                  <span>节点数量</span>
                  <strong>{sensorRows.length}</strong>
                </div>
                <div className="console-info-row">
                  <span>告警阈值</span>
                  <strong>{settings?.alarm_threshold || '--'}</strong>
                </div>
                <div className="console-info-row">
                  <span>默认阈值</span>
                  <strong>{settings?.soil_moisture_threshold || '--'}%</strong>
                </div>
              </div>
              <div className="console-feature-strip">
                {(dashboard.status?.features || []).length === 0 ? (
                  <span className="console-feature-tag console-feature-tag-muted">暂无系统特性数据</span>
                ) : null}
                {(dashboard.status?.features || []).map((feature) => (
                  <span key={feature} className="console-feature-tag">
                    {feature}
                  </span>
                ))}
              </div>
            </section>
          </aside>
        </div>
      </div>
    </AppShell>
  )
}
