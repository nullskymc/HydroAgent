'use client'

import type { ReactNode } from 'react'
import ReactECharts from 'echarts-for-react'
import { EmptyState } from '@/components/ui/empty-state'
import { SectionBadge } from '@/components/ui/section-badge'
import { PLAN_STAGE_LABELS, labelFor } from '@/lib/labels'
import { AnalyticsOverview } from '@/lib/types'
import { formatNumber1, formatPercent1 } from '@/lib/format'

const axisStyle = {
  axisTick: { show: false },
  axisLine: { lineStyle: { color: '#E2E8F0' } },
  axisLabel: { color: '#94A3B8' },
}

const valueAxisStyle = {
  axisLabel: { color: '#94A3B8' },
  splitLine: { lineStyle: { color: '#E2E8F0', type: 'dashed' } },
}

function chartShell(label: string, children: ReactNode) {
  return (
    <section className="surface-panel">
      <div className="mb-4">
        <SectionBadge label={label} />
      </div>
      {children}
    </section>
  )
}

export function AnalyticsOverviewPanel({ overview }: { overview: AnalyticsOverview }) {
  const moistureOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', valueFormatter: (value: number) => formatPercent1(Number(value)) },
    legend: { data: ['土壤湿度', '阈值'], textStyle: { color: '#64748B' } },
    grid: { left: 34, right: 18, top: 44, bottom: 28 },
    xAxis: { type: 'category', boundaryGap: false, data: overview.soil_trend.labels, ...axisStyle },
    yAxis: { type: 'value', min: 0, max: 100, ...valueAxisStyle },
    series: [
      {
        name: '土壤湿度',
        type: 'line',
        smooth: true,
        symbol: 'none',
        data: overview.soil_trend.soil_moisture.map((value) => Number(value.toFixed(1))),
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
      },
      {
        name: '阈值',
        type: 'line',
        smooth: true,
        symbol: 'none',
        data: overview.soil_trend.threshold.map((value) => Number(value.toFixed(1))),
        lineStyle: { width: 2, color: '#CBD5E1', type: 'dashed' },
      },
    ],
  }

  const funnelOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', valueFormatter: (value: number) => formatNumber1(Number(value), ' 次') },
    grid: { left: 34, right: 18, top: 20, bottom: 36 },
    xAxis: { type: 'category', data: overview.plan_funnel.items.map((item) => labelFor(item.stage, PLAN_STAGE_LABELS)), ...axisStyle },
    yAxis: { type: 'value', minInterval: 1, ...valueAxisStyle },
    series: [
      {
        type: 'bar',
        data: overview.plan_funnel.items.map((item) => item.count),
        barWidth: 28,
        itemStyle: { color: '#0052FF', borderRadius: [8, 8, 0, 0] },
      },
    ],
  }

  const alertOption = {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { data: ['高风险', '中风险', '低风险'], textStyle: { color: '#64748B' } },
    grid: { left: 34, right: 18, top: 44, bottom: 28 },
    xAxis: { type: 'category', data: overview.alert_trend.labels, ...axisStyle },
    yAxis: { type: 'value', minInterval: 1, ...valueAxisStyle },
    series: [
      { name: '高风险', type: 'line', smooth: true, symbol: 'none', data: overview.alert_trend.series.high || [], lineStyle: { color: '#E11D48', width: 2 } },
      { name: '中风险', type: 'line', smooth: true, symbol: 'none', data: overview.alert_trend.series.medium || [], lineStyle: { color: '#F59E0B', width: 2 } },
      { name: '低风险', type: 'line', smooth: true, symbol: 'none', data: overview.alert_trend.series.low || [], lineStyle: { color: '#10B981', width: 2 } },
    ],
  }

  const heatmapOption = {
    backgroundColor: 'transparent',
    tooltip: {},
    grid: { left: 76, right: 18, top: 22, bottom: 42 },
    xAxis: { type: 'category', data: ['湿度', '缺口', '告警'], ...axisStyle },
    yAxis: { type: 'category', data: overview.zone_health.map((item) => item.zone_name), ...axisStyle },
    visualMap: {
      min: 0,
      max: Math.max(100, ...overview.zone_health.map((item) => Math.max(item.soil_moisture, item.deficit, item.alert_count))),
      calculable: false,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
      inRange: { color: ['#EFF6FF', '#4D7CFF', '#0052FF'] },
    },
    series: [
      {
        type: 'heatmap',
        data: overview.zone_health.flatMap((item, index) => [
          [0, index, Number(item.soil_moisture.toFixed(1))],
          [1, index, Number(item.deficit.toFixed(1))],
          [2, index, item.alert_count],
        ]),
        label: { show: true, color: '#0F172A' },
      },
    ],
  }

  if (!overview.soil_trend.labels.length) {
    return <EmptyState title="暂无分析数据" description="分析接口还没有返回可视化序列。" />
  }

  return (
    <div className="admin-chart-grid">
      {chartShell('Moisture Trend', <ReactECharts option={moistureOption} style={{ height: 280 }} />)}
      {chartShell('Plan Funnel', <ReactECharts option={funnelOption} style={{ height: 280 }} />)}
      {chartShell('Alert Trend', <ReactECharts option={alertOption} style={{ height: 280 }} />)}
      {chartShell('Zone Health', <ReactECharts option={heatmapOption} style={{ height: 320 }} />)}
    </div>
  )
}
