"""
Asset domain service for zones, sensors and actuators.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from src.database.models import Actuator, SensorDevice, Zone, ZoneSensorBinding


def ensure_sensor_devices(db: Session):
    bindings = db.query(ZoneSensorBinding).all()
    changed = False
    for binding in bindings:
        device = db.query(SensorDevice).filter(SensorDevice.sensor_id == binding.sensor_id).first()
        if not device:
            device = SensorDevice(
                sensor_id=binding.sensor_id,
                name=f"传感器 {binding.sensor_id}",
                location=binding.zone.location if binding.zone else None,
                status="online",
                is_enabled=True,
                last_seen_at=dt.datetime.utcnow(),
            )
            db.add(device)
            db.flush()
            changed = True
        if binding.sensor_device_id != device.sensor_device_id:
            binding.sensor_device_id = device.sensor_device_id
            changed = True
    if changed:
        db.commit()


def list_sensor_devices(db: Session) -> list[SensorDevice]:
    ensure_sensor_devices(db)
    return db.query(SensorDevice).order_by(SensorDevice.created_at.asc()).all()


def create_sensor_device(
    db: Session,
    *,
    sensor_id: str,
    name: str,
    model: str | None = None,
    location: str | None = None,
    status: str = "online",
    notes: str | None = None,
) -> SensorDevice:
    device = SensorDevice(
        sensor_id=sensor_id,
        name=name,
        model=model,
        location=location,
        status=status,
        notes=notes,
        last_seen_at=dt.datetime.utcnow(),
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device


def update_sensor_device(db: Session, sensor_device_id: str, **updates) -> SensorDevice | None:
    device = db.query(SensorDevice).filter(SensorDevice.sensor_device_id == sensor_device_id).first()
    if not device:
        return None
    for key, value in updates.items():
        if value is not None and hasattr(device, key):
            setattr(device, key, value)
    if "status" in updates and updates.get("status") == "online":
        device.last_seen_at = dt.datetime.utcnow()
    db.commit()
    db.refresh(device)
    return device


def create_zone_asset(
    db: Session,
    *,
    name: str,
    location: str,
    crop_type: str,
    soil_moisture_threshold: float,
    default_duration_minutes: int,
    is_enabled: bool = True,
    notes: str | None = None,
) -> Zone:
    zone = Zone(
        name=name,
        location=location,
        crop_type=crop_type,
        soil_moisture_threshold=soil_moisture_threshold,
        default_duration_minutes=default_duration_minutes,
        is_enabled=is_enabled,
        notes=notes,
    )
    db.add(zone)
    db.commit()
    db.refresh(zone)
    return zone


def update_zone_asset(db: Session, zone_id: str, **updates) -> Zone | None:
    zone = db.query(Zone).filter(Zone.zone_id == zone_id).first()
    if not zone:
        return None
    for key, value in updates.items():
        if value is not None and hasattr(zone, key):
            setattr(zone, key, value)
    db.commit()
    db.refresh(zone)
    return zone


def list_actuators(db: Session) -> list[Actuator]:
    return db.query(Actuator).order_by(Actuator.created_at.asc()).all()


def update_actuator_asset(db: Session, actuator_id: str, **updates) -> Actuator | None:
    actuator = db.query(Actuator).filter(Actuator.actuator_id == actuator_id).first()
    if not actuator:
        return None
    for key, value in updates.items():
        if value is not None and hasattr(actuator, key):
            setattr(actuator, key, value)
    actuator.last_seen_at = dt.datetime.utcnow()
    db.commit()
    db.refresh(actuator)
    return actuator


def bind_sensor_to_zone(
    db: Session,
    *,
    zone_id: str,
    sensor_device_id: str,
    role: str = "primary",
    is_enabled: bool = True,
) -> ZoneSensorBinding:
    device = db.query(SensorDevice).filter(SensorDevice.sensor_device_id == sensor_device_id).first()
    if not device:
        raise ValueError("传感器不存在")

    binding = (
        db.query(ZoneSensorBinding)
        .filter(ZoneSensorBinding.zone_id == zone_id, ZoneSensorBinding.sensor_device_id == sensor_device_id)
        .first()
    )
    if not binding:
        binding = ZoneSensorBinding(
            zone_id=zone_id,
            sensor_id=device.sensor_id,
            sensor_device_id=device.sensor_device_id,
            role=role,
            is_enabled=is_enabled,
        )
        db.add(binding)
    else:
        binding.role = role
        binding.is_enabled = is_enabled
        binding.sensor_id = device.sensor_id
    db.commit()
    db.refresh(binding)
    return binding
