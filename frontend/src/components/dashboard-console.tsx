'use client'

import ReactECharts from 'echarts-for-react'
import { useQuery } from '@tanstack/react-query'
import { motion, type Variants } from 'framer-motion'
import { CloudRain, Droplets, Power, Sun, Thermometer } from 'lucide-react'
import { DashboardChatLauncher } from '@/components/dashboard-chat-launcher'
import { Badge, StatusDot } from '@/components/ui/badge'
import { EmptyState } from '@/components/ui/empty-state'
import { SectionBadge } from '@/components/ui/section-badge'
import { apiGet } from '@/lib/api-client'
import { labelFor } from '@/lib/labels'
import { DashboardData, RuntimeSettings, Zone } from '@/lib/types'
import { formatNumber1, formatPercent1, toNumber } from '@/lib/format'
import { formatDateTime } from '@/lib/utils'

type ZoneView = {
  zone: Zone
  soilMoisture: number
  threshold: number
  deficit: number
  actuator?: Zone['actuators'][number]
}

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.07,
      delayChildren: 0.05,
    },
  },
}

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0, transition: { duration: 0.42, ease: 'easeOut' } },
}

function getSensorRows(dashboard: DashboardData) {
  return (dashboard.sensors?.sensors || []) as Array<Record<string, unknown>>
}

function toneForState(value?: string | null): 'default' | 'success' | 'warning' | 'danger' {
  if (value === 'running' || value === 'executing') return 'warning'
  if (value === 'idle' || value === 'ready' || value === 'completed') return 'success'
  if (value === 'unknown' || value === 'error') return 'danger'
  return 'default'
}

function buildZoneRows(dashboard: DashboardData): ZoneView[] {
  const sensorRows = getSensorRows(dashboard)
  return dashboard.zones.map((zone) => {
    const reading = sensorRows.find((row) => String(row.zone_id || '') === zone.zone_id)
    const soilMoisture = toNumber(reading?.soil_moisture)
    const threshold = toNumber(zone.soil_moisture_threshold, 40)
    return {
      zone,
      soilMoisture,
      threshold,
      deficit: Math.max(0, threshold - soilMoisture),
      actuator: zone.actuators[0],
    }
  })
}

function buildMoistureOption(zoneRows: ZoneView[]) {
  return {
    backgroundColor: 'transparent',
    color: ['#0052FF', '#94A3B8'],
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value: number) => formatPercent1(Number(value)),
      borderColor: '#E2E8F0',
      backgroundColor: 'rgba(255,255,255,0.96)',
      textStyle: { color: '#0F172A' },
    },
    legend: {
      top: 0,
      right: 4,
      textStyle: { color: '#64748B' },
      data: ['土壤湿度', '阈值'],
    },
    grid: { left: 32, right: 12, top: 28, bottom: 24 },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: zoneRows.map((item) => item.zone.name),
      axisTick: { show: false },
      axisLine: { lineStyle: { color: '#E2E8F0' } },
      axisLabel: { color: '#94A3B8' },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 100,
      axisLabel: { color: '#94A3B8', formatter: '{value}%' },
      splitLine: { lineStyle: { color: '#E2E8F0', type: 'dashed' } },
    },
    series: [
      {
        name: '土壤湿度',
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 3, color: '#0052FF' },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: 'rgba(0, 82, 255, 0.22)' },
              { offset: 1, color: 'rgba(0, 82, 255, 0)' },
            ],
          },
        },
        data: zoneRows.map((item) => Number(item.soilMoisture.toFixed(1))),
      },
      {
        name: '阈值',
        type: 'line',
        smooth: true,
        symbol: 'none',
        lineStyle: { width: 2, color: '#CBD5E1', type: 'dashed' },
        data: zoneRows.map((item) => Number(item.threshold.toFixed(1))),
      },
    ],
  }
}

function DeviceControlCard({ dashboard }: { dashboard: DashboardData }) {
  const running = dashboard.irrigation?.status === 'running'
  const statusLabel = labelFor(dashboard.irrigation?.status || 'idle')
  const content = (
    <section className="h-full border-0 bg-white shadow-none">
      <div className="flex h-full flex-col gap-4 p-4">
        <div className="flex items-center justify-between gap-3">
          <SectionBadge label="Device Control" />
          <Badge tone={running ? 'warning' : 'success'}>{statusLabel}</Badge>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex size-10 items-center justify-center rounded-lg bg-gradient-to-r from-[#0052FF] to-[#4D7CFF] text-white shadow-electric">
            <Power className="size-5" aria-hidden="true" />
          </div>
          <div>
            <h3 className="m-0 text-base font-semibold text-slate-950">设备控制</h3>
            <p className="m-0 mt-1 text-xs text-slate-500">执行状态由后端计划与审批链路驱动。</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-md bg-slate-50 p-3">
            <span className="text-xs text-slate-500">计划时长</span>
            <strong className="mt-1 block text-lg font-semibold text-slate-950">
              {formatNumber1(dashboard.irrigation?.duration_minutes ?? null, ' 分钟')}
            </strong>
          </div>
          <div className="rounded-md bg-slate-50 p-3">
            <span className="text-xs text-slate-500">剩余时间</span>
            <strong className="mt-1 block text-lg font-semibold text-slate-950">
              {formatNumber1(dashboard.irrigation?.remaining_minutes ?? null, ' 分钟')}
            </strong>
          </div>
        </div>
      </div>
    </section>
  )

  if (!running) {
    return <div className="h-full rounded-lg bg-white shadow-sm ring-1 ring-blue-100">{content}</div>
  }

  return (
    <div className="h-full rounded-lg bg-gradient-to-r from-[#0052FF] to-[#4D7CFF] p-0.5 shadow-electric">
      {content}
    </div>
  )
}

function CompactMetricStrip({ dashboard }: { dashboard: DashboardData }) {
  const average = dashboard.sensors?.average
  const metrics = [
    { label: '温度', value: formatNumber1(average?.temperature ?? null), unit: '°C', icon: Thermometer },
    { label: '湿度', value: formatNumber1(average?.soil_moisture ?? null), unit: '%', icon: Droplets },
    { label: '光照', value: formatNumber1(average?.light_intensity ?? null), unit: 'lx', icon: Sun },
    { label: '降雨', value: formatNumber1(average?.rainfall ?? null), unit: 'mm', icon: CloudRain },
  ]

  return (
    <motion.section variants={itemVariants} className="rounded-lg bg-white p-3 shadow-sm">
      <div className="grid grid-cols-2 divide-y divide-slate-100 md:grid-cols-4 md:divide-x md:divide-y-0">
        {metrics.map((metric) => {
          const Icon = metric.icon
          return (
            <div key={metric.label} className="flex min-h-16 items-center justify-between gap-3 px-3 py-2 first:pl-0 md:px-4 md:first:pl-1 md:last:pr-1">
              <div>
                <span className="font-mono text-[0.62rem] font-semibold uppercase tracking-widest text-slate-400">{metric.label}</span>
                <div className="mt-1 flex items-baseline gap-1">
                  <strong className="text-2xl font-semibold leading-none text-slate-950">{metric.value}</strong>
                  <span className="text-xs text-slate-500">{metric.unit}</span>
                </div>
              </div>
              <div className="flex size-8 items-center justify-center rounded-md bg-blue-50 text-[#0052FF]">
                <Icon className="size-4" aria-hidden="true" />
              </div>
            </div>
          )
        })}
      </div>
    </motion.section>
  )
}

export function DashboardConsole({
  initialDashboard,
  initialSettings,
}: {
  initialDashboard: DashboardData
  initialSettings: RuntimeSettings | null
}) {
  const dashboardQuery = useQuery({
    queryKey: ['dashboard'],
    queryFn: () => apiGet<DashboardData>('/api/dashboard'),
    initialData: initialDashboard,
    refetchInterval: 5_000,
  })
  const settingsQuery = useQuery({
    queryKey: ['settings'],
    queryFn: () => apiGet<RuntimeSettings>('/api/settings'),
    initialData: initialSettings,
    enabled: Boolean(initialSettings),
    refetchInterval: 30_000,
  })

  const dashboard = dashboardQuery.data
  const settings = settingsQuery.data
  const zoneRows = buildZoneRows(dashboard)
  const rainfall = dashboard.sensors?.average.rainfall ?? null
  const lastUpdated = formatDateTime(dashboard.status?.timestamp || dashboard.sensors?.timestamp)

  return (
    <motion.div className="console-dashboard flex flex-col gap-4" variants={containerVariants} initial="hidden" animate="show">
      <motion.section variants={itemVariants} className="surface-panel flex flex-col gap-3">
        <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
          <div className="max-w-2xl">
            <SectionBadge label="HydroAgent Overview" />
            <h1 className="mt-2 text-2xl font-semibold leading-tight text-slate-950">智能灌溉控制台</h1>
            <p className="mt-2 text-sm leading-6 text-slate-500">
              以计划、审批、执行和审计链路组织灌溉决策，当前数据每 5 秒自动刷新。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <Badge tone={dashboard.backendReachable ? 'success' : 'danger'}>
              <StatusDot tone={dashboard.backendReachable ? 'success' : 'danger'} />
              {dashboard.backendReachable ? 'CORE ONLINE' : 'CORE OFFLINE'}
            </Badge>
            <Badge>UPDATED {lastUpdated}</Badge>
          </div>
        </div>
      </motion.section>

      <motion.div variants={itemVariants}>
        <DashboardChatLauncher />
      </motion.div>

      <CompactMetricStrip dashboard={dashboard} />

      <div className="grid grid-cols-1 items-stretch gap-4 lg:grid-cols-12">
        <main className="flex h-full min-w-0 flex-col gap-4 lg:col-span-8">
          <motion.section variants={itemVariants} className="surface-panel flex min-h-[360px] flex-1 flex-col">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <SectionBadge label="24H Trend" />
                <h2 className="m-0 mt-3 text-base font-semibold text-slate-950">近24小时运行趋势</h2>
              </div>
              <span className="text-sm text-slate-500">{zoneRows.length} 个分区</span>
            </div>
            {zoneRows.length === 0 ? (
              <EmptyState className="flex-1" title="暂无分区数据" description="核心未返回分区与传感器信息，图表保持空态。" />
            ) : (
              <div className="min-h-[320px] flex-1">
                <ReactECharts option={buildMoistureOption(zoneRows)} style={{ height: '100%', minHeight: 320 }} />
              </div>
            )}
          </motion.section>

          <motion.section variants={itemVariants} className="surface-panel flex h-full flex-col">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <SectionBadge label="Zone Status" />
                <h2 className="m-0 mt-3 text-base font-semibold text-slate-950">分区状态</h2>
              </div>
              <span className="text-sm text-slate-500">阈值默认 {formatPercent1(settings?.soil_moisture_threshold ?? 40)}</span>
            </div>
            {zoneRows.length === 0 ? (
              <EmptyState className="flex-1" title="暂无分区数据" description="核心未返回分区与传感器信息。" />
            ) : (
              <div className="data-table-shell flex-1">
                <table className="min-w-[760px] w-full border-collapse text-sm">
                  <thead className="bg-slate-50 text-left font-mono text-[0.64rem] uppercase tracking-widest text-slate-400">
                    <tr>
                      <th className="h-9 border-b border-slate-100 px-3 font-semibold">分区</th>
                      <th className="h-9 border-b border-slate-100 px-3 font-semibold">湿度</th>
                      <th className="h-9 border-b border-slate-100 px-3 font-semibold">阈值</th>
                      <th className="h-9 border-b border-slate-100 px-3 font-semibold">缺口</th>
                      <th className="h-9 border-b border-slate-100 px-3 font-semibold">执行器</th>
                    </tr>
                  </thead>
                  <tbody>
                    {zoneRows.map((item) => (
                      <tr key={item.zone.zone_id} className="h-10 border-b border-slate-100 last:border-b-0 hover:bg-blue-50/40">
                        <td className="px-3">
                          <strong className="block truncate text-slate-950">{item.zone.name}</strong>
                          <span className="block truncate text-xs text-slate-500">{item.zone.location}</span>
                        </td>
                        <td className="px-3 font-semibold text-slate-900">{formatPercent1(item.soilMoisture)}</td>
                        <td className="px-3 text-slate-600">{formatPercent1(item.threshold)}</td>
                        <td className="px-3 text-slate-600">{formatPercent1(item.deficit)}</td>
                        <td className="px-3">
                          <div className="flex items-center gap-2">
                            <Badge tone={toneForState(item.actuator?.status)}>{labelFor(item.actuator?.status || 'unknown')}</Badge>
                            <span className="truncate text-xs text-slate-500">{item.actuator?.name || '未绑定执行器'}</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </motion.section>
        </main>

        <aside className="flex h-full min-w-0 flex-col gap-4 lg:col-span-4">
          <motion.div variants={itemVariants} className="shrink-0">
            <DeviceControlCard dashboard={dashboard} />
          </motion.div>

          <motion.section variants={itemVariants} className="surface-panel flex flex-1 flex-col">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <SectionBadge label="Weather Window" />
                <h2 className="m-0 mt-3 text-base font-semibold text-slate-950">天气预报</h2>
              </div>
              <Badge tone="success">
                <CloudRain className="size-3" />
                {formatNumber1(rainfall, 'MM')}
              </Badge>
            </div>
            {(dashboard.weather?.forecast || []).length === 0 ? (
              <EmptyState className="flex-1" title="暂无预报" description="天气服务未返回未来窗口，自动灌溉将保持谨慎。" icon={CloudRain} />
            ) : (
              <div className="flex flex-1 flex-col justify-between gap-3">
                {(dashboard.weather?.forecast || []).slice(0, 4).map((forecast) => (
                  <div key={forecast.date} className="flex items-center justify-between gap-3 rounded-md bg-slate-50 p-3">
                    <div>
                      <strong className="text-sm text-slate-950">{forecast.date}</strong>
                      <p className="mt-1 text-xs text-slate-500">{forecast.day_weather}</p>
                    </div>
                    <span className="text-sm font-semibold text-slate-700">{forecast.day_temp}° / {forecast.night_temp}°</span>
                  </div>
                ))}
              </div>
            )}
          </motion.section>
        </aside>
      </div>
    </motion.div>
  )
}
