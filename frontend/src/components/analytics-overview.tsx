'use client'

import ReactECharts from 'echarts-for-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { AnalyticsOverview } from '@/lib/types'

export function AnalyticsOverviewPanel({ overview }: { overview: AnalyticsOverview }) {
  const moistureOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['湿度', '阈值'] },
    xAxis: { type: 'category', data: overview.soil_trend.labels },
    yAxis: { type: 'value', min: 0, max: 100 },
    series: [
      { name: '湿度', type: 'line', smooth: true, data: overview.soil_trend.soil_moisture },
      { name: '阈值', type: 'line', smooth: true, data: overview.soil_trend.threshold },
    ],
  }

  const funnelOption = {
    tooltip: { trigger: 'item' },
    xAxis: { type: 'category', data: overview.plan_funnel.items.map((item) => item.stage) },
    yAxis: { type: 'value' },
    series: [{ type: 'bar', data: overview.plan_funnel.items.map((item) => item.count), itemStyle: { color: '#0f766e' } }],
  }

  const alertOption = {
    tooltip: { trigger: 'axis' },
    legend: { data: ['high', 'medium', 'low'] },
    xAxis: { type: 'category', data: overview.alert_trend.labels },
    yAxis: { type: 'value' },
    series: [
      { name: 'high', type: 'line', data: overview.alert_trend.series.high || [] },
      { name: 'medium', type: 'line', data: overview.alert_trend.series.medium || [] },
      { name: 'low', type: 'line', data: overview.alert_trend.series.low || [] },
    ],
  }

  const heatmapOption = {
    tooltip: {},
    xAxis: { type: 'category', data: ['湿度', '缺口', '告警'] },
    yAxis: { type: 'category', data: overview.zone_health.map((item) => item.zone_name) },
    visualMap: {
      min: 0,
      max: Math.max(100, ...overview.zone_health.map((item) => Math.max(item.soil_moisture, item.deficit, item.alert_count))),
      calculable: true,
      orient: 'horizontal',
      left: 'center',
      bottom: 0,
    },
    series: [
      {
        type: 'heatmap',
        data: overview.zone_health.flatMap((item, index) => [
          [0, index, item.soil_moisture],
          [1, index, item.deficit],
          [2, index, item.alert_count],
        ]),
        label: { show: true },
      },
    ],
  }

  return (
    <div className="admin-chart-grid">
      <Card>
        <CardHeader>
          <CardTitle>湿度趋势</CardTitle>
        </CardHeader>
        <CardContent>
          <ReactECharts option={moistureOption} style={{ height: 280 }} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>计划漏斗</CardTitle>
        </CardHeader>
        <CardContent>
          <ReactECharts option={funnelOption} style={{ height: 280 }} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>告警趋势</CardTitle>
        </CardHeader>
        <CardContent>
          <ReactECharts option={alertOption} style={{ height: 280 }} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>分区健康热力图</CardTitle>
        </CardHeader>
        <CardContent>
          <ReactECharts option={heatmapOption} style={{ height: 320 }} />
        </CardContent>
      </Card>
    </div>
  )
}
