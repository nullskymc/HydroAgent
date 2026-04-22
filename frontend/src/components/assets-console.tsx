'use client'

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent } from '@/components/ui/card'
import { EmptyState } from '@/components/ui/empty-state'
import { SectionBadge } from '@/components/ui/section-badge'
import { apiGet, apiSend } from '@/lib/api-client'
import { Actuator, SensorDevice, UserProfile, Zone } from '@/lib/types'
import { labelFor } from '@/lib/labels'
import { formatPercent1 } from '@/lib/format'

type AssetPayload = { zones: Zone[]; sensors: SensorDevice[]; actuators: Actuator[] }

function AssetCard({
  label,
  count,
  children,
}: {
  label: string
  count: number
  children: React.ReactNode
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 p-4">
        <div className="flex items-center justify-between gap-3">
          <SectionBadge label={label} />
          <Badge>{count}</Badge>
        </div>
        {children}
      </CardContent>
    </Card>
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

  return (
    <div className="admin-grid admin-grid-3">
      <AssetCard label="Zones" count={assetsQuery.data.zones.length}>
        {assetsQuery.data.zones.length === 0 ? (
          <EmptyState title="暂无分区数据" description="资产接口未返回分区数据。" />
        ) : (
          <div className="admin-list">
            {assetsQuery.data.zones.map((zone) => (
              <div key={zone.zone_id} className="admin-list-item">
                <div>
                  <strong>{zone.name}</strong>
                  <p>{zone.location} · 阈值 {formatPercent1(zone.soil_moisture_threshold)}</p>
                  <Badge tone={zone.is_enabled ? 'success' : 'default'}>{zone.is_enabled ? '启用' : '停用'}</Badge>
                </div>
                {canManage ? (
                  <Button size="sm" variant={zone.is_enabled ? 'secondary' : 'primary'} disabled={toggleMutation.isPending} onClick={() => toggleMutation.mutate({ path: `/api/assets/zones/${zone.zone_id}`, enabled: !zone.is_enabled })}>
                    {zone.is_enabled ? '停用' : '启用'}
                  </Button>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </AssetCard>

      <AssetCard label="Sensors" count={assetsQuery.data.sensors.length}>
        {assetsQuery.data.sensors.length === 0 ? (
          <EmptyState title="暂无传感器数据" description="资产接口未返回传感器数据。" />
        ) : (
          <div className="admin-list">
            {assetsQuery.data.sensors.map((sensor) => (
              <div key={sensor.sensor_device_id} className="admin-list-item">
                <div>
                  <strong>{sensor.name}</strong>
                  <p>{sensor.sensor_id} · {labelFor(sensor.status)}</p>
                  <Badge tone={sensor.is_enabled ? 'success' : 'default'}>{sensor.is_enabled ? '启用' : '停用'}</Badge>
                </div>
                {canManage ? (
                  <Button size="sm" variant={sensor.is_enabled ? 'secondary' : 'primary'} disabled={toggleMutation.isPending} onClick={() => toggleMutation.mutate({ path: `/api/assets/sensors/${sensor.sensor_device_id}`, enabled: !sensor.is_enabled })}>
                    {sensor.is_enabled ? '停用' : '启用'}
                  </Button>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </AssetCard>

      <AssetCard label="Actuators" count={assetsQuery.data.actuators.length}>
        {assetsQuery.data.actuators.length === 0 ? (
          <EmptyState title="暂无执行器数据" description="资产接口未返回执行器数据。" />
        ) : (
          <div className="admin-list">
            {assetsQuery.data.actuators.map((actuator) => (
              <div key={actuator.actuator_id} className="admin-list-item">
                <div>
                  <strong>{actuator.name}</strong>
                  <p>{labelFor(actuator.status)} · {labelFor(actuator.health_status || 'healthy')}</p>
                  <Badge tone={actuator.is_enabled ? 'success' : 'default'}>{actuator.is_enabled ? '启用' : '停用'}</Badge>
                </div>
                {canManage ? (
                  <Button size="sm" variant={actuator.is_enabled ? 'secondary' : 'primary'} disabled={toggleMutation.isPending} onClick={() => toggleMutation.mutate({ path: `/api/assets/actuators/${actuator.actuator_id}`, enabled: !actuator.is_enabled })}>
                    {actuator.is_enabled ? '停用' : '启用'}
                  </Button>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </AssetCard>
    </div>
  )
}
