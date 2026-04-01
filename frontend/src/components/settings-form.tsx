'use client'

import { useState, useTransition } from 'react'
import { RuntimeSettings } from '@/lib/types'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'

export function SettingsForm({ initialSettings }: { initialSettings: RuntimeSettings }) {
  const [settings, setSettings] = useState(initialSettings)
  const [message, setMessage] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  function update<K extends keyof RuntimeSettings>(key: K, value: RuntimeSettings[K]) {
    setSettings((current) => ({ ...current, [key]: value }))
  }

  function submit() {
    startTransition(async () => {
      setMessage(null)
      const response = await fetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          soil_moisture_threshold: settings.soil_moisture_threshold,
          default_duration_minutes: settings.default_duration_minutes,
          alarm_threshold: settings.alarm_threshold,
          alarm_enabled: settings.alarm_enabled,
        }),
      })

      if (!response.ok) {
        setMessage(await response.text())
        return
      }

      const payload = await response.json()
      setSettings(payload.settings)
      setMessage('设置已保存')
    })
  }

  return (
    <div className="settings-layout">
      <Card>
        <CardHeader>
          <CardTitle>运行参数</CardTitle>
          <CardDescription>调整阈值与默认灌溉策略，变更会立即影响当前运行时配置。</CardDescription>
        </CardHeader>
        <CardContent className="settings-grid">
          <label className="field-card">
            <span>土壤湿度阈值 (%)</span>
            <Input
              type="number"
              value={settings.soil_moisture_threshold}
              onChange={(event) => update('soil_moisture_threshold', Number(event.target.value))}
            />
          </label>

          <label className="field-card">
            <span>默认灌溉时长 (分钟)</span>
            <Input
              type="number"
              value={settings.default_duration_minutes}
              onChange={(event) => update('default_duration_minutes', Number(event.target.value))}
            />
          </label>

          <label className="field-card">
            <span>报警阈值 (%)</span>
            <Input
              type="number"
              value={settings.alarm_threshold}
              onChange={(event) => update('alarm_threshold', Number(event.target.value))}
            />
          </label>

          <label className="field-card toggle-card">
            <span>启用报警</span>
            <input
              className="ui-checkbox"
              type="checkbox"
              checked={settings.alarm_enabled}
              onChange={(event) => update('alarm_enabled', event.target.checked)}
            />
          </label>

          <div className="settings-footer">
            <Button disabled={isPending} onClick={submit}>
              {isPending ? '保存中...' : '保存设置'}
            </Button>
            {message ? <span className="inline-message">{message}</span> : null}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>系统信息</CardTitle>
          <CardDescription>只读元数据用于确认模型、数据源和采集节奏是否符合预期。</CardDescription>
        </CardHeader>
        <CardContent className="meta-list">
          <div className="meta-row"><span>模型</span><strong>{settings.model_name || '--'}</strong></div>
          <div className="meta-row"><span>数据库</span><strong>{settings.db_type || '--'}</strong></div>
          <div className="meta-row"><span>采集周期</span><strong>{settings.collection_interval_minutes || '--'} 分钟</strong></div>
          <div className="meta-row meta-row-wrap">
            <span>传感器</span>
            <div className="tag-list">
              {(settings.sensor_ids || []).length
                ? (settings.sensor_ids || []).map((sensorId) => <Badge key={sensorId}>{sensorId}</Badge>)
                : <strong>--</strong>}
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  )
}
