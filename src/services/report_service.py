"""
CSV report export service for HydroAgent.
"""
from __future__ import annotations

import csv
import io

from sqlalchemy.orm import Session

from src.database.models import AlertEvent, AuditEvent
from src.services.analytics_service import get_zone_trend
from src.services.irrigation_service import get_zone_status, list_plans, list_zones


def _is_executed_plan(plan) -> bool:
    return str(getattr(plan, "status", "") or "") in {"executing", "completed"} or str(getattr(plan, "execution_status", "") or "") in {"running", "stopped", "executed"}


def _write_csv(rows: list[dict], fieldnames: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def export_operations_report(db: Session) -> str:
    rows = []
    plans = list_plans(db, limit=200)
    for zone in list_zones(db):
        status = get_zone_status(db, zone.zone_id)
        sensor_average = status["sensor_summary"].get("average", {})
        latest_plan = status.get("pending_plan") or next((plan.to_dict() for plan in plans if plan.zone_id == zone.zone_id), {})
        alert_count = (
            db.query(AlertEvent)
            .filter(AlertEvent.zone_id == zone.zone_id, AlertEvent.status.in_(["open", "acknowledged"]))
            .count()
        )
        rows.append(
            {
                "timestamp": status["sensor_summary"].get("timestamp"),
                "zone_id": zone.zone_id,
                "zone_name": zone.name,
                "soil_moisture": sensor_average.get("soil_moisture"),
                "threshold": zone.soil_moisture_threshold,
                "plan_status": latest_plan.get("status"),
                "approval_status": latest_plan.get("approval_status"),
                "execution_status": latest_plan.get("execution_status"),
                "alert_count": alert_count,
            }
        )

    return _write_csv(
        rows,
        [
            "timestamp",
            "zone_id",
            "zone_name",
            "soil_moisture",
            "threshold",
            "plan_status",
            "approval_status",
            "execution_status",
            "alert_count",
        ],
    )


def export_audit_report(db: Session) -> str:
    rows = [
        {
            "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            "event_type": event.event_type,
            "object_type": event.object_type,
            "object_id": event.object_id,
            "actor": event.actor,
            "result": event.result,
            "comment": event.comment,
        }
        for event in db.query(AuditEvent).order_by(AuditEvent.occurred_at.desc()).all()
    ]
    return _write_csv(
        rows,
        ["occurred_at", "event_type", "object_type", "object_id", "actor", "result", "comment"],
    )


def export_zone_report(db: Session, zone_id: str) -> str:
    trend = get_zone_trend(db, zone_id, "7d")
    plans = [plan for plan in list_plans(db, limit=200) if plan.zone_id == zone_id]
    rows = [
        {
            "label": label,
            "soil_moisture": moisture,
            "threshold": threshold,
            "plan_count": len(plans),
            "executed_plan_count": sum(1 for plan in plans if _is_executed_plan(plan)),
            "recent_alert_count": db.query(AlertEvent).filter(AlertEvent.zone_id == zone_id).count(),
        }
        for label, moisture, threshold in zip(trend["labels"], trend["soil_moisture"], trend["threshold"], strict=False)
    ]
    return _write_csv(
        rows,
        ["label", "soil_moisture", "threshold", "plan_count", "executed_plan_count", "recent_alert_count"],
    )
