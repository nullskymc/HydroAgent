#!/usr/bin/env python3
"""
Seed deterministic demo sensor history for ML soil-moisture forecasting.
"""
from __future__ import annotations

import argparse
import datetime as dt
import random
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.database.models import SensorData, SessionLocal, WeatherData, init_db
from src.services.irrigation_service import bootstrap_default_zones, list_zones

MIN_EXISTING_ROWS = 6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed demo sensor history for HydroAgent ML prediction.")
    parser.add_argument("--history-hours", type=int, default=168)
    parser.add_argument("--interval-hours", type=int, default=2)
    parser.add_argument("--force", action="store_true", help="Delete recent demo rows before seeding.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    init_db()
    db = SessionLocal()
    try:
        inserted = seed_sensor_history(
            db,
            history_hours=args.history_hours,
            interval_hours=args.interval_hours,
            force=args.force,
        )
        print(f"seeded {inserted} sensor rows")
    finally:
        db.close()


def seed_sensor_history(db, *, history_hours: int = 168, interval_hours: int = 2, force: bool = False) -> int:
    zones = bootstrap_default_zones(db)
    if not zones:
        zones = list_zones(db)

    now = dt.datetime.utcnow()
    since = now - dt.timedelta(hours=max(1, history_hours))
    interval_hours = max(1, interval_hours)
    point_count = max(2, history_hours // interval_hours + 1)
    delete_since = since - dt.timedelta(hours=interval_hours)
    inserted = 0

    for zone_index, zone in enumerate(zones):
        _seed_weather(db, zone.location, since, delete_since, now, force=force)
        for binding in zone.sensor_bindings:
            if not binding.is_enabled:
                continue
            sensor_id = binding.sensor_id
            if force:
                db.query(SensorData).filter(SensorData.sensor_id == sensor_id, SensorData.timestamp >= delete_since).delete(
                    synchronize_session=False
                )
                db.commit()
            existing_count = (
                db.query(SensorData)
                .filter(SensorData.sensor_id == sensor_id, SensorData.timestamp >= since)
                .count()
            )
            if existing_count >= MIN_EXISTING_ROWS:
                print(f"skip {sensor_id}: {existing_count} recent rows already exist")
                continue
            inserted += _seed_sensor(db, sensor_id, zone_index, since, interval_hours, point_count)

    return inserted


def _seed_sensor(
    db,
    sensor_id: str,
    zone_index: int,
    since: dt.datetime,
    interval_hours: int,
    point_count: int,
) -> int:
    rng = random.Random(f"hydro-demo:{sensor_id}")
    base_moisture = 62 - zone_index * 8
    inserted = 0
    for index in range(point_count):
        timestamp = since + dt.timedelta(hours=index * interval_hours)
        # Keep a gentle drying trend so the regression forecast differs from the latest mock value.
        moisture = max(8.0, min(92.0, base_moisture - index * 0.22 + rng.uniform(-1.1, 1.1)))
        temperature = 23 + zone_index * 0.8 + rng.uniform(-1.5, 1.5)
        rainfall = 0.0 if index % 19 else round(rng.uniform(0.2, 1.0), 2)
        db.add(
            SensorData(
                sensor_id=sensor_id,
                timestamp=timestamp,
                soil_moisture=round(moisture, 2),
                temperature=round(temperature, 2),
                light_intensity=round(560 + rng.uniform(-80, 80), 2),
                rainfall=rainfall,
                raw_data={"source": "demo_seed", "sensor_id": sensor_id},
            )
        )
        inserted += 1
    db.commit()
    return inserted


def _seed_weather(
    db,
    location: str,
    since: dt.datetime,
    delete_since: dt.datetime,
    now: dt.datetime,
    *,
    force: bool,
) -> None:
    if force:
        db.query(WeatherData).filter(WeatherData.location == location, WeatherData.timestamp >= delete_since).delete(
            synchronize_session=False
        )
        db.commit()
    existing = db.query(WeatherData).filter(WeatherData.location == location, WeatherData.timestamp >= since).count()
    if existing:
        return
    db.add(
        WeatherData(
            location=location,
            timestamp=now,
            temperature=24,
            humidity=58,
            wind_speed=2,
            condition="晴",
            precipitation=0,
            forecast_data={"source": "demo_seed"},
        )
    )
    db.commit()


if __name__ == "__main__":
    main()
