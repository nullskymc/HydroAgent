"""
Analytics aggregation service for HydroAgent.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

from sqlalchemy.orm import Session

from src.database.models import AlertEvent, IrrigationPlan, SensorData
from src.services.alert_service import list_alert_events
from src.services.irrigation_service import get_zone_status, list_plans, list_zones


def _is_executed_plan(plan: IrrigationPlan) -> bool:
    return str(plan.status or "") in {"executing", "completed"} or str(plan.execution_status or "") in {"running", "stopped", "executed"}


def _is_pending_plan(plan: IrrigationPlan) -> bool:
    return str(plan.status or "") == "pending_approval"


def _is_approved_plan(plan: IrrigationPlan) -> bool:
    return str(plan.status or "") == "approved"


def _resolve_window(range_key: str) -> tuple[dt.datetime, str]:
    now = dt.datetime.utcnow()
    if range_key == "24h":
        return now - dt.timedelta(hours=24), "hour"
    if range_key == "30d":
        return now - dt.timedelta(days=30), "day"
    return now - dt.timedelta(days=7), "day"


def _bucket_label(timestamp: dt.datetime, granularity: str) -> str:
    return timestamp.strftime("%m-%d") if granularity == "day" else timestamp.strftime("%m-%d %H:00")


def get_zone_trend(db: Session, zone_id: str, range_key: str = "7d") -> dict:
    since, granularity = _resolve_window(range_key)
    status = get_zone_status(db, zone_id)
    zone = status["zone"]
    labels: list[str] = []
    moisture_values: list[float] = []

    rows = (
        db.query(SensorData)
        .filter(SensorData.timestamp >= since)
        .order_by(SensorData.timestamp.asc())
        .all()
    )
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row.sensor_id not in zone.get("sensor_ids", []):
            continue
        grouped[_bucket_label(row.timestamp, granularity)].append(float(row.soil_moisture or 0.0))

    for label, values in grouped.items():
        labels.append(label)
        moisture_values.append(round(sum(values) / len(values), 2))

    if not labels:
        average = status["sensor_summary"].get("average", {})
        labels = [_bucket_label(dt.datetime.utcnow(), granularity)]
        moisture_values = [round(float(average.get("soil_moisture", 0.0) or 0.0), 2)]

    return {
        "zone_id": zone_id,
        "zone_name": zone["name"],
        "range": range_key,
        "labels": labels,
        "soil_moisture": moisture_values,
        "threshold": [float(zone.get("soil_moisture_threshold", 40.0)) for _ in labels],
    }


def get_plan_funnel(db: Session, range_key: str = "7d") -> dict:
    since, _ = _resolve_window(range_key)
    plans = db.query(IrrigationPlan).filter(IrrigationPlan.created_at >= since).all()
    return {
        "range": range_key,
        "items": [
            {"stage": "generated", "count": len(plans)},
            {"stage": "pending", "count": sum(1 for plan in plans if _is_pending_plan(plan))},
            {"stage": "approved", "count": sum(1 for plan in plans if _is_approved_plan(plan))},
            {"stage": "executed", "count": sum(1 for plan in plans if _is_executed_plan(plan))},
            {"stage": "completed_or_rejected", "count": sum(1 for plan in plans if plan.status in {"completed", "rejected", "superseded", "cancelled"})},
        ],
    }


def get_alert_trend(db: Session, range_key: str = "7d") -> dict:
    since, granularity = _resolve_window(range_key)
    alerts = db.query(AlertEvent).filter(AlertEvent.created_at >= since).all()
    labels_map: dict[str, dict[str, int]] = defaultdict(lambda: {"high": 0, "medium": 0, "low": 0})
    for alert in alerts:
        labels_map[_bucket_label(alert.created_at, granularity)][alert.severity] += 1

    labels = sorted(labels_map.keys())
    if not labels:
        labels = [_bucket_label(dt.datetime.utcnow(), granularity)]
        labels_map[labels[0]]

    return {
        "range": range_key,
        "labels": labels,
        "series": {
            "high": [labels_map[label]["high"] for label in labels],
            "medium": [labels_map[label]["medium"] for label in labels],
            "low": [labels_map[label]["low"] for label in labels],
        },
    }


def get_analytics_overview(db: Session, range_key: str = "7d") -> dict:
    zones = list_zones(db)
    zone_health = []
    pending_alerts = [alert for alert in list_alert_events(db, limit=200) if alert.status != "resolved"]
    plans = list_plans(db, limit=200)

    for zone in zones:
        status = get_zone_status(db, zone.zone_id)
        average = status["sensor_summary"].get("average", {})
        moisture = float(average.get("soil_moisture", 0.0) or 0.0)
        threshold = float(zone.soil_moisture_threshold or 40.0)
        zone_health.append(
            {
                "zone_id": zone.zone_id,
                "zone_name": zone.name,
                "soil_moisture": round(moisture, 2),
                "deficit": round(max(0.0, threshold - moisture), 2),
                "actuator_status": status["actuator"]["status"] if status.get("actuator") else "unknown",
                "alert_count": sum(1 for alert in pending_alerts if alert.zone_id == zone.zone_id),
            }
        )

    primary_zone = zones[0].zone_id if zones else None
    soil_trend = get_zone_trend(db, primary_zone, range_key) if primary_zone else {"labels": [], "soil_moisture": [], "threshold": []}
    funnel = get_plan_funnel(db, range_key)
    alert_trend = get_alert_trend(db, range_key)

    return {
        "range": range_key,
        "kpis": {
            "zone_count": len(zones),
            "pending_plan_count": sum(1 for plan in plans if _is_pending_plan(plan)),
            "active_alert_count": sum(1 for alert in pending_alerts if alert.status in {"open", "acknowledged"}),
            "executed_plan_count": sum(1 for plan in plans if _is_executed_plan(plan)),
        },
        "soil_trend": soil_trend,
        "plan_funnel": funnel,
        "alert_trend": alert_trend,
        "zone_health": zone_health,
    }
