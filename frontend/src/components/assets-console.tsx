'use client'

import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Actuator, SensorDevice, UserProfile, Zone } from '@/lib/types'

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
  const [zones, setZones] = useState(initialZones)
  const [sensors, setSensors] = useState(initialSensors)
  const [actuators, setActuators] = useState(initialActuators)

  async function toggleZone(zone: Zone) {
    const response = await fetch(`/api/assets/zones/${zone.zone_id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_enabled: !zone.is_enabled }),
    })
    if (!response.ok) return
    const payload = await response.json()
    setZones((current) => current.map((item) => (item.zone_id === zone.zone_id ? payload.zone : item)))
  }

  async function toggleSensor(sensor: SensorDevice) {
    const response = await fetch(`/api/assets/sensors/${sensor.sensor_device_id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_enabled: !sensor.is_enabled }),
    })
    if (!response.ok) return
    const payload = await response.json()
    setSensors((current) => current.map((item) => (item.sensor_device_id === sensor.sensor_device_id ? payload.sensor : item)))
  }

  async function toggleActuator(actuator: Actuator) {
    const response = await fetch(`/api/assets/actuators/${actuator.actuator_id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_enabled: !actuator.is_enabled }),
    })
    if (!response.ok) return
    const payload = await response.json()
    setActuators((current) => current.map((item) => (item.actuator_id === actuator.actuator_id ? payload.actuator : item)))
  }

  return (
    <div className="admin-grid admin-grid-3">
      <Card>
        <CardHeader><CardTitle>分区</CardTitle></CardHeader>
        <CardContent className="admin-list">
          {zones.map((zone) => (
            <div key={zone.zone_id} className="admin-list-item">
              <div>
                <strong>{zone.name}</strong>
                <p>{zone.location} · 阈值 {zone.soil_moisture_threshold}%</p>
              </div>
              {currentUser.permissions.includes('assets:manage') ? (
                <Button size="sm" variant={zone.is_enabled ? 'secondary' : 'primary'} onClick={() => toggleZone(zone)}>
                  {zone.is_enabled ? '停用' : '启用'}
                </Button>
              ) : null}
            </div>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>传感器</CardTitle></CardHeader>
        <CardContent className="admin-list">
          {sensors.map((sensor) => (
            <div key={sensor.sensor_device_id} className="admin-list-item">
              <div>
                <strong>{sensor.name}</strong>
                <p>{sensor.sensor_id} · {sensor.status}</p>
              </div>
              {currentUser.permissions.includes('assets:manage') ? (
                <Button size="sm" variant={sensor.is_enabled ? 'secondary' : 'primary'} onClick={() => toggleSensor(sensor)}>
                  {sensor.is_enabled ? '停用' : '启用'}
                </Button>
              ) : null}
            </div>
          ))}
        </CardContent>
      </Card>
      <Card>
        <CardHeader><CardTitle>执行器</CardTitle></CardHeader>
        <CardContent className="admin-list">
          {actuators.map((actuator) => (
            <div key={actuator.actuator_id} className="admin-list-item">
              <div>
                <strong>{actuator.name}</strong>
                <p>{actuator.status} · {actuator.health_status || 'healthy'}</p>
              </div>
              {currentUser.permissions.includes('assets:manage') ? (
                <Button size="sm" variant={actuator.is_enabled ? 'secondary' : 'primary'} onClick={() => toggleActuator(actuator)}>
                  {actuator.is_enabled ? '停用' : '启用'}
                </Button>
              ) : null}
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  )
}
