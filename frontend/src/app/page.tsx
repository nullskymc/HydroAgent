import { AppShell } from '@/components/app-shell'
import { DashboardActions } from '@/components/dashboard-actions'
import { SectionHeader } from '@/components/section-header'
import { Badge, StatusDot } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { getDashboardData, getSettingsData } from '@/lib/server-data'
import { formatDateTime, formatNumber } from '@/lib/utils'

type SummaryTone = 'success' | 'danger'

function clampPercent(value: number, max: number) {
  return Math.max(0, Math.min(100, (value / max) * 100))
}

export default async function DashboardPage() {
  const [dashboard, settings] = await Promise.all([getDashboardData(), getSettingsData().catch(() => null)])
  const sensorRows = (dashboard.sensors?.sensors || []) as Array<Record<string, unknown>>
  const forecastRows = dashboard.weather?.forecast || []
  const soilMoisture = dashboard.sensors?.average.soil_moisture || 0
  const temperature = dashboard.sensors?.average.temperature || 0
  const lightIntensity = dashboard.sensors?.average.light_intensity || 0
  const rainfall = dashboard.sensors?.average.rainfall || 0
  const primaryMetrics = [
    { title: '土壤湿度', value: formatNumber(soilMoisture, '%'), width: clampPercent(soilMoisture, 100) },
    { title: '环境温度', value: formatNumber(temperature, '°C'), width: clampPercent(temperature, 40) },
    { title: '光照强度', value: formatNumber(lightIntensity, ' lux'), width: clampPercent(lightIntensity, 1000) },
    { title: '降雨量', value: formatNumber(rainfall, ' mm'), width: clampPercent(rainfall, 5) },
  ]
  const currentMode = dashboard.irrigation?.status === 'running' ? '运行中' : '待命监测'
  const summaryItems: Array<{ label: string; value: string; tone?: SummaryTone }> = [
    { label: '系统状态', value: dashboard.backendReachable ? '在线' : '离线', tone: dashboard.backendReachable ? 'success' : 'danger' },
    { label: '灌溉模式', value: currentMode },
    { label: '天气', value: dashboard.weather?.live.weather || '--' },
    { label: '策略记录', value: `${dashboard.decisions.length} 条` },
    { label: '更新时间', value: formatDateTime(dashboard.status?.timestamp || dashboard.sensors?.timestamp) },
  ]
  const systemOverview = [
    ['Agent 就绪', dashboard.status?.agent_initialized ? '已就绪' : '未就绪'],
    ['模型', settings?.model_name || dashboard.status?.version || '--'],
    ['采集周期', `${settings?.collection_interval_minutes || '--'} 分钟`],
    ['报警阈值', `${settings?.alarm_threshold || '--'}%`],
    ['湿度阈值', `${settings?.soil_moisture_threshold || '--'}%`],
    ['城市', dashboard.weather?.city || '--'],
  ]

  return (
    <AppShell currentPath="/">
      <div className="page-stack">
        <div className="dashboard-headline">
          <div>
            <p className="eyebrow">智能体中枢</p>
            <h2>实时运行态</h2>
            <p className="page-description">围绕灌溉状态、环境数据和执行动作构建的高密度运行工作台。</p>
          </div>
          <div className="dashboard-headline-meta">
            <Badge tone={dashboard.backendReachable ? 'success' : 'danger'}>
              <StatusDot tone={dashboard.backendReachable ? 'success' : 'danger'} />
              {dashboard.backendReachable ? 'Core Online' : 'Core Offline'}
            </Badge>
            <Badge>更新时间 {formatDateTime(dashboard.status?.timestamp || dashboard.sensors?.timestamp)}</Badge>
          </div>
        </div>

        <div className="summary-strip">
          {summaryItems.map((item) => (
            <div key={item.label} className="summary-cell">
              <span className="summary-label">{item.label}</span>
              <div className="summary-value-row">
                {item.tone ? (
                  <Badge tone={item.tone}>
                    <StatusDot tone={item.tone} />
                    {item.value}
                  </Badge>
                ) : (
                  <strong className="summary-value">{item.value}</strong>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="management-grid">
          <Card className="control-panel-card">
            <CardHeader>
              <div>
                <p className="eyebrow">管理控制</p>
                <CardTitle>灌溉执行台</CardTitle>
                <CardDescription>把执行状态、可操作动作和策略边界放在同一个决策面板中。</CardDescription>
              </div>
            </CardHeader>
            <CardContent className="control-panel-content">
              <div className="control-primary">
                <div className="control-state-block">
                  <span className="hero-value-label">当前模式</span>
                  <strong className="control-state-value">{currentMode}</strong>
                  <p className="inline-muted">系统根据实时传感器、阈值和天气信息决定是否进入主动灌溉。</p>
                </div>
                <div className="control-action-block">
                  <DashboardActions running={dashboard.irrigation?.status === 'running'} defaultDuration={settings?.default_duration_minutes || 30} />
                  <div className="hero-action-note">
                    <Badge tone={settings?.alarm_enabled ? 'success' : 'default'}>告警 {settings?.alarm_enabled ? '启用' : '关闭'}</Badge>
                    <Badge>默认 {settings?.default_duration_minutes || '--'} 分钟</Badge>
                  </div>
                </div>
              </div>
              <div className="control-detail-grid">
                <div className="control-detail-card">
                  <span className="summary-label">执行信息</span>
                  <dl className="ops-detail-list">
                    <div>
                      <dt>剩余时长</dt>
                      <dd>{formatNumber(dashboard.irrigation?.remaining_minutes, ' 分钟')}</dd>
                    </div>
                    <div>
                      <dt>计划时长</dt>
                      <dd>{formatNumber(dashboard.irrigation?.duration_minutes, ' 分钟')}</dd>
                    </div>
                    <div>
                      <dt>启动时间</dt>
                      <dd>{dashboard.irrigation?.start_time ? formatDateTime(dashboard.irrigation.start_time) : '--'}</dd>
                    </div>
                  </dl>
                </div>
                <div className="control-detail-card">
                  <span className="summary-label">系统约束</span>
                  <dl className="ops-detail-list">
                    <div>
                      <dt>湿度阈值</dt>
                      <dd>{settings?.soil_moisture_threshold || '--'}%</dd>
                    </div>
                    <div>
                      <dt>报警阈值</dt>
                      <dd>{settings?.alarm_threshold || '--'}%</dd>
                    </div>
                    <div>
                      <dt>数据源</dt>
                      <dd>{settings?.db_type || '--'}</dd>
                    </div>
                  </dl>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>环境监测概览</CardTitle>
              <CardDescription>用统一刻度查看当前环境状态，而不是把单个指标拆成独立展示卡。</CardDescription>
            </CardHeader>
            <CardContent className="management-metric-list">
              {primaryMetrics.map((metric) => (
                <div key={metric.title} className="management-metric-row">
                  <div className="management-metric-copy">
                    <span>{metric.title}</span>
                    <strong>{metric.value}</strong>
                  </div>
                  <div className="metric-bar"><span style={{ width: `${metric.width}%` }} /></div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>

        <div className="board-grid">
          <Card className="board-card">
            <CardHeader>
              <CardTitle>系统概览</CardTitle>
            </CardHeader>
            <CardContent className="meta-list">
              {systemOverview.map(([label, value]) => (
                <div key={label} className="meta-row">
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card className="board-card">
            <CardHeader>
              <CardTitle>天气与外部条件</CardTitle>
            </CardHeader>
            <CardContent className="meta-list">
              <div className="meta-row">
                <span>实况天气</span>
                <strong>{dashboard.weather?.live.weather || '--'}</strong>
              </div>
              <div className="meta-row">
                <span>实时温度</span>
                <strong>{dashboard.weather?.live.temperature || '--'}°C</strong>
              </div>
              <div className="meta-row">
                <span>风向</span>
                <strong>{dashboard.weather?.live.wind_direction || '--'}</strong>
              </div>
              <div className="meta-row">
                <span>风力</span>
                <strong>{dashboard.weather?.live.wind_power || '--'}</strong>
              </div>
            </CardContent>
          </Card>

          <Card className="board-card">
            <CardHeader>
              <CardTitle>节点状态</CardTitle>
            </CardHeader>
            <CardContent className="meta-list">
              <div className="meta-row">
                <span>节点数量</span>
                <strong>{sensorRows.length}</strong>
              </div>
              <div className="meta-row">
                <span>采样时间</span>
                <strong>{dashboard.sensors?.timestamp ? formatDateTime(dashboard.sensors.timestamp) : '--'}</strong>
              </div>
              <div className="meta-row">
                <span>异常提示</span>
                <strong>{dashboard.error || '无'}</strong>
              </div>
            </CardContent>
          </Card>

          <Card className="board-card">
            <CardHeader>
              <CardTitle>系统能力</CardTitle>
            </CardHeader>
            <CardContent className="tag-list">
              {(dashboard.status?.features || []).length ? (
                (dashboard.status?.features || []).map((feature) => (
                  <span key={feature} className="tag">
                    {feature}
                  </span>
                ))
              ) : (
                <p className="inline-muted">暂无能力标记</p>
              )}
            </CardContent>
          </Card>
        </div>

        <SectionHeader
          title="运行数据"
          description="传感器、天气、能力与决策"
        />

        <div className="board-grid board-grid-operations">
          <Card className="board-card board-card-wide">
            <CardHeader>
              <CardTitle>传感器节点明细</CardTitle>
              <CardDescription>直接面向管理者展示节点状态，而不是把节点信息埋在装饰卡片里。</CardDescription>
            </CardHeader>
            <CardContent className="table-card sensor-list">
              {sensorRows.length === 0 ? <p className="inline-muted">暂无节点数据</p> : null}
              {sensorRows.map((sensor, index) => {
                const sensorId = String(sensor.sensor_id || `sensor_${index + 1}`)
                const rowKey = `${sensorId}-${index}`

                return (
                <div key={rowKey} className="table-row sensor-row">
                  <strong>{sensorId}</strong>
                  <span>湿度 {formatNumber(Number(sensor.soil_moisture || 0), '%')}</span>
                  <span>温度 {formatNumber(Number(sensor.temperature || 0), '°C')}</span>
                  <span>光照 {formatNumber(Number(sensor.light_intensity || 0), ' lux')}</span>
                </div>
                )
              })}
            </CardContent>
          </Card>

          <Card className="board-card">
            <CardHeader>
              <CardTitle>天气预报</CardTitle>
              <CardDescription>未来 4 个时段</CardDescription>
            </CardHeader>
            <CardContent className="table-card forecast-list">
              {forecastRows.length === 0 ? <p className="inline-muted">暂无天气预报</p> : null}
              {forecastRows.map((forecast) => (
                <div key={forecast.date} className="table-row forecast-row">
                  <strong>{forecast.date}</strong>
                  <span>{forecast.day_weather}</span>
                  <span>{forecast.day_temp}° / {forecast.night_temp}°</span>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card className="board-card">
            <CardHeader>
              <CardTitle>最近决策</CardTitle>
              <CardDescription>面向管理者保留触发原因、输出摘要和时间点。</CardDescription>
            </CardHeader>
            <CardContent className="table-card decision-feed">
            {dashboard.decisions.length === 0 ? (
              <p className="inline-muted">暂无决策日志</p>
            ) : (
              dashboard.decisions.map((item) => (
                <div key={item.decision_id} className="table-row">
                  <strong>{item.trigger}</strong>
                  <p>{item.decision_result ? JSON.stringify(item.decision_result) : '无结果摘要'}</p>
                  <time>{formatDateTime(item.created_at)}</time>
                </div>
              ))
            )}
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  )
}
