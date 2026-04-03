from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.database.models import User, get_db
from src.services.asset_service import (
    bind_sensor_to_zone,
    create_sensor_device,
    create_zone_asset,
    ensure_sensor_devices,
    list_actuators,
    list_sensor_devices,
    update_actuator_asset,
    update_sensor_device,
    update_zone_asset,
)
from src.services.auth_service import get_current_user, record_audit_event, require_permission
from src.services.irrigation_service import list_zones

router = APIRouter(prefix="/assets", tags=["assets"])


class ZoneUpsertRequest(BaseModel):
    name: str
    location: str = "北京"
    crop_type: str = "通用作物"
    soil_moisture_threshold: float = 40.0
    default_duration_minutes: int = 30
    is_enabled: bool = True
    notes: str | None = None


class ZonePatchRequest(BaseModel):
    name: str | None = None
    location: str | None = None
    crop_type: str | None = None
    soil_moisture_threshold: float | None = None
    default_duration_minutes: int | None = None
    is_enabled: bool | None = None
    notes: str | None = None
    sensor_device_id: str | None = None
    sensor_role: str | None = "primary"


class SensorUpsertRequest(BaseModel):
    sensor_id: str
    name: str
    model: str | None = None
    location: str | None = None
    status: str = "online"
    notes: str | None = None


class SensorPatchRequest(BaseModel):
    name: str | None = None
    model: str | None = None
    location: str | None = None
    status: str | None = None
    notes: str | None = None
    is_enabled: bool | None = None


class ActuatorPatchRequest(BaseModel):
    name: str | None = None
    status: str | None = None
    is_enabled: bool | None = None
    serial_number: str | None = None
    firmware_version: str | None = None
    health_status: str | None = None


@router.get("/zones")
def get_asset_zones(
    _: User = Depends(require_permission("assets:view")),
    db: Session = Depends(get_db),
):
    ensure_sensor_devices(db)
    return {"zones": [zone.to_dict() for zone in list_zones(db)]}


@router.post("/zones")
def create_asset_zone(
    req: ZoneUpsertRequest,
    current_user: User = Depends(require_permission("assets:manage")),
    db: Session = Depends(get_db),
):
    zone = create_zone_asset(db, **req.dict())
    record_audit_event(
        db,
        actor=current_user.username,
        event_type="asset.zone.create",
        object_type="zone",
        object_id=zone.zone_id,
        details=req.dict(),
    )
    return {"zone": zone.to_dict()}


@router.patch("/zones/{zone_id}")
def patch_zone(
    zone_id: str,
    req: ZonePatchRequest,
    current_user: User = Depends(require_permission("assets:manage")),
    db: Session = Depends(get_db),
):
    payload = req.dict(exclude_unset=True)
    sensor_device_id = payload.pop("sensor_device_id", None)
    sensor_role = payload.pop("sensor_role", "primary")
    zone = update_zone_asset(db, zone_id, **payload)
    if not zone:
        raise HTTPException(status_code=404, detail="分区不存在")
    if sensor_device_id:
        bind_sensor_to_zone(db, zone_id=zone_id, sensor_device_id=sensor_device_id, role=sensor_role or "primary")
        zone = next(item for item in list_zones(db) if item.zone_id == zone_id)
    record_audit_event(
        db,
        actor=current_user.username,
        event_type="asset.zone.update",
        object_type="zone",
        object_id=zone.zone_id,
        details=req.dict(exclude_unset=True),
    )
    return {"zone": zone.to_dict()}


@router.get("/sensors")
def get_sensors(
    _: User = Depends(require_permission("assets:view")),
    db: Session = Depends(get_db),
):
    return {"sensors": [sensor.to_dict() for sensor in list_sensor_devices(db)]}


@router.post("/sensors")
def create_sensor(
    req: SensorUpsertRequest,
    current_user: User = Depends(require_permission("assets:manage")),
    db: Session = Depends(get_db),
):
    sensor = create_sensor_device(db, **req.dict())
    record_audit_event(
        db,
        actor=current_user.username,
        event_type="asset.sensor.create",
        object_type="sensor",
        object_id=sensor.sensor_device_id,
        details=req.dict(),
    )
    return {"sensor": sensor.to_dict()}


@router.patch("/sensors/{sensor_device_id}")
def patch_sensor(
    sensor_device_id: str,
    req: SensorPatchRequest,
    current_user: User = Depends(require_permission("assets:manage")),
    db: Session = Depends(get_db),
):
    sensor = update_sensor_device(db, sensor_device_id, **req.dict(exclude_unset=True))
    if not sensor:
        raise HTTPException(status_code=404, detail="传感器不存在")
    record_audit_event(
        db,
        actor=current_user.username,
        event_type="asset.sensor.update",
        object_type="sensor",
        object_id=sensor.sensor_device_id,
        details=req.dict(exclude_unset=True),
    )
    return {"sensor": sensor.to_dict()}


@router.get("/actuators")
def get_actuators(
    _: User = Depends(require_permission("assets:view")),
    db: Session = Depends(get_db),
):
    return {"actuators": [actuator.to_dict() for actuator in list_actuators(db)]}


@router.patch("/actuators/{actuator_id}")
def patch_actuator(
    actuator_id: str,
    req: ActuatorPatchRequest,
    current_user: User = Depends(require_permission("assets:manage")),
    db: Session = Depends(get_db),
):
    actuator = update_actuator_asset(db, actuator_id, **req.dict(exclude_unset=True))
    if not actuator:
        raise HTTPException(status_code=404, detail="执行器不存在")
    record_audit_event(
        db,
        actor=current_user.username,
        event_type="asset.actuator.update",
        object_type="actuator",
        object_id=actuator.actuator_id,
        details=req.dict(exclude_unset=True),
    )
    return {"actuator": actuator.to_dict()}
