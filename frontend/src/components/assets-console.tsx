'use client'

import type { ReactNode } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge, StatusDot } from '@/components/ui/badge'
import { EmptyState } from '@/components/ui/empty-state'
import { SectionBadge } from '@/components/ui/section-badge'
import { apiGet, apiSend } from '@/lib/api-client'
import { Actuator, SensorDevice, UserProfile, Zone } from '@/lib/types'
import { labelFor } from '@/lib/labels'
import { formatPercent1 } from '@/lib/format'
import { formatDateTime } from '@/lib/utils'

type AssetPayload = { zones: Zone[]; sensors: SensorDevice[]; actuators: Actuator[] }

function stateTone(value?: string | null): 'default' | 'success' | 'warning' | 'danger' {
  if (value === 'ready' || value === 'idle' || value === 'healthy' || value === 'online') return 'success'
  if (value === 'running' || value === 'executing' || value === 'maintenance') return 'warning'
  if (value === 'unknown' || value === 'error' || value === 'offline' || value === 'disabled') return 'danger'
  return 'default'
}

function AssetSection({
  label,
  count,
  children,
}: {
  label: string
  count: number
  children: ReactNode
}) {
  return (
    <section className="surface-panel flex min-h-0 flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <SectionBadge label={label} />
          <h2 className="m-0 mt-2 text-base font-semibold text-slate-950">{label}</h2>
        </div>
        <Badge>{count} 项</Badge>
      </div>
      {children}
    </section>
  )
}

function ToggleButton({
  enabled,
  disabled,
  onClick,
}: {
  enabled: boolean
  disabled: boolean
  onClick: () => void
}) {
  return (
    <Button size="sm" variant={enabled ? 'secondary' : 'primary'} disabled={disabled} onClick={onClick}>
      {enabled ? '停用' : '启用'}
    </Button>
  )
}

export function AssetsConsole({
  initialZones,
  initialSensors,
  initialActuators,
  currentUser,
}: {
  initialZones: Zone[]
  initialSensors: SensorDevice[]
  initialActuators: Actuator[]
  currentUser: UserProfile
}) {
  const queryClient = useQueryClient()
  const assetsQuery = useQuery({
    queryKey: ['assets'],
    queryFn: async (): Promise<AssetPayload> => {
      const [zones, sensors, actuators] = await Promise.all([
        apiGet<{ zones: Zone[] }>('/api/assets/zones'),
        apiGet<{ sensors: SensorDevice[] }>('/api/assets/sensors'),
        apiGet<{ actuators: Actuator[] }>('/api/assets/actuators'),
      ])
      return { zones: zones.zones || [], sensors: sensors.sensors || [], actuators: actuators.actuators || [] }
    },
    initialData: { zones: initialZones, sensors: initialSensors, actuators: initialActuators },
    refetchInterval: 15_000,
  })
  const toggleMutation = useMutation({
    mutationFn: ({ path, enabled }: { path: string; enabled: boolean }) => apiSend(path, 'PATCH', { is_enabled: enabled }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['assets'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
  const canManage = currentUser.permissions.includes('assets:manage')
  const totalCount = assetsQuery.data.zones.length + assetsQuery.data.sensors.length + assetsQuery.data.actuators.length
  const enabledCount = [
    ...assetsQuery.data.zones,
    ...assetsQuery.data.sensors,
    ...assetsQuery.data.actuators,
  ].filter((item) => item.is_enabled).length

  function toggle(path: string, enabled: boolean) {
    toggleMutation.mutate({ path, enabled })
  }

  return (
    <div className="page-stack">
      <section className="console-telemetry-bar">
        <div className="console-telemetry-title">
          <p className="eyebrow">Asset Registry</p>
          <h2>资产运行台</h2>
        </div>
        <div className="console-telemetry-stream">
          {[
            { label: '分区', value: assetsQuery.data.zones.length },
            { label: '传感器', value: assetsQuery.data.sensors.length },
            { label: '执行器', value: assetsQuery.data.actuators.length },
            { label: '启用资产', value: enabledCount },
          ].map((item) => (
            <div key={item.label} className="console-telemetry-item">
              <span>{item.label}</span>
              <strong>{item.value}</strong>
            </div>
          ))}
        </div>
        <div className="console-telemetry-meta">
          <span>{assetsQuery.isFetching ? 'Syncing' : 'Inventory'}</span>
          <strong>{totalCount} total</strong>
        </div>
      </section>

      <div className="grid gap-4 xl:grid-cols-3">
        <AssetSection label="Zones" count={assetsQuery.data.zones.length}>
          {assetsQuery.data.zones.length === 0 ? (
            <EmptyState title="暂无分区数据" description="资产接口未返回分区数据。" />
          ) : (
            <div className="data-table-shell">
              <table className="min-w-[620px] w-full border-collapse text-sm">
                <thead className="bg-slate-50 text-left font-mono text-[0.64rem] font-semibold tracking-normal text-slate-400">
                  <tr>
                    <th className="h-9 border-b border-slate-100 px-3">分区</th>
                    <th className="h-9 border-b border-slate-100 px-3">策略</th>
                    <th className="h-9 border-b border-slate-100 px-3">状态</th>
                    <th className="h-9 border-b border-slate-100 px-3 text-right">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {assetsQuery.data.zones.map((zone) => (
                    <tr key={zone.zone_id} className="border-b border-slate-100 last:border-b-0 hover:bg-blue-50/40">
                      <td className="h-11 px-3">
                        <strong className="block truncate text-sm font-semibold text-slate-950">{zone.name}</strong>
                        <span className="block truncate text-xs text-slate-500">{zone.location}</span>
                      </td>
                      <td className="h-11 px-3 text-xs text-slate-600">
                        {zone.crop_type || '未配置'} · 阈值 {formatPercent1(zone.soil_moisture_threshold)}
                      </td>
                      <td className="h-11 px-3">
                        <Badge tone={zone.is_enabled ? 'success' : 'default'}>
                          <StatusDot tone={zone.is_enabled ? 'success' : 'default'} />
                          {zone.is_enabled ? '启用' : '停用'}
                        </Badge>
                      </td>
                      <td className="h-11 px-3 text-right">
                        {canManage ? (
                          <ToggleButton
                            enabled={zone.is_enabled}
                            disabled={toggleMutation.isPending}
                            onClick={() => toggle(`/api/assets/zones/${zone.zone_id}`, !zone.is_enabled)}
                          />
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </AssetSection>

        <AssetSection label="Sensors" count={assetsQuery.data.sensors.length}>
          {assetsQuery.data.sensors.length === 0 ? (
            <EmptyState title="暂无传感器数据" description="资产接口未返回传感器数据。" />
          ) : (
            <div className="data-table-shell">
              <table className="min-w-[620px] w-full border-collapse text-sm">
                <thead className="bg-slate-50 text-left font-mono text-[0.64rem] font-semibold tracking-normal text-slate-400">
                  <tr>
                    <th className="h-9 border-b border-slate-100 px-3">设备</th>
                    <th className="h-9 border-b border-slate-100 px-3">在线</th>
                    <th className="h-9 border-b border-slate-100 px-3">启用</th>
                    <th className="h-9 border-b border-slate-100 px-3 text-right">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {assetsQuery.data.sensors.map((sensor) => (
                    <tr key={sensor.sensor_device_id} className="border-b border-slate-100 last:border-b-0 hover:bg-blue-50/40">
                      <td className="h-11 px-3">
                        <strong className="block truncate text-sm font-semibold text-slate-950">{sensor.name}</strong>
                        <span className="block truncate text-xs text-slate-500">{sensor.sensor_id} · {sensor.location || '未绑定位置'}</span>
                      </td>
                      <td className="h-11 px-3">
                        <Badge tone={stateTone(sensor.status)}>
                          <StatusDot tone={stateTone(sensor.status)} />
                          {labelFor(sensor.status)}
                        </Badge>
                      </td>
                      <td className="h-11 px-3">
                        <Badge tone={sensor.is_enabled ? 'success' : 'default'}>{sensor.is_enabled ? '启用' : '停用'}</Badge>
                      </td>
                      <td className="h-11 px-3 text-right">
                        {canManage ? (
                          <ToggleButton
                            enabled={sensor.is_enabled}
                            disabled={toggleMutation.isPending}
                            onClick={() => toggle(`/api/assets/sensors/${sensor.sensor_device_id}`, !sensor.is_enabled)}
                          />
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </AssetSection>

        <AssetSection label="Actuators" count={assetsQuery.data.actuators.length}>
          {assetsQuery.data.actuators.length === 0 ? (
            <EmptyState title="暂无执行器数据" description="资产接口未返回执行器数据。" />
          ) : (
            <div className="data-table-shell">
              <table className="min-w-[620px] w-full border-collapse text-sm">
                <thead className="bg-slate-50 text-left font-mono text-[0.64rem] font-semibold tracking-normal text-slate-400">
                  <tr>
                    <th className="h-9 border-b border-slate-100 px-3">设备</th>
                    <th className="h-9 border-b border-slate-100 px-3">状态</th>
                    <th className="h-9 border-b border-slate-100 px-3">最近命令</th>
                    <th className="h-9 border-b border-slate-100 px-3 text-right">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {assetsQuery.data.actuators.map((actuator) => {
                    const tone = actuator.is_enabled ? stateTone(actuator.status) : 'default'
                    return (
                      <tr key={actuator.actuator_id} className="border-b border-slate-100 last:border-b-0 hover:bg-blue-50/40">
                        <td className="h-11 px-3">
                          <strong className="block truncate text-sm font-semibold text-slate-950">{actuator.name}</strong>
                          <span className="block truncate text-xs text-slate-500">{actuator.actuator_type} · {actuator.zone_id}</span>
                        </td>
                        <td className="h-11 px-3">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <Badge tone={tone}>
                              <StatusDot tone={tone} />
                              {labelFor(actuator.status)}
                            </Badge>
                            <Badge tone={stateTone(actuator.health_status || 'healthy')}>{labelFor(actuator.health_status || 'healthy')}</Badge>
                          </div>
                        </td>
                        <td className="h-11 px-3 text-xs text-slate-500">{formatDateTime(actuator.last_command_at)}</td>
                        <td className="h-11 px-3 text-right">
                          {canManage ? (
                            <ToggleButton
                              enabled={actuator.is_enabled}
                              disabled={toggleMutation.isPending}
                              onClick={() => toggle(`/api/assets/actuators/${actuator.actuator_id}`, !actuator.is_enabled)}
                            />
                          ) : null}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </AssetSection>
      </div>
    </div>
  )
}
